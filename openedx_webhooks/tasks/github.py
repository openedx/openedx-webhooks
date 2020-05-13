import json
import os
import random
import re
from datetime import date

import requests
from flask import render_template, render_template_string
from iso8601 import parse_date
from urlobject import URLObject

from openedx_webhooks import celery
from openedx_webhooks.info import (
    get_people_file, get_repos_file, get_fun_fact_file, is_beta_tester_pull_request,
    is_contractor_pull_request, is_internal_pull_request, is_bot_pull_request
)
from openedx_webhooks.jira_views import get_jira_custom_fields
from openedx_webhooks.oauth import github_bp, jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.utils import (
    log_error, log_info, log_request_response
)
from openedx_webhooks.utils import memoize, paginated_get, sentry_extra_context

COVERLETTER_MARKER = "<!-- open edx coverletter -->"


@celery.task(bind=True)
def pull_request_opened(self, pull_request, ignore_internal=True, check_contractor=True):
    """
    Process a pull request. This is called when a pull request is opened, or
    when the pull requests of a repo are re-scanned. By default, this function
    will ignore internal pull requests (unless a repo has supplied .pr_cover_letter.md.j2),
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

    # Environment variable containing the Open edX release name
    open_edx_release = os.environ.get('OPENEDX_RELEASE_NAME')
    # Environment variable containing a string of comma separated Github usernames for testing
    test_open_edx_release = os.environ.get('GITHUB_USERS_CHERRY_PICK_MESSAGE_TEST')
    #test_open_edx_release = 'mduboseedx,nedbat,fakeuser'

    github = github_bp.session
    pr = pull_request
    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    is_internal_pr = is_internal_pull_request(pr)
    has_cl = has_internal_cover_letter(pr)
    is_beta = is_beta_tester_pull_request(pr)

    msg = "Processing {} PR #{} by {}...".format(repo, num, user)
    log_info(self.request, msg)

    if is_bot_pull_request(pr):
        # Bots never need OSPR attention.
        return None, False

    if is_internal_pr and not has_cl and is_beta:
        msg = "Adding cover letter to PR #{num} against {repo}".format(repo=repo, num=num)
        log_info(self.request, msg)
        coverletter = github_internal_cover_letter(pr)

        if coverletter is not None:
            comment = {
                "body": coverletter
            }
            url = "/repos/{repo}/issues/{num}/comments".format(repo=repo, num=num)

            comment_resp = github.post(url, json=comment)
            log_request_response(self.request, comment_resp)
            comment_resp.raise_for_status()

    if ignore_internal and is_internal_pr:
        # not an open source pull request, don't create an issue for it
        msg = "@{user} opened PR #{num} against {repo} (internal PR)".format(user=user, repo=repo, num=num)
        log_info(self.request, msg)
        # new release candidate for Open edX is available, ask internal PR if should be cherry picked
        do_cherry_pick_comment = False
        if open_edx_release:
            do_cherry_pick_comment = True
            release_message = open_edx_release
        elif test_open_edx_release:
            if user in test_open_edx_release.split(','):
                do_cherry_pick_comment = True
                release_message = "Test Release"
        if do_cherry_pick_comment:
            github_post_cherry_pick_comment(self, github, pr, release_message)
            return None, True
        return None, False

    if check_contractor and is_contractor_pull_request(pr):
        # have we already left a contractor comment?
        if has_contractor_comment(pr):
            msg = "Already left contractor comment for PR #{}".format(num)
            log_info(self.request, msg)
            return None, False

        # don't create a JIRA issue, but leave a comment
        comment = {
            "body": github_contractor_pr_comment(pr),
        }
        url = "/repos/{repo}/issues/{num}/comments".format(repo=repo, num=num)
        msg = "Posting contractor comment to PR #{}".format(num)
        log_info(self.request, msg)

        comment_resp = github.post(url, json=comment)
        log_request_response(self.request, comment_resp)
        comment_resp.raise_for_status()
        return None, True

    issue_key = get_jira_issue_key(pr)
    if issue_key:
        msg = "Already created {key} for PR #{num} against {repo}".format(
            key=issue_key,
            num=pr["number"],
            repo=pr["base"]["repo"]["full_name"],
        )
        log_info(self.request, msg)
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

    log_info(self.request, 'Creating new JIRA issue...')
    resp = jira_bp.session.post("/rest/api/2/issue", json=new_issue)
    log_request_response(self.request, resp)
    resp.raise_for_status()

    new_issue_body = resp.json()
    issue_key = new_issue_body["key"]
    new_issue["key"] = issue_key
    sentry_extra_context({"new_issue": new_issue})
    # add a comment to the Github pull request with a link to the JIRA issue
    comment = {
        "body": github_community_pr_comment(pr, new_issue_body, people),
    }
    url = "/repos/{repo}/issues/{num}/comments".format(repo=repo, num=pr["number"])
    log_info(self.request, 'Creating new GitHub comment with JIRA issue...')
    comment_resp = github.post(url, json=comment)
    log_request_response(self.request, comment_resp)
    comment_resp.raise_for_status()

    # Add the "Needs Triage" label to the PR
    issue_url = "/repos/{repo}/issues/{num}".format(repo=repo, num=pr["number"])
    labels = {'labels': ['needs triage', 'open-source-contribution']}
    log_info(self.request, 'Updating GitHub labels...')
    label_resp = github.patch(issue_url, data=json.dumps(labels))
    log_request_response(self.request, label_resp)
    label_resp.raise_for_status()

    msg = "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
        user=user,
        repo=repo,
        num=pr["number"],
        issue=issue_key,
    )
    log_info(self.request, msg)
    return issue_key, True


@celery.task(bind=True)
def pull_request_closed(self, pull_request):
    """
    A GitHub pull request has been merged or closed. Synchronize the JIRA issue
    to also be in the "merged" or "closed" state. Returns a boolean: True
    if the JIRA issue was correctly synchronized, False otherwise. (However,
    these booleans are ignored.)
    """
    jira = jira_bp.session
    pr = pull_request
    repo = pr["base"]["repo"]["full_name"]

    merged = pr["merged"]
    issue_key = get_jira_issue_key(pr)
    if not issue_key:
        msg = "Couldn't find JIRA issue for PR #{num} against {repo}".format(
            num=pr["number"], repo=repo,
        )
        log_info(self.request, msg)
        return "no JIRA issue :("
    sentry_extra_context({"jira_key": issue_key})

    # close the issue on JIRA
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    log_info(self.request, 'Closing the issue on JIRA...')
    transitions_resp = jira.get(transition_url)
    log_request_response(self.request, transitions_resp)
    if transitions_resp.status_code == requests.codes.not_found:
        # JIRA issue has been deleted
        return False
    transitions_resp.raise_for_status()

    transitions = transitions_resp.json()["transitions"]

    sentry_extra_context({"transitions": transitions})

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
        sentry_extra_context({"jira_issue": issue})
        current_status = issue["fields"]["status"]["name"]
        if current_status == transition_name:
            msg = "{key} is already in status {status}".format(
                key=issue_key, status=transition_name
            )
            log_info(self.request, msg)
            return False

        # nope, raise an error message
        fail_msg = (
            "{key} cannot be transitioned directly from status {curr_status} "
            "to status {new_status}. Valid status transitions are: {valid}".format(
                key=issue_key,
                new_status=transition_name,
                curr_status=current_status,
                valid=", ".join(t["to"]["name"] for t in transitions),
            )
        )
        log_error(self.request, fail_msg)
        raise Exception(fail_msg)

    log_info(self.request, 'Changing JIRA issue status...')
    transition_resp = jira.post(transition_url, json={
        "transition": {
            "id": transition_id,
        }
    })
    log_request_response(self.request, transition_resp)
    transition_resp.raise_for_status()
    msg = "PR #{num} against {repo} was {action}, moving {issue} to status {status}".format(
        num=pr["number"],
        repo=repo,
        action="merged" if merged else "closed",
        issue=issue_key,
        status="Merged" if merged else "Rejected",
    )
    log_info(self.request, msg)
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
        repo=pull_request["base"]["repo"]["full_name"],
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github_bp.session):
        # I only care about comments I made
        if comment["user"]["login"] != my_username:
            continue
        # search for the first occurrance of a JIRA ticket key in the comment body
        match = re.search(r"\b([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            return match.group(0)
    return None


def github_post_cherry_pick_comment(self, github, pull_request, open_edx_release):
    """
    Posts a cherry pick comment used for internal engineers during the window between
    an Open edX release candidate and the official release.

    """
    # fun_facts is a dictionary of trivia questions and answers
    fun_facts = get_fun_fact_file()
    question, answer = random.choice(list(fun_facts.items()))
    comment = {
        "body": github_internal_cherrypick_comment(pull_request, open_edx_release, question, answer),
    }
    url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"],
        num=pull_request["number"],
    )
    comment_resp = github.post(url, json=comment)
    log_request_response(self.request, comment_resp)
    comment_resp.raise_for_status()


def github_community_pr_comment(pull_request, jira_issue, people=None):
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * contain a link to our process documentation
    """
    github = github_bp.session
    people = people or get_people_file()
    people = {user.lower(): values for user, values in people.items()}
    pr_author = pull_request["user"]["login"].lower()
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    # does the user have a valid, signed contributor agreement?
    has_signed_agreement = (
        pr_author in people and
        people[pr_author].get("expires_on", date.max) > created_at.date()
    )
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

def github_internal_cherrypick_comment(pull_request, release_name, fun_fact_question, fun_fact_answer):
    """
    Formats a comment for internal authors during the window between a release candidate
    and the official release of Open edX. This asks if their PRs should be cherry picked
    onto the release candidate.

    * include the Open edX release name, e.g. Hawthorn, Ironwood, etc
    """
    return render_template("github_internal_cherrypick_comment.md.j2",
        user=pull_request["user"]["login"],
        open_edx_release_name=release_name,
        fun_fact_question=fun_fact_question,
        fun_fact_answer=fun_fact_answer,
    )


def has_contractor_comment(pull_request):
    """
    Given a pull request, this function returns a boolean indicating whether
    we have already left a comment on that pull request that suggests
    making an OSPR issue for the pull request.
    """
    me = github_whoami()
    my_username = me["login"]
    comment_url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"],
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github_bp.session):
        # I only care about comments I made
        if comment["user"]["login"] != my_username:
            continue
        magic_phrase = "It looks like you're a member of a company that does contract work for edX."
        if magic_phrase in comment["body"]:
            return True
    return False


def github_internal_cover_letter(pull_request):
    """
    For a newly-created pull request an edX internal developer,
    return a comment for the pull request that contains the cover letter.
    """
    # check for a `.pr_cover_letter.md.j2` in repo, use that if it exists
    coverletter_url = "https://raw.githubusercontent.com/{repo}/{branch}/.pr_cover_letter.md.j2".format(
        repo=pull_request["head"]["repo"]["full_name"],
        branch=pull_request["head"]["ref"],
    )
    coverletter_resp = github_bp.session.get(coverletter_url)
    ctx = {
        "user": pull_request["user"]["login"],
    }
    if coverletter_resp.ok:
        template_string = coverletter_resp.text
        return "\n\n".join([render_template_string(template_string, **ctx), COVERLETTER_MARKER])
    else:
        return None


def has_internal_cover_letter(pull_request):
    """
    Given a pull request, this function returns a boolean indicating whether
    the body has already been replaced with the cover letter template.
    """

    me = github_whoami()
    my_username = me["login"]
    comment_url = "/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"],
        num=pull_request["number"],
    )
    for comment in paginated_get(comment_url, session=github_bp.session):
        # I only care about comments I made
        if comment["user"]["login"] != my_username:
            continue

        body = comment["body"]
        if COVERLETTER_MARKER in body:
            return True
    return False


@memoize
def github_whoami():
    self_resp = github_bp.session.get("/user")
    self_resp.raise_for_status()
    return self_resp.json()
