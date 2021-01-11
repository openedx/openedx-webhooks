from typing import Optional, Tuple

from urlobject import URLObject

from openedx_webhooks import celery
from openedx_webhooks.info import (
    get_jira_issue_key,
    get_labels_file,
    is_internal_pull_request,
)
from openedx_webhooks.oauth import get_github_session
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.pr_tracking import (
    current_support_state,
    desired_support_state,
    PrTrackingFixer,
)
from openedx_webhooks.types import PrDict
from openedx_webhooks.utils import (
    log_check_response,
    paginated_get,
    retry_get,
    sentry_extra_context,
)


@celery.task(bind=True)
def pull_request_changed_task(_, pull_request):
    """A bound Celery task to call pull_request_changed."""
    return pull_request_changed(pull_request)

def pull_request_changed(pr: PrDict) -> Tuple[Optional[str], bool]:
    """
    Process a pull request.

    This is called when a pull request is opened, edited, or closed, or when
    pull requests are re-scanned.  This function will ignore internal pull requests,
    and will add a comment to pull requests made by contractors (if if has not
    yet added a comment).

    This function must be idempotent. Every time the repositories are re-scanned,
    this function will be called for pull requests that have already been opened.
    As a result, it should not comment on the pull request without checking to
    see if it has *already* commented on the pull request.

    Returns a 2-tuple. The first element in the tuple is the key of the JIRA
    issue associated with the pull request, if any, as a string. The second
    element in the tuple is a boolean indicating if this function did any
    work, such as making a JIRA issue or commenting on the pull request.
    """

    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]

    logger.info(f"Processing PR {repo} #{num} by @{user}...")

    desired = desired_support_state(pr)
    if desired is not None:
        synchronize_labels(repo)
        current = current_support_state(pr)
        fixer = PrTrackingFixer(pr, current, desired)
        fixer.fix()
        return fixer.result()
    else:
        return None, False


@celery.task(bind=True)
def rescan_repository_task(self, repo, allpr):
    """A bound Celery task to call rescan_repository."""
    return rescan_repository(repo, allpr, task=self)


def rescan_repository(repo, allpr, task=None):
    """
    Re-scans a single repo for external pull requests.

    If `allpr` is False, then only open pull requests are considered.
    If `allpr` is True, then all external pull requests are re-scanned.

    """
    sentry_extra_context({"repo": repo})
    state = "all" if allpr else "open"
    url = f"/repos/{repo}/pulls?state={state}"

    created = {}
    if task is not None:
        task.update_state(state='STARTED', meta={'repo': repo})

    def page_callback(response):
        if task is not None and response.ok:
            current_url = URLObject(response.url)
            current_page = int(current_url.query_dict.get("page", 1))
            link_last = response.links.get("last")
            if link_last:
                last_url = URLObject(link_last['url'])
                last_page = int(last_url.query_dict["page"])
            else:
                last_page = current_page
            state_meta = {
                "repo": repo,
                "current_page": current_page,
                "last_page": last_page
            }
            task.update_state(state='STARTED', meta=state_meta)

    # Pull requests before this will not be rescanned. Contractor messages
    # are hard to rescan, and in other ways the early pull requests are
    # different enough that it's hard to do it right.  Our last contractor
    # message was in December 2017.
    earliest = "2018-01-01"

    for pull_request in paginated_get(url, session=get_github_session(), callback=page_callback):
        sentry_extra_context({"pull_request": pull_request})
        if is_internal_pull_request(pull_request):
            # Never rescan internal pull requests.
            continue

        if pull_request["created_at"] < earliest:
            continue

        should_scan = True
        if not allpr:
            issue_key = get_jira_issue_key(pull_request)
            should_scan = not issue_key

        if should_scan:
            # Listed pull requests don't have all the information we need,
            # so get the full description.
            resp = retry_get(get_github_session(), pull_request["url"])
            resp.raise_for_status()
            pull_request = resp.json()

            issue_key, anything_happened = pull_request_changed(pull_request)
            if anything_happened:
                created[pull_request["number"]] = issue_key

    logger.info(
        "Created {num} JIRA issues on repo {repo}. PRs are {prs}".format(
            num=len(created), repo=repo, prs=list(created.keys()),
        ),
    )
    info = {"repo": repo}
    if created:
        info["created"] = created
    return info


def synchronize_labels(repo: str) -> None:
    """Ensure the labels in `repo` match the specs in repo-tools-data/labels.yaml"""

    url = f"/repos/{repo}/labels"
    repo_labels = {lbl["name"]: lbl for lbl in paginated_get(url, session=get_github_session())}
    desired_labels = get_labels_file()
    for name, label_data in desired_labels.items():
        if label_data.get("delete", False):
            # A label that should not exist in the repo.
            if name in repo_labels:
                logger.info(f"Deleting label {name} from {repo}")
                resp = get_github_session().delete(f"{url}/{name}")
                log_check_response(resp)
        else:
            # A label that should exist in the repo.
            label_data["name"] = name
            if name in repo_labels:
                repo_label = repo_labels[name]
                color_differs = repo_label["color"] != label_data["color"]
                repo_desc = repo_label.get("description", "") or ""
                desired_desc = label_data.get("description", "") or ""
                desc_differs = repo_desc != desired_desc
                if color_differs or desc_differs:
                    logger.info(f"Updating label {name} in {repo}")
                    resp = get_github_session().patch(f"{url}/{name}", json=label_data)
                    log_check_response(resp)
            else:
                logger.info(f"Adding label {name} to {repo}")
                resp = get_github_session().post(url, json=label_data)
                log_check_response(resp)
