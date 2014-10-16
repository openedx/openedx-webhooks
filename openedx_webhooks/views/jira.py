from __future__ import unicode_literals, print_function

import sys
import json

import bugsnag
import requests
from urlobject import URLObject
from flask import request, render_template, make_response
from flask_dance.contrib.jira import jira
from flask_dance.contrib.github import github
from openedx_webhooks import app
from openedx_webhooks.utils import pop_dict_id, memoize, jira_paginated_get
from openedx_webhooks.oauth import jira_get


@memoize
def get_jira_custom_fields():
    """
    Return a name-to-id mapping for the custom fields on JIRA.
    """
    field_resp = jira.get("/rest/api/2/field")
    if not field_resp.ok:
        raise requests.exceptions.RequestException(field_resp.text)
    field_map = dict(pop_dict_id(f) for f in field_resp.json())
    return {
        value["name"]: id
        for id, value in field_map.items()
        if value["custom"]
    }

@app.route("/jira/rescan", methods=("GET", "POST"))
def jira_rescan():
    if request.method == "GET":
        # just render the form
        return render_template("jira_rescan.html")
    jql = request.form.get("jql") or 'status = "Needs Triage" ORDER BY key'
    bugsnag_context = {"jql": jql}
    bugsnag.configure_request(meta_data=bugsnag_context)
    issues = jira_paginated_get("/rest/api/2/search", "issues", jql=jql, session=jira)
    results = {}

    for issue in issues:
        issue_key = issue["key"].decode('utf-8')
        results[issue_key] = issue_opened(issue)

    resp = make_response(json.dumps(results), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp


# Maps JIRA status : Github label name
# Sometimes the existing labels are just strings, but other times they're the full on
# label dict with url, color, and name defined.
STATUS_LABEL_DICT = {
    'Needs Triage': [
        "needs triage",
        {u'name': u'needs triage', u'color': u'e11d21', u'url': u'https://api.github.com/repos/{pr_repo}/labels/needs+triage'}
    ],
    'Product Review': [
        "product review",
        {"name": "product review", "color": "5319e7", "url": "https://api.github.com/repos/{pr_repo}/labels/product+review"}
    ],
    'Community Manager Review': [
        "community manager review",
        {"name": "community manager review", "color": "207de5", "url": "https://api.github.com/repos/{pr_repo}/labels/community+manager+review"}
    ],
    'Awaiting Prioritization': [
        "awaiting prioritization",
        {"name": "awaiting prioritization", "color": "fad8c7", "url": "https://api.github.com/repos/{pr_repo}/labels/awaiting+prioritization"}
    ],
    'Engineering Review': [
        "engineering review",
        {"name": "engineering review", "color": "c7def8", "url": "https://api.github.com/repos/{pr_repo}/labels/engineering+review"}
    ],
    'Waiting on Author': [
        "waiting on author",
        {"name": "waiting on author", "color": "0052cc", "url": "https://api.github.com/repos/{pr_repo}/labels/waiting+on+author"}
    ],
}


@app.route("/jira/issue/created", methods=("POST",))
def jira_issue_created():
    """
    Received an "issue created" event from JIRA.
    https://developer.atlassian.com/display/JIRADEV/JIRA+Webhooks+Overview

    Ideally, this should be handled in a task queue, but we want to stay within
    Heroku's free plan, so it will be handled inline instead.
    (A worker dyno costs money.)
    """
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from JIRA: {data}".format(
            data=request.data.decode('utf-8')
        ))
    bugsnag_context = {"event": event}
    bugsnag.configure_request(meta_data=bugsnag_context)

    if app.debug:
        print(json.dumps(event), file=sys.stderr)

    if "issue" not in event:
        # It's rare, but we occasionally see junk data from JIRA. For example,
        # here's a real API request we've received on this handler:
        #   {"baseUrl": "https://openedx.atlassian.net",
        #    "key": "jira:1fec1026-b232-438f-adab-13b301059297",
        #    "newVersion": 64005, "oldVersion": 64003}
        # If we don't have an "issue" key, it's junk.
        return "What is this shit!?", 400

    return issue_opened(event["issue"], bugsnag_context)


def issue_opened(issue, bugsnag_context=None):
    bugsnag_context = bugsnag_context or {}
    bugsnag_context = {"issue": issue}
    bugsnag.configure_request(meta_data=bugsnag_context)

    issue_key = issue["key"].decode('utf-8')
    issue_status = issue["fields"]["status"]["name"].decode('utf-8')
    project = issue["fields"]["project"]["key"].decode('utf-8')
    if issue_status != "Needs Triage":
        print(
            "{key} has status {status}, does not need to be processed".format(
                key=issue_key, status=issue_status,
            ),
            file=sys.stderr,
        )
        return "issue does not need to be triaged"
    if project == "OSPR":
        # open source pull requests do not skip Needs Triage
        print(
            "{key} is an open source pull request, and does not need to be processed.".format(
                key=issue_key
            ),
            file=sys.stderr,
        )
        return "issue is OSPR"

    issue_url = URLObject(issue["self"])
    user_url = URLObject(issue["fields"]["creator"]["self"])
    user_url = user_url.set_query_param("expand", "groups")

    user_resp = jira_get(user_url)
    if not user_resp.ok:
        raise requests.exceptions.RequestException(user_resp.text)

    user = user_resp.json()
    groups = {g["name"]: g["self"] for g in user["groups"]["items"]}

    # skip "Needs Triage" if bug was created by edX employee
    transitioned = False
    if "edx-employees" in groups:
        transitions_url = issue_url.with_path(issue_url.path + "/transitions")
        transitions_resp = jira_get(transitions_url)
        if not transitions_resp.ok:
            raise requests.exceptions.RequestException(transitions_resp.text)
        transitions = {t["name"]: t["id"] for t in transitions_resp.json()["transitions"]}
        if "Open" in transitions:
            new_status = "Open"
        elif "Design Backlog" in transitions:
            new_status = "Design Backlog"
        else:
            raise ValueError("No valid transition! Possibilities are {}".format(transitions.keys()))

        body = {
            "transition": {
                "id": transitions[new_status],
            }
        }
        transition_resp = jira.post(transitions_url, json=body)
        if not transition_resp.ok:
            raise requests.exceptions.RequestException(transition_resp.text)
        transitioned = True

    try:
        name = issue["fields"]["creator"]["displayName"].decode('utf-8')
    except:
        bugsnag_context["name_type"] = type(issue["fields"]["creator"]["displayName"])
        bugsnag.configure_request(meta_data=bugsnag_context)
        raise

    # log to stderr
    action = "Transitioned to Open" if transitioned else "ignored"
    print(
        "{key} created by {name} ({username}), {action}".format(
            key=issue_key,
            name=name,
            username=issue["fields"]["creator"]["name"].decode('utf-8'),
            action="Transitioned to Open" if transitioned else "ignored",
        ),
        file=sys.stderr,
    )
    return action


@app.route("/jira/issue/updated", methods=("POST",))
def jira_issue_updated():
    """
    Received an "issue updated" event from JIRA.
    https://developer.atlassian.com/display/JIRADEV/JIRA+Webhooks+Overview
    """
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from JIRA: {data}".format(
            data=request.data.decode('utf-8')
        ))
    bugsnag_context = {"event": event}
    bugsnag.configure_request(meta_data=bugsnag_context)

    if app.debug:
        print(json.dumps(event), file=sys.stderr)

    issue_key = event["issue"]["key"].decode('utf-8')

    # is the issue an open source pull request?
    if event["issue"]["fields"]["project"]["key"] != "OSPR":
        # TODO: if the issue has just been moved from the OSPR project to a new project,
        # change the label to "engineering review". Need to figure out if we can tell that
        # the ticket has just moved projects.
        return "I don't care"

    # is there a changelog?
    changelog = event.get("changelog")
    if not changelog:
        # it was just someone adding a comment
        return "I don't care"

    # did the issue change status?
    status_changelog_items = [item for item in changelog["items"] if item["field"] == "status"]
    if len(status_changelog_items) == 0:
        return "I don't care"

    # construct Github API URL
    custom_fields = get_jira_custom_fields()
    pr_repo = event["issue"]["fields"].get(custom_fields["Repo"], "")
    pr_num = event["issue"]["fields"].get(custom_fields["PR Number"])
    if not pr_repo or not pr_num:
        fail_msg = '{key} is missing "Repo" or "PR Number" fields'.format(key=issue_key)
        raise Exception(fail_msg)
    pr_num = int(pr_num)

    pr_url = "/repos/{repo}/pulls/{num}".format(repo=pr_repo, num=pr_num)
    # Need to use the Issues API for label manipulation
    issue_url = "/repos/{repo}/issues/{num}".format(repo=pr_repo, num=pr_num)

    old_status = status_changelog_items[0]["fromString"]
    new_status = status_changelog_items[0]["toString"]

    if new_status == "Rejected":
        issue_resp = github.get(issue_url)
        if not issue_resp.ok:
            raise requests.exceptions.RequestException(issue_resp.text)
        issue = issue_resp.json()
        if issue["state"] == "closed":
            # nothing to do
            msg = "{key} was rejected, but PR #{num} was already closed".format(
                key=issue_key, num=pr_num
            )
            print(msg, file=sys.stderr)
            return msg

        # Comment on the PR to explain to look at JIRA
        username = issue["user"]["login"].decode('utf-8')
        comment = {"body": (
            "Hello @{username}: We are unable to continue with "
            "review of your submission at this time. Please see the "
            "associated JIRA ticket for more explanation.".format(username=username)
        )}
        comment_resp = github.post(issue_url + "/comments", json=comment)

        # close the pull request on Github
        close_resp = github.patch(pr_url, json={"state": "closed"})
        if not close_resp.ok or not comment_resp.ok:
            bugsnag_context['request_headers'] = close_resp.request.headers
            bugsnag_context['request_url'] = close_resp.request.url
            bugsnag_context['request_method'] = close_resp.request.method
            bugsnag.configure_request(meta_data=bugsnag_context)
            bug_text = ''
            if not close_resp.ok:
                bug_text += "Failed to close; " + close_resp.text
            if not comment_resp.ok:
                bug_text += "Failed to comment on the PR; " + comment_resp.text
            raise requests.exceptions.RequestException(bug_text)
        return "Closed PR #{num}".format(num=pr_num)

    elif new_status in STATUS_LABEL_DICT:
        # Get all the existing labels on this PR
        label_list = github.get(issue_url).json()["labels"]

        # Add in the label representing the new status - just add in the plain string label
        label_list.append(STATUS_LABEL_DICT[new_status][0])

        # remove the label representing the old status, if it exists
        if old_status in STATUS_LABEL_DICT:
            # Sometimes labels are strings ("needs triage") whereas other times they're dictionaries
            # with the label name, color, and url defined. Have not pinned down when or why this happens.
            for old_label in STATUS_LABEL_DICT[old_status]:
                try:
                    if isinstance(old_label, dict):
                        old_label["url"] = old_label["url"].format(pr_repo=pr_repo)
                    label_list.remove(old_label)
                except ValueError:
                    print("PR {num} does not have label {old_label} to remove".format(num=pr_num, old_label=old_label))
                    print("PR {num} only has labels {labels}".format(num=pr_num, labels=label_list))
                else:
                    print("PR {num}: Successfully removed label {old_label}".format(num=pr_num, old_label=old_label))
                    break

        # Post the new set of labels to github
        label_resp = github.patch(issue_url, json={"labels": label_list})
        if not label_resp.ok:
            raise requests.exceptions.RequestException(label_resp.text)
        return "Changed label of PR #{num} to {labels}".format(num=pr_num, labels=label_list)

    return "no change necessary"
