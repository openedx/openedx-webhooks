"""
Queuable background tasks to do large work.
"""

import traceback

from typing import Dict, Set

from urlobject import URLObject

from openedx_webhooks import celery
from openedx_webhooks.auth import get_github_session
from openedx_webhooks.info import is_internal_pull_request
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.pr_tracking import (
    current_support_state,
    desired_support_state,
    DryRunFixingActions,
    FixResult,
    PrTrackingFixer,
)
from openedx_webhooks.types import JiraId, PrDict
from openedx_webhooks.utils import (
    log_rate_limit,
    paginated_get,
    retry_get,
    sentry_extra_context,
)


@celery.task(bind=True)
def pull_request_changed_task(_, pull_request):
    """A bound Celery task to call pull_request_changed."""
    try:
        pull_request_changed(pull_request)
        log_rate_limit()
    except Exception:
        logger.exception("Couldn't pull_request_changed_task")
        raise


def pull_request_changed(pr: PrDict, actions=None) -> FixResult:
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

    Returns an object with details of the associated Jira issues.
    """

    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]

    logger.info(f"Processing PR {repo}#{num} by @{user}...")

    desired = desired_support_state(pr)
    current = current_support_state(pr)
    fixer = PrTrackingFixer(pr, current, desired, actions=actions)
    fixer.fix()
    return fixer.result()


class PaginateCallback:
    """
    A callback for paginated_get which updates the celery task with URL progress.
    """
    def __init__(self, task, meta):
        self.task = task
        self.meta = meta

    def __call__(self, response):
        if response.ok:
            current_url = URLObject(response.url)
            current_page = int(current_url.query_dict.get("page", 1))
            link_last = response.links.get("last")
            if link_last:
                last_url = URLObject(link_last['url'])
                last_page = int(last_url.query_dict["page"])
            else:
                last_page = current_page
            state_meta = {
                "current_page": current_page,
                "last_page": last_page
            }
            state_meta.update(self.meta)
            self.task.update_state(state='STARTED', meta=state_meta)


@celery.task(bind=True)
def rescan_repository_task(task, repo, allpr, dry_run, earliest, latest):
    """A bound Celery task to call rescan_repository."""
    meta = {"repo": repo}
    task.update_state(state="STARTED", meta=meta)
    callback = PaginateCallback(task, meta=meta)
    return rescan_repository(repo, allpr, dry_run, earliest, latest, page_callback=callback)


def rescan_repository(
        repo: str,
        allpr: bool,
        dry_run: bool = False,
        earliest: str = "",
        latest: str = "",
        page_callback=None,
    ) -> Dict:
    """
    Re-scans a single repo for external pull requests.

    Arguments:
        allpr (bool): if False, then only open pull requests are considered.
            If True, then all external pull requests are re-scanned.
        dry_run (bool): if True, don't write to GitHub or Jira. Put names of
            action methods and their arguments into the "dry_run_actions" key
            of the return value.
        earliest (str): An ISO8401-formatted date string ("2019-06-28") of the
            earliest pull requests (by creation date) to be rescanned.  Nothing
            before 2018 will be rescanned regardless of this argument.
        latest (str): An ISO8401-formatted date string ("2019-12-25") of the
            latest pull requests (by creation date) to be rescanned.

    """
    sentry_extra_context({"repo": repo})
    state = "all" if allpr else "open"
    url = f"/repos/{repo}/pulls?state={state}"

    changed: Dict[int, Set[JiraId]] = {}
    errors: Dict[int, str] = {}
    dry_run_actions = {}

    # Pull requests before this will not be rescanned. Contractor messages
    # are hard to rescan, and in other ways the early pull requests are
    # different enough that it's hard to do it right.  Our last contractor
    # message was in December 2017.
    earliest = max("2018-01-01", earliest)

    pull_request: PrDict
    for pull_request in paginated_get(url, session=get_github_session(), callback=page_callback):
        sentry_extra_context({"pull_request": pull_request})
        if is_internal_pull_request(pull_request):
            # Never rescan internal pull requests.
            continue

        if pull_request["created_at"] < earliest:
            continue

        if latest and pull_request["created_at"] > latest:
            continue

        actions = DryRunFixingActions() if dry_run else None
        try:
            # Listed pull requests don't have all the information we need,
            # so get the full description.
            resp = retry_get(get_github_session(), pull_request["url"])
            resp.raise_for_status()
            pull_request = resp.json()

            result = pull_request_changed(pull_request, actions=actions)
        except Exception:       # pylint: disable=broad-except
            errors[pull_request["number"]] = traceback.format_exc()
        else:
            if result.changed_jira_issues:
                changed[pull_request["number"]] = result.changed_jira_issues
            if dry_run:
                assert actions is not None
                dry_run_actions[pull_request["number"]] = actions.action_calls

    if not dry_run:
        logger.info(
            "Changed {num} JIRA issues on repo {repo}. PRs are {prs}".format(
                num=len(changed), repo=repo, prs=list(changed.keys()),
            ),
        )

    info: Dict = {
        "repo": repo,
        "changed": changed,
        "errors": errors,
    }
    if dry_run_actions:
        info["dry_run_actions"] = dry_run_actions
    return info


@celery.task(bind=True)
def rescan_organization_task(task, org, allpr, dry_run, earliest, latest):
    """A bound Celery task to call rescan_organization."""
    meta = {"org": org}
    task.update_state(state="STARTED", meta=meta)
    callback = PaginateCallback(task, meta)
    return rescan_organization(org, allpr, dry_run, earliest, latest, page_callback=callback)

def rescan_organization(
        org: str,
        allpr: bool = False,
        dry_run: bool = False,
        earliest: str = "",
        latest: str = "",
        page_callback=None,
    ) -> Dict:
    """
    Re-scan an entire organization.

    See rescan_repository for details of the arguments.
    """
    infos = {}
    org_url = f"https://api.github.com/orgs/{org}/repos"
    repos = list(paginated_get(org_url, callback=page_callback))
    for irepo, repo in enumerate(repos):
        repo_name = repo["full_name"]
        if page_callback is not None:
            page_callback.meta = {"repo": repo_name, "repo_num": f"{irepo+1}/{len(repos)}"}
        info = rescan_repository(repo_name, allpr, dry_run, earliest, latest, page_callback=page_callback)
        if list(info) != ["repo"]:
            infos[repo_name] = info
    return infos
