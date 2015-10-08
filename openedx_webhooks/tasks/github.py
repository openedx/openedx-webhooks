# coding=utf-8
from __future__ import unicode_literals, print_function

import json
import re
from datetime import date

from iso8601 import parse_date
from flask import render_template
from urlobject import URLObject

from openedx_webhooks import sentry, celery
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks import github_session as github
from openedx_webhooks.tasks import jira_session as jira
from openedx_webhooks.info import (
    get_people_file, is_internal_pull_request, is_contractor_pull_request
)
from openedx_webhooks.utils import memoize, paginated_get
from openedx_webhooks.jira_views import get_jira_custom_fields


@celery.task
def pull_request_opened(pull_request, ignore_internal=True, check_contractor=True):
    """
    Process a pull request. This is called when a pull request is opened, or
    when the pull requests of a repo are re-scanned. By default, this function
    will ignore internal pull requests, and will add a comment to pull requests
    made by contractors (if if has not yet added a comment). However,
    this function can be called in such a way that it processes those pull
    requests anyway.

    Returns a 2-tuple. The first element in the tuple is the key of the JIRA
    issue associated with the pull request, if any, as a string. The second
    element in the tuple is a boolean indicating if this function did any
    work, such as making a JIRA issue or commenting on the pull request.
    """
    pr = pull_request
    user = pr["user"]["login"].decode('utf-8')
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    if ignore_internal and is_internal_pull_request(pr, session=github):
        # not an open source pull request, don't create an issue for it
        logger.info(
            "@{user} opened PR #{num} against {repo} (internal PR)".format(
                user=user, repo=repo, num=num,
            ),
        )
        return None, False

    if check_contractor and is_contractor_pull_request(pr, session=github):
        # have we already left a contractor comment?
        if has_contractor_comment(pr, session=github):
            return None, False

        # don't create a JIRA issue, but leave a comment
        comment = {
            "body": github_contractor_pr_comment(pr),
        }
        url = "/repos/{repo}/issues/{num}/comments".format(
            repo=repo, num=num,
        )
        comment_resp = github.post(url, json=comment)
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

    repo = pr["base"]["repo"]["full_name"].decode('utf-8')
    people = get_people_file(session=github)
    custom_fields = get_jira_custom_fields(jira)

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
            custom_fields["URL"]: pr["html_url"],
            custom_fields["PR Number"]: pr["number"],
            custom_fields["Repo"]: pr["base"]["repo"]["full_name"],
            custom_fields["Contributor Name"]: user_name,
        }
    }
    institution = people.get(user, {}).get("institution", None)
    if institution:
        new_issue["fields"][custom_fields["Customer"]] = [institution]
    sentry.client.extra_context({"new_issue": new_issue})

    resp = jira.post("/rest/api/2/issue", json=new_issue)
    resp.raise_for_status()
    new_issue_body = resp.json()
    issue_key = new_issue_body["key"].decode('utf-8')
    new_issue["key"] = issue_key
    sentry.client.extra_context({"new_issue": new_issue})
    # add a comment to the Github pull request with a link to the JIRA issue
    comment = {
        "body": github_community_pr_comment(pr, new_issue_body, people),
    }
    url = "/repos/{repo}/issues/{num}/comments".format(
        repo=repo, num=pr["number"],
    )
    comment_resp = github.post(url, json=comment)
    comment_resp.raise_for_status()

    # Add the "Needs Triage" label to the PR
    issue_url = "/repos/{repo}/issues/{num}".format(repo=repo, num=pr["number"])
    label_resp = github.patch(issue_url, data=json.dumps({"labels": ["needs triage", "open-source-contribution"]}))
    label_resp.raise_for_status()

    logger.info(
        "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
            user=user, repo=repo,
            num=pr["number"], issue=issue_key,
        ),
    )
    return issue_key, True


@celery.task
def pull_request_closed(pull_request):
    pr = pull_request
    repo = pr["base"]["repo"]["full_name"].decode('utf-8')

    merged = pr["merged"]
    issue_key = get_jira_issue_key(pr)
    if not issue_key:
        logger.info(
            "Couldn't find JIRA issue for PR #{num} against {repo}".format(
                num=pr["number"], repo=repo,
            ),
        )
        return "no JIRA issue :("
    sentry.client.extra_context({"jira_key": issue_key})

    # close the issue on JIRA
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    transitions_resp = jira.get(transition_url)
    transitions_resp.raise_for_status()

    transitions = transitions_resp.json()["transitions"]

    sentry.client.extra_context({"transitions": transitions})

    transition_name = "Merged" if merged else "Rejected"
    transition_id = None
    for t in transitions:
        if t["to"]["name"] == transition_name:
            transition_id = t["id"]
            break

    if not transition_id:
        # maybe the issue is *already* in the right status?
        issue_url = "/rest/api/2/issue/{key}".format(key=issue_key)
        issue_resp = jira.get(issue_url)
        issue_resp.raise_for_status()
        issue = issue_resp.json()
        sentry.client.extra_context({"jira_issue": issue})
        current_status = issue["fields"]["status"]["name"].decode("utf-8")
        if current_status == transition_name:
            msg = "{key} is already in status {status}".format(
                key=issue_key, status=transition_name
            )
            logger.info(msg)
            return False

        # nope, raise an error message
        fail_msg = (
            "{key} cannot be transitioned directly from status {curr_status} "
            "to status {new_status}. Valid status transitions are: {valid}".format(
                key=issue_key,
                new_status=transition_name,
                curr_status=current_status,
                valid=", ".join(t["to"]["name"].decode('utf-8') for t in transitions),
            )
        )
        raise Exception(fail_msg)

    transition_resp = jira.post(transition_url, json={
        "transition": {
            "id": transition_id,
        }
    })
    transition_resp.raise_for_status()
    logger.info(
        "PR #{num} against {repo} was {action}, moving {issue} to status {status}".format(
            num=pr["number"],
            repo=repo,
            action="merged" if merged else "closed",
            issue=issue_key,
            status="Merged" if merged else "Rejected",
        ),
    )
    return True


@celery.task(bind=True)
def rescan_repository(self, repo):
    """
    rescans a single repo for new prs
    """
    sentry.client.extra_context({"repo": repo})
    url = "/repos/{repo}/pulls".format(repo=repo)
    created = {}
    if not self.request.called_directly:
        self.update_state(state='STARTED', meta={'repo': repo})

    def page_callback(response):
        if not response.ok:
            return
        current_url = URLObject(response.url)
        current_page = int(url.query_dict.get("page", 1))
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
        sentry.client.extra_context({"pull_request": pull_request})
        issue_key = get_jira_issue_key(pull_request)
        is_internal = is_internal_pull_request(pull_request, session=github)
        if not issue_key and not is_internal:
            # `pull_request_opened()` is a celery task, but by calling it as
            # a function instead of calling `.delay()` on it, we're eagerly
            # executing the task now, instead of adding it to the task queue
            # so it is executed later. As a result, this will return the values
            # that the `pull_request_opened()` function returns, rather than
            # return an AsyncResult object.
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


def get_jira_issue_key(pull_request):
    me = github_whoami()
    my_username = me["login"]
    comment_url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"].decode('utf-8'),
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github):
        # I only care about comments I made
        if comment["user"]["login"] != my_username:
            continue
        # search for the first occurrance of a JIRA ticket key in the comment body
        match = re.search(r"\b([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            return match.group(0).decode('utf-8')
    return None


def github_community_pr_comment(pull_request, jira_issue, people=None, session=None):
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * check for AUTHORS entry
    * contain a link to our process documentation
    """
    people = people or get_people_file(session=session)
    people = {user.lower(): values for user, values in people.items()}
    pr_author = pull_request["user"]["login"].decode('utf-8').lower()
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    # does the user have a valid, signed contributor agreement?
    has_signed_agreement = (
        pr_author in people and
        people[pr_author].get("expires_on", date.max) > created_at.date()
    )
    # is the user in the AUTHORS file?
    in_authors_file = False
    name = people.get(pr_author, {}).get("name", "")
    if name:
        authors_url = "https://raw.githubusercontent.com/{repo}/{branch}/AUTHORS".format(
            repo=pull_request["head"]["repo"]["full_name"].decode('utf-8'),
            branch=pull_request["head"]["ref"].decode('utf-8'),
        )
        authors_resp = github.get(authors_url)
        if authors_resp.ok:
            authors_content = authors_resp.text
            if name in authors_content:
                in_authors_file = True

    return render_template("github_community_pr_comment.md.j2",
        user=pull_request["user"]["login"].decode('utf-8'),
        repo=pull_request["base"]["repo"]["full_name"].decode('utf-8'),
        number=pull_request["number"],
        issue_key=jira_issue["key"].decode('utf-8'),
        has_signed_agreement=has_signed_agreement,
        in_authors_file=in_authors_file,
    )


def github_contractor_pr_comment(pull_request):
    """
    For a newly-created pull request from a contractor that edX works with,
    write a comment on the pull request. The comment should:

    * Help the author determine if the work is paid for by edX or not
    * If not, show the author how to trigger the creation of an OSPR issue
    """
    return render_template("github_contractor_pr_comment.md.j2",
        user=pull_request["user"]["login"].decode('utf-8'),
        repo=pull_request["base"]["repo"]["full_name"].decode('utf-8'),
        number=pull_request["number"],
    )


def has_contractor_comment(pull_request, session=None):
    """
    Given a pull request, this function returns a boolean indicating whether
    we have already left a comment on that pull request that suggests
    making an OSPR issue for the pull request.
    """
    me = github_whoami(session=session)
    my_username = me["login"]
    comment_url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"].decode('utf-8'),
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github):
        # I only care about comments I made
        if comment["user"]["login"] != my_username:
            continue
        magic_phrase = "It looks like you're a member of a company that does contract work for edX."
        if magic_phrase in comment["body"]:
            return True
    return False


@memoize
def github_whoami(session=None):
    session = session or github
    self_resp = session.get("/user")
    self_resp.raise_for_status()
    return self_resp.json()
