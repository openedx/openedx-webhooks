import re

import requests
from flask import render_template
from urlobject import URLObject

from openedx_webhooks import celery
from openedx_webhooks.info import (
    get_labels_file, get_people_file,
    is_contractor_pull_request, is_internal_pull_request, is_bot_pull_request,
    is_committer_pull_request, pull_request_has_cla,
)
from openedx_webhooks.oauth import github_bp, jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import (
    memoize, paginated_get, sentry_extra_context, get_jira_custom_fields,
    jira_paginated_get,
)


def log_check_response(response, raise_for_status=True):
    """
    Logs HTTP request and response at debug level and checks if it succeeded.

    Arguments:
        response (requests.Response)
        raise_for_status (bool): if True, call raise_for_status on the response
            also.
    """
    msg = "{0.method} {0.url}: {0.body}".format(response.request)
    logger.debug(msg)
    msg = "{0.status_code} {0.reason} for {0.url}: {0.content}".format(response)
    logger.debug(msg)
    if raise_for_status:
        response.raise_for_status()


@celery.task(bind=True)
def pull_request_opened_task(_, pull_request):
    """A bound Celery task to call pull_request_opened."""
    return pull_request_opened(pull_request)

def pull_request_opened(pr):
    """
    Process a pull request.

    This is called when a pull request is opened, or when the pull requests of
    a repo are re-scanned. This function will ignore internal pull requests,
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

    logger.info(f"Processing {repo} PR #{num} by @{user}...")

    if is_bot_pull_request(pr):
        # Bots never need OSPR attention.
        logger.info(f"@{user} is a bot, ignored.")
        return None, False

    if is_internal_pull_request(pr):
        # not an open source pull request, don't create an issue for it
        logger.info(f"@{user} opened PR #{num} against {repo} (internal PR)")
        return None, False

    if is_contractor_pull_request(pr):
        # have we already left a contractor comment?
        if has_contractor_comment(pr):
            logger.info(f"Already left contractor comment for PR #{num}")
            return None, False

        # Don't create a JIRA issue, but leave a comment.
        logger.info(f"Posting contractor comment to PR #{num}")
        add_comment_to_pull_request(pr, github_contractor_pr_comment(pr))
        return None, True

    issue_key = get_jira_issue_key(pr)
    if issue_key:
        logger.info(f"Already created {issue_key} for PR #{num} against {repo}")
        return issue_key, False

    synchronize_labels(repo)

    jira_labels = []
    jira_project = "OSPR"
    jira_extra_fields = []
    jira_status = "Needs Triage"
    github_labels = []
    committer = False
    has_cla = pull_request_has_cla(pr)

    blended_id = get_blended_project_id(pr)
    if blended_id is not None:
        jira_labels.append("blended")
        jira_project = "BLENDED"
        github_labels.append("blended")
        blended_epic = find_blended_epic(blended_id)
        custom_fields = get_jira_custom_fields(jira_bp.session)
        jira_extra_fields.extend([
            ("Epic Link", blended_epic["key"]),
            ("Platform Map Area (Levels 1 & 2)",
                blended_epic["fields"].get(custom_fields["Platform Map Area (Levels 1 & 2)"])),
        ])
    else:
        github_labels.append("open-source-contribution")
        committer = is_committer_pull_request(pr)
        if committer:
            jira_labels.append("core-committer")
            jira_status = "Open edX Community Review"
            github_labels.append("core committer")
        else:
            if not has_cla:
                jira_status = "Community Manager Review"

    # Create an issue on Jira.
    new_issue = create_ospr_issue(pr, jira_labels, jira_project, jira_extra_fields)
    issue_key = new_issue["key"]
    sentry_extra_context({"new_issue": new_issue})

    # Add a comment to the Github pull request with a link to the JIRA issue.
    if blended_id is not None:
        comment_body = github_blended_pr_comment(pr, new_issue, blended_epic)
    elif committer:
        comment_body = github_committer_pr_comment(pr, new_issue)
    else:
        comment_body = github_community_pr_comment(pr, new_issue)

    if has_cla:
        comment_body += "\n<!-- jenkins ok to test -->"

    logger.info(f"Commenting on PR #{num} with issue id {issue_key}")
    add_comment_to_pull_request(pr, comment_body)

    # Set the GitHub labels.
    logger.info(f"Updating GitHub labels on PR #{num}...")
    github_labels.append(jira_status.lower())
    update_labels_on_pull_request(pr, github_labels)

    # Set the Jira status.
    if jira_status != "Needs Triage":
        transition_jira_issue(issue_key, jira_status)

    logger.info(f"@{user} opened PR #{num} against {repo}, created {issue_key} to track it")
    return issue_key, True


def create_ospr_issue(pr, labels, project, extra_fields):
    """
    Create a new OSPR or OSPR-like issue for a pull request.

    Returns the JSON describing the issue.
    """
    num = pr["number"]
    repo = pr["base"]["repo"]["full_name"]

    user_name, institution = get_name_and_institution_for_pr(pr)

    custom_fields = get_jira_custom_fields(jira_bp.session)
    new_issue = {
        "fields": {
            "project": {
                "key": project,
            },
            "issuetype": {
                "name": "Pull Request Review",
            },
            "summary": pr["title"],
            "description": pr["body"],
            "labels": labels,
            "customfield_10904": pr["html_url"],        # "URL" is ambiguous, use the internal name.
            custom_fields["PR Number"]: num,
            custom_fields["Repo"]: repo,
            custom_fields["Contributor Name"]: user_name,
        }
    }
    if institution:
        new_issue["fields"][custom_fields["Customer"]] = [institution]
    for name, value in extra_fields:
        new_issue["fields"][custom_fields[name]] = value
    sentry_extra_context({"new_issue": new_issue})

    logger.info(f"Creating new JIRA issue for PR #{num}...")
    resp = jira_bp.session.post("/rest/api/2/issue", json=new_issue)
    log_check_response(resp)

    new_issue_body = resp.json()
    new_issue["key"] = new_issue_body["key"]
    return new_issue


def get_name_and_institution_for_pr(pr):
    """
    Get the author name and institution for a pull request.

    The returned name will always be a string. The institution might be None.

    Returns:
        name, institution
    """
    github = github_bp.session
    user = pr["user"]["login"]
    people = get_people_file()

    user_name = None
    if user in people:
        user_name = people[user].get("name", "")
    if not user_name:
        resp = github.get(pr["user"]["url"])
        if resp.ok:
            user_name = resp.json().get("name", user)
        else:
            user_name = user

    institution = people.get(user, {}).get("institution", None)

    return user_name, institution


def add_comment_to_pull_request(pr, comment_body):
    """
    Add a comment to a pull request.
    """
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    url = f"/repos/{repo}/issues/{num}/comments"
    resp = github_bp.session.post(url, json={"body": comment_body})
    log_check_response(resp)


def update_labels_on_pull_request(pr, labels):
    """
    Change the labels on a pull request.

    Arguments:
        pr: a dict of pull request info.
        labels: a list of strings.
    """
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    url = f"/repos/{repo}/issues/{num}"
    resp = github_bp.session.patch(url, json={"labels": labels})
    log_check_response(resp)


@celery.task(bind=True)
def pull_request_closed_task(_, pull_request):
    """A bound Celery task to call pull_request_closed."""
    return pull_request_closed(pull_request)


def pull_request_closed(pull_request):
    """
    A GitHub pull request has been merged or closed. Synchronize the JIRA issue
    to also be in the "merged" or "closed" state. Returns a boolean: True
    if the JIRA issue was correctly synchronized, False otherwise. (However,
    these booleans are ignored.)
    """
    pr = pull_request
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    merged = pr["merged"]

    issue_key = get_jira_issue_key(pr)
    if not issue_key:
        logger.info(f"Couldn't find Jira issue for PR #{num} against {repo}")
        return "no JIRA issue :("
    sentry_extra_context({"jira_key": issue_key})

    # close the issue on JIRA
    new_status = "Merged" if merged else "Rejected"
    logger.info(f"Closing Jira issue {issue_key} as {new_status}...")
    if not transition_jira_issue(issue_key, new_status):
        return False

    action = "merged" if merged else "closed"
    logger.info(
        f"PR #{num} against {repo} was {action}, moved {issue_key} to status {new_status}"
    )
    return True


def transition_jira_issue(issue_key, status_name):
    """
    Transition a Jira issue to a new status.

    Returns:
        True if the issue was changed.

    """
    jira = jira_bp.session
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    transitions_resp = jira.get(transition_url)
    log_check_response(transitions_resp, raise_for_status=False)
    if transitions_resp.status_code == requests.codes.not_found:
        # JIRA issue has been deleted
        return False
    transitions_resp.raise_for_status()

    transitions = transitions_resp.json()["transitions"]

    sentry_extra_context({"transitions": transitions})

    transition_id = None
    for t in transitions:
        if t["to"]["name"] == status_name:
            transition_id = t["id"]
            break

    if not transition_id:
        # maybe the issue is *already* in the right status?
        issue_url = "/rest/api/2/issue/{key}".format(key=issue_key)
        issue_resp = jira.get(issue_url)
        issue_resp.raise_for_status()
        issue = issue_resp.json()
        sentry_extra_context({"jira_issue": issue})
        current_status = issue["fields"]["status"]["name"]
        if current_status == status_name:
            msg = "{key} is already in status {status}".format(
                key=issue_key, status=status_name
            )
            logger.info(msg)
            return False

        # nope, raise an error message
        fail_msg = (
            "{key} cannot be transitioned directly from status {curr_status} "
            "to status {new_status}. Valid status transitions are: {valid}".format(
                key=issue_key,
                new_status=status_name,
                curr_status=current_status,
                valid=", ".join(t["to"]["name"] for t in transitions),
            )
        )
        logger.error(fail_msg)
        raise Exception(fail_msg)

    logger.info('Changing JIRA issue status...')
    transition_resp = jira.post(transition_url, json={
        "transition": {
            "id": transition_id,
        }
    })
    log_check_response(transition_resp)
    return True


@celery.task(bind=True)
def rescan_repository(self, repo):
    """
    rescans a single repo for new prs
    """
    github = github_bp.session
    sentry_extra_context({"repo": repo})
    url = "/repos/{repo}/pulls".format(repo=repo)
    created = {}
    if not self.request.called_directly:
        self.update_state(state='STARTED', meta={'repo': repo})

    def page_callback(response):
        if not response.ok or self.request.called_directly:
            return
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
        self.update_state(state='STARTED', meta=state_meta)

    for pull_request in paginated_get(url, session=github, callback=page_callback):
        sentry_extra_context({"pull_request": pull_request})
        issue_key = get_jira_issue_key(pull_request)
        is_internal = is_internal_pull_request(pull_request)
        if not issue_key and not is_internal:
            issue_key, issue_created = pull_request_opened(pull_request)
            if issue_created:
                created[pull_request["number"]] = issue_key

    logger.info(
        "Created {num} JIRA issues on repo {repo}. PRs are {prs}".format(
            num=len(created), repo=repo, prs=created.keys(),
        ),
    )
    info = {"repo": repo}
    if created:
        info["created"] = created
    return info


def get_bot_comments(pull_request):
    """Find all the comments the bot has made on a pull request."""
    me = github_whoami()
    my_username = me["login"]
    comment_url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"],
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github_bp.session):
        # I only care about comments I made
        if comment["user"]["login"] == my_username:
            yield comment


def get_jira_issue_key(pull_request):
    """Find mention of a Jira issue number in bot-authored comments."""
    for comment in get_bot_comments(pull_request):
        # search for the first occurrence of a JIRA ticket key in the comment body
        match = re.search(r"\b([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            return match.group(0)
    return None


def synchronize_labels(repo):
    """Ensure the labels in `repo` match the specs in repo-tools-data/labels.yaml"""

    url = f"/repos/{repo}/labels"
    repo_labels = {lbl["name"]: lbl for lbl in paginated_get(url, session=github_bp.session)}
    desired_labels = get_labels_file()
    for name, label_data in desired_labels.items():
        if label_data.get("delete", False):
            # A label that should not exist in the repo.
            if name in repo_labels:
                logger.info(f"Deleting label {name} from {repo}")
                resp = github_bp.session.delete(f"{url}/{name}")
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
                    resp = github_bp.session.patch(f"{url}/{name}", json=label_data)
                    log_check_response(resp)
            else:
                logger.info(f"Adding label {name} to {repo}")
                resp = github_bp.session.post(url, json=label_data)
                log_check_response(resp)


def github_community_pr_comment(pull_request, jira_issue):
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * contain a link to our process documentation
    """
    # does the user have a valid, signed contributor agreement?
    has_signed_agreement = pull_request_has_cla(pull_request)
    return render_template("github_community_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
        issue_key=jira_issue["key"],
        has_signed_agreement=has_signed_agreement,
    )


def github_contractor_pr_comment(pull_request):
    """
    For a newly-created pull request from a contractor that edX works with,
    write a comment on the pull request. The comment should:

    * Help the author determine if the work is paid for by edX or not
    * If not, show the author how to trigger the creation of an OSPR issue
    """
    return render_template("github_contractor_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
    )


def github_committer_pr_comment(pull_request, jira_issue):
    """
    Create the body of the comment for new pull requests from core committers.
    """
    return render_template("github_committer_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
        issue_key=jira_issue["key"],
    )


def github_blended_pr_comment(pull_request, jira_issue, blended_epic):
    """
    Create a Blended PR comment.
    """
    custom_fields = get_jira_custom_fields(jira_bp.session)
    project_name = blended_epic["fields"].get(custom_fields["Blended Project ID"])
    project_page = blended_epic["fields"].get(custom_fields["Blended Project Status Page"])
    return render_template("github_blended_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
        issue_key=jira_issue["key"],
        epic=blended_epic["key"],
        project_name=project_name,
        project_page=project_page,
    )


def has_contractor_comment(pull_request):
    """
    Given a pull request, this function returns a boolean indicating whether
    we have already left a comment on that pull request that suggests
    making an OSPR issue for the pull request.
    """
    for comment in get_bot_comments(pull_request):
        magic_phrase = "It looks like you're a member of a company that does contract work for edX."
        if magic_phrase in comment["body"]:
            return True
    return False


def get_blended_project_id(pull_request):
    """
    Find the blended project id in the pull request, if any.

    Returns:
        An int ("[BD-5]" returns 5, for example) found in the pull request, or None.
    """
    m = re.search(r"\[\s*BD\s*-\s*(\d+)\s*\]", pull_request["title"])
    if m:
        return int(m[1])


def find_blended_epic(project_id):
    """
    Find the blended epic for a blended project.
    """
    jql = (
        '"Blended Project ID" ~ "BD-00{id}" or ' +
        '"Blended Project ID" ~ "BD-0{id}" or ' +
        '"Blended Project ID" ~ "BD-{id}"'
    ).format(id=project_id)
    issues = list(jira_paginated_get("/rest/api/2/search", jql=jql, obj_name="issues", session=jira_bp.session))
    if not issues:
        logger.info(f"Couldn't find a blended epic for {project_id}")
    elif len(issues) > 1:
        logger.info(f"Found {len(issues)} blended epics for {project_id}")
    else:
        return issues[0]


@memoize
def github_whoami():
    self_resp = github_bp.session.get("/user")
    self_resp.raise_for_status()
    return self_resp.json()
