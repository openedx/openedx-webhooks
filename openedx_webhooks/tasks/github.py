import json
import re
from datetime import date

import requests
from flask import render_template
from iso8601 import parse_date
from urlobject import URLObject

from openedx_webhooks import celery
from openedx_webhooks.info import (
    get_people_file,
    is_contractor_pull_request, is_internal_pull_request, is_bot_pull_request
)
from openedx_webhooks.jira_views import get_jira_custom_fields
from openedx_webhooks.oauth import github_bp, jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import memoize, paginated_get, sentry_extra_context


def log_request_response(response):
    """
    Logs HTTP request and response at debug level.

    Arguments:
        response (requests.Response)
    """
    msg = "{0.method} {0.url}: {0.body}".format(response.request)
    logger.debug(msg)
    msg = "{0.status_code} {0.reason} for {0.url}: {0.content}".format(response)
    logger.debug(msg)


@celery.task(bind=True)
def pull_request_opened_task(_, pull_request, ignore_internal=True, check_contractor=True):
    """A bound Celery task to call pull_request_opened."""
    return pull_request_opened(
        pull_request,
        ignore_internal=ignore_internal,
        check_contractor=check_contractor,
    )

def pull_request_opened(pull_request, ignore_internal=True, check_contractor=True):
    """
    Process a pull request. This is called when a pull request is opened, or
    when the pull requests of a repo are re-scanned. By default, this function
    will ignore internal pull requests,
    and will add a comment to pull requests made by contractors (if if has not yet added
    a comment). However, this function can be called in such a way that it processes those pull
    requests anyway.

    This function must be idempotent. Every time the repositories are re-scanned,
    this function will be called for pull requests that have already been opened.
    As a result, it should not comment on the pull request without checking to
    see if it has *already* commented on the pull request.

    Returns a 2-tuple. The first element in the tuple is the key of the JIRA
    issue associated with the pull request, if any, as a string. The second
    element in the tuple is a boolean indicating if this function did any
    work, such as making a JIRA issue or commenting on the pull request.
    """

    github = github_bp.session
    pr = pull_request
    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    is_internal_pr = is_internal_pull_request(pr)

    msg = "Processing {} PR #{} by {}...".format(repo, num, user)
    logger.info(msg)

    if is_bot_pull_request(pr):
        # Bots never need OSPR attention.
        return None, False

    if ignore_internal and is_internal_pr:
        # not an open source pull request, don't create an issue for it
        msg = "@{user} opened PR #{num} against {repo} (internal PR)".format(user=user, repo=repo, num=num)
        logger.info(msg)
        return None, False

    if check_contractor and is_contractor_pull_request(pr):
        # have we already left a contractor comment?
        if has_contractor_comment(pr):
            msg = "Already left contractor comment for PR #{}".format(num)
            logger.info(msg)
            return None, False

        # don't create a JIRA issue, but leave a comment
        comment = {
            "body": github_contractor_pr_comment(pr),
        }
        url = "/repos/{repo}/issues/{num}/comments".format(repo=repo, num=num)
        msg = "Posting contractor comment to PR #{}".format(num)
        logger.info(msg)

        comment_resp = github.post(url, json=comment)
        log_request_response(comment_resp)
        comment_resp.raise_for_status()
        return None, True

    issue_key = get_jira_issue_key(pr)
    if issue_key:
        msg = "Already created {key} for PR #{num} against {repo}".format(
            key=issue_key,
            num=pr["number"],
            repo=pr["base"]["repo"]["full_name"],
        )
        logger.info(msg)
        return issue_key, False

    repo = pr["base"]["repo"]["full_name"]
    people = get_people_file()
    custom_fields = get_jira_custom_fields(jira_bp.session)

    user_name = None
    if user in people:
        user_name = people[user].get("name", "")
    if not user_name:
        user_resp = github.get(pr["user"]["url"])
        if user_resp.ok:
            user_name = user_resp.json().get("name", user)
        else:
            user_name = user

    # create an issue on JIRA!
    new_issue = {
        "fields": {
            "project": {
                "key": "OSPR",
            },
            "issuetype": {
                "name": "Pull Request Review",
            },
            "summary": pr["title"],
            "description": pr["body"],
            "customfield_10904": pr["html_url"],        # "URL" is ambiguous, use the internal name.
            custom_fields["PR Number"]: pr["number"],
            custom_fields["Repo"]: pr["base"]["repo"]["full_name"],
            custom_fields["Contributor Name"]: user_name,
        }
    }
    institution = people.get(user, {}).get("institution", None)
    if institution:
        new_issue["fields"][custom_fields["Customer"]] = [institution]
    sentry_extra_context({"new_issue": new_issue})

    logger.info('Creating new JIRA issue...')
    resp = jira_bp.session.post("/rest/api/2/issue", json=new_issue)
    log_request_response(resp)
    resp.raise_for_status()

    new_issue_body = resp.json()
    issue_key = new_issue_body["key"]
    new_issue["key"] = issue_key
    sentry_extra_context({"new_issue": new_issue})
    # add a comment to the Github pull request with a link to the JIRA issue
    comment = {
        "body": github_community_pr_comment(pr, new_issue_body),
    }
    url = "/repos/{repo}/issues/{num}/comments".format(repo=repo, num=pr["number"])
    logger.info('Creating new GitHub comment with JIRA issue...')
    comment_resp = github.post(url, json=comment)
    log_request_response(comment_resp)
    comment_resp.raise_for_status()

    # Add the "Needs Triage" label to the PR
    issue_url = "/repos/{repo}/issues/{num}".format(repo=repo, num=pr["number"])
    labels = {'labels': ['needs triage', 'open-source-contribution']}
    logger.info('Updating GitHub labels...')
    label_resp = github.patch(issue_url, data=json.dumps(labels))
    log_request_response(label_resp)
    label_resp.raise_for_status()

    msg = "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
        user=user,
        repo=repo,
        num=pr["number"],
        issue=issue_key,
    )
    logger.info(msg)
    return issue_key, True


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

    merged = pr["merged"]
    issue_key = get_jira_issue_key(pr)
    if not issue_key:
        msg = "Couldn't find JIRA issue for PR #{num} against {repo}".format(
            num=pr["number"], repo=repo,
        )
        logger.info(msg)
        return "no JIRA issue :("
    sentry_extra_context({"jira_key": issue_key})

    # close the issue on JIRA
    logger.info('Closing the issue on JIRA...')
    new_staus = "Merged" if merged else "Rejected"
    if not transition_jira_issue(issue_key, new_staus):
        return False

    msg = "PR #{num} against {repo} was {action}, moving {issue} to status {status}".format(
        num=pr["number"],
        repo=repo,
        action="merged" if merged else "closed",
        issue=issue_key,
        status="Merged" if merged else "Rejected",
    )
    logger.info(msg)
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
    log_request_response(transitions_resp)
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
    log_request_response(transition_resp)
    transition_resp.raise_for_status()
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
        # search for the first occurrance of a JIRA ticket key in the comment body
        match = re.search(r"\b([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            return match.group(0)
    return None


def pull_request_has_cla(pull_request):
    """Does this pull request have a valid CLA?"""
    pr_author = pull_request["user"]["login"].lower()
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    return person_has_cla(pr_author, created_at)


def person_has_cla(author, created_at):
    """Does `author` have a valid CLA at a point in time?"""
    people = get_people_file()
    people = {user.lower(): values for user, values in people.items()}
    has_signed_agreement = (
        author in people and
        people[author].get("expires_on", date.max) > created_at.date()
    )
    return has_signed_agreement


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


@memoize
def github_whoami():
    self_resp = github_bp.session.get("/user")
    self_resp.raise_for_status()
    return self_resp.json()
