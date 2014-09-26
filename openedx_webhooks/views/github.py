from __future__ import unicode_literals, print_function

import sys
import json
import re

import bugsnag
import requests
import yaml
from flask import request
from flask_dance.contrib.github import github
from flask_dance.contrib.jira import jira
from openedx_webhooks import app
from openedx_webhooks.utils import memoize
from openedx_webhooks.views.jira import get_jira_custom_fields


@app.route("/github/pr", methods=("POST",))
def github_pull_request():
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from Github: {data}".format(data=request.data))
    bugsnag_context = {"event": event}
    bugsnag.configure_request(meta_data=bugsnag_context)

    if "pull_request" not in event and "hook" in event and "zen" in event:
        # this is a ping
        repo = event.get("repository", {}).get("full_name")
        print("ping from {repo}".format(repo=repo), file=sys.stderr)
        return "PONG"

    pr = event["pull_request"]
    repo = pr["base"]["repo"]["full_name"]
    if event["action"] == "opened":
        return pr_opened(pr, bugsnag_context)
    if event["action"] == "closed":
        return pr_closed(pr, bugsnag_context)

    print(
        "Received {action} event on PR #{num} against {repo}, don't know how to handle it".format(
            action=event["action"], repo=pr["base"]["repo"]["full_name"],
            num=pr["number"]
        ),
        file=sys.stderr
    )
    return "Don't know how to handle this.", 400


@memoize
def get_people_file():
    people_resp = requests.get("https://raw.githubusercontent.com/edx/repo-tools/master/people.yaml")
    if not people_resp.ok:
        raise requests.exceptions.RequestException(people_resp.text)
    return yaml.safe_load(people_resp.text)


def pr_opened(pr, bugsnag_context=None):
    bugsnag_context = bugsnag_context or {}
    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    people = get_people_file()

    if user in people and people[user].get("institution", "") == "edX":
        # not an open source pull request, don't create an issue for it
        print(
            "@{user} opened PR #{num} against {repo} (internal PR)".format(
                user=user, repo=pr["base"]["repo"]["full_name"],
                num=pr["number"]
            ),
            file=sys.stderr
        )
        return "internal pull request"

    custom_fields = get_jira_custom_fields()

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
    bugsnag_context["new_issue"] = new_issue
    bugsnag.configure_request(meta_data=bugsnag_context)

    resp = jira.post("/rest/api/2/issue", data=json.dumps(new_issue))
    if not resp.ok:
        raise requests.exceptions.RequestException(resp.text)
    new_issue_body = resp.json()
    bugsnag_context["new_issue"]["key"] = new_issue_body["key"]
    bugsnag.configure_request(meta_data=bugsnag_context)
    # add a comment to the Github pull request with a link to the JIRA issue
    comment = {
        "body": github_pr_comment(pr, new_issue_body, people),
    }
    url = "/repos/{repo}/issues/{num}/comments".format(
        repo=repo, num=pr["number"],
    )
    comment_resp = github.post(url, data=json.dumps(comment))
    if not comment_resp.ok:
        raise requests.exceptions.RequestException(comment_resp.text)
    needs_triage_label = {
        "url": "https://api.github.com/repos/edx/edx-platform/labels/needs+triage",
        "name": "needs triage",
        "color": "e11d21"
    }

    label_resp = github.patch(issue_url, data=json.dumps({"labels": [needs_triage_label]}))
    if not label_resp.ok:
        raise requests.exceptions.RequestException(label_resp.text)

    print(
        "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
            user=user, repo=repo,
            num=pr["number"], issue=new_issue_body["key"]
        ),
        file=sys.stderr
    )
    return "created!"


def pr_closed(pr, bugsnag_context=None):
    bugsnag_context = bugsnag_context or {}
    repo = pr["base"]["repo"]["full_name"]

    merged = pr["merged"]
    issue_key = get_jira_issue_key(pr)
    if not issue_key:
        print(
            "Couldn't find JIRA issue for PR #{num} against {repo}".format(
                num=pr["number"], repo=repo,
            ),
            file=sys.stderr
        )
        return "no JIRA issue :("
    bugsnag_context["jira_key"] = issue_key
    bugsnag.configure_request(meta_data=bugsnag_context)

    # close the issue on JIRA
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    transitions_resp = jira.get(transition_url)
    if not transitions_resp.ok:
        raise requests.exceptions.RequestException(transitions_resp.text)

    transitions = transitions_resp.json()["transitions"]

    bugsnag_context["transitions"] = transitions
    bugsnag.configure_request(meta_data=bugsnag_context)

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
        if not issue_resp.ok:
            raise requests.exceptions.RequestException(issue_resp.text)
        issue = issue_resp.json()
        bugsnag_context["jira_issue"] = issue
        bugsnag.configure_request(meta_data=bugsnag_context)
        current_status = issue["fields"]["status"]["name"]
        if current_status == transition_name:
            msg = "{key} is already in status {status}".format(
                key=issue_key, status=transition_name
            )
            print(msg, file=sys.stderr)
            return "nothing to do!"

        # nope, raise an error message
        fail_msg = (
            "{key} cannot be transitioned directly from status {curr_status} "
            "to status {new_status}. Valid status transitions are: {valid}".format(
                key=issue_key, new_status=transition_name,
                curr_status=current_status,
                valid=", ".join(t["to"]["name"] for t in transitions),
            )
        )
        raise Exception(fail_msg)

    transition_resp = jira.post(transition_url, data=json.dumps({
        "transition": {
            "id": transition_id,
        }
    }))
    if not transition_resp.ok:
        raise requests.exceptions.RequestException(transition_resp.text)
    print(
        "PR #{num} against {repo} was {action}, moving {issue} to status {status}".format(
            num=pr["number"], repo=repo, action="merged" if merged else "closed",
            issue=issue_key, status="Merged" if merged else "Rejected",
        ),
        file=sys.stderr
    )
    return "closed!"


def get_jira_issue_key(pull_request):
    # who am I?
    self_resp = github.get("/user")
    rate_limit_info = {k: v for k, v in self_resp.headers.items() if "ratelimit" in k}
    print("Rate limits: {}".format(rate_limit_info), file=sys.stderr)
    if not self_resp.ok:
        raise requests.exceptions.RequestException(self_resp.text)
    my_username = self_resp.json()["login"]
    # get my first comment on this pull request
    comments_resp = github.get("/repos/{repo}/issues/{num}/comments".format(
        repo=pull_request["base"]["repo"]["full_name"], num=pull_request["number"],
    ))
    if not comments_resp.ok:
        raise requests.exceptions.RequestException(comments_resp.text)
    my_comments = [comment for comment in comments_resp.json()
                   if comment["user"]["login"] == my_username]
    if len(my_comments) < 1:
        return None
    # search for the first occurrance of a JIRA ticket key in the comment body
    match = re.search(r"\b([A-Z]{2,}-\d+)\b", my_comments[0]["body"])
    if match:
        return match.group(0)
    return None


def github_pr_comment(pull_request, jira_issue, people=None):
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * check for AUTHORS entry
    * contain a link to our process documentation
    """
    people = people or get_people_file()
    people = {user.lower(): values for user, values in people.items()}
    pr_author = pull_request["user"]["login"].lower()
    # does the user have a signed contributor agreement?
    has_signed_agreement = pr_author in people
    # is the user in the AUTHORS file?
    in_authors_file = False
    name = people.get(pr_author, {}).get("name", "")
    institution = people.get(pr_author, {}).get("institution", None)
    if name:
        authors_url = "https://raw.githubusercontent.com/{repo}/{branch}/AUTHORS".format(
            repo=pull_request["head"]["repo"]["full_name"], branch=pull_request["head"]["ref"],
        )
        authors_resp = github.get(authors_url)
        if authors_resp.ok:
            authors_content = authors_resp.text
            if name in authors_content:
                in_authors_file = True

    doc_url = "http://edx.readthedocs.org/projects/userdocs/en/latest/process/overview.html"
    issue_key = jira_issue["key"]
    issue_url = "https://openedx.atlassian.net/browse/{key}".format(key=issue_key)
    contributing_url = "https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst"
    agreement_url = "http://code.edx.org/individual-contributor-agreement.pdf"
    authors_url = "https://github.com/edx/edx-platform/blob/master/AUTHORS"
    comment = (
        "Thanks for the pull request, @{user}! I've created "
        "[{issue_key}]({issue_url}) to keep track of it in JIRA. "
        "JIRA is a place for product owners to prioritize feature reviews "
        "by the engineering development teams. Supporting information that is "
        "good to add there is anything that can help Product understand the "
        "context for the PR - supporting documentation, edx-code email threads, "
        "timeline information ('this must be merged by XX date', and why that is), "
        "partner information (this is for a course on edx.org, for example), etc. "
        "\n\nAll technical communication about the code itself will still be "
        "done via the Github pull request interface. "
        "As a reminder, [our process documentation is here]({doc_url})."
    ).format(
        user=pull_request["user"]["login"],
        issue_key=issue_key, issue_url=issue_url, doc_url=doc_url,
    )
    if not has_signed_agreement or not in_authors_file:
        todo = ""
        if not has_signed_agreement:
            todo += (
                "submitted a [signed contributor agreement]({agreement_url}) "
                "or indicated your institutional affiliation"
            ).format(
                agreement_url=agreement_url,
            )
        if not has_signed_agreement and not in_authors_file:
            todo += " and "
        if not in_authors_file:
            todo += "added yourself to the [AUTHORS]({authors_url}) file".format(
                authors_url=authors_url,
            )
        comment += ("\n\n"
            "We can't start reviewing your pull request until you've {todo}. "
            "Please see the [CONTRIBUTING]({contributing_url}) file for "
            "more information."
        ).format(todo=todo, contributing_url=contributing_url)
    return comment
