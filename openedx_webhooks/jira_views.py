"""
These are the views that process webhook events coming from JIRA.
"""

import json
import re
import sys

from flask import (
    Blueprint, current_app, jsonify, make_response, render_template, request,
    url_for
)
from flask_dance.contrib.github import github
from flask_dance.contrib.jira import jira
from urlobject import URLObject

from openedx_webhooks.oauth import jira_get
from openedx_webhooks.tasks.jira import rescan_users as rescan_user_task
from openedx_webhooks.utils import (
    jira_paginated_get, memoize, pop_dict_id, to_unicode, sentry_extra_context
)

jira_bp = Blueprint('jira_views', __name__)


@memoize
def get_jira_custom_fields(session=None):
    """
    Return a name-to-id mapping for the custom fields on JIRA.
    """
    session = session or jira
    field_resp = session.get("/rest/api/2/field")
    field_resp.raise_for_status()
    field_map = dict(pop_dict_id(f) for f in field_resp.json())
    return {
        value["name"]: id
        for id, value in field_map.items()
        if value["custom"]
    }


@memoize
def get_jira_issue(key):
    return jira_get("/rest/api/2/issue/{key}".format(key=key))


@jira_bp.route("/issue/rescan", methods=("GET",))
def rescan_issues_get():
    """
    Display a friendly HTML form for re-scanning JIRA issues.
    """
    return render_template("jira_rescan_issues.html")


@jira_bp.route("/issue/rescan", methods=("POST",))
def rescan_issues():
    """
    Re-scan all JIRA issues that are in the "Needs Triage" state. If any were
    created by edX employees, they will be automatically transitioned to an
    "Open" state.

    Normally, issues are processed automatically. However, sometimes an issue
    is skipped accidentally, either due to a network hiccup, a bug in JIRA,
    or this bot going offline. This endpoint is used to clean up after these
    kind of problems.
    """
    jql = request.form.get("jql") or 'status = "Needs Triage" ORDER BY key'
    sentry_extra_context({"jql": jql})
    issues = jira_paginated_get(
        "/rest/api/2/search", jql=jql, obj_name="issues", session=jira,
    )
    results = {}

    for issue in issues:
        issue_key = to_unicode(issue["key"])
        results[issue_key] = issue_opened(issue)

    resp = make_response(json.dumps(results), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp


@jira_bp.route("/issue/created", methods=("POST",))
def issue_created():
    """
    Received an "issue created" event from JIRA. See `JIRA's webhook docs`_.

    .. _JIRA's webhook docs: https://developer.atlassian.com/display/JIRADEV/JIRA+Webhooks+Overview
    """
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from JIRA: {data}".format(data=request.data))
    sentry_extra_context({"event": event})

    if current_app.debug:
        print(json.dumps(event), file=sys.stderr)

    if "issue" not in event:
        # It's rare, but we occasionally see junk data from JIRA. For example,
        # here's a real API request we've received on this handler:
        #   {"baseUrl": "https://openedx.atlassian.net",
        #    "key": "jira:1fec1026-b232-438f-adab-13b301059297",
        #    "newVersion": 64005, "oldVersion": 64003}
        # If we don't have an "issue" key, it's junk.
        return "What is this shit!?", 400

    return issue_opened(event["issue"])


def should_transition(issue):
    """
    Return a boolean indicating if the given issue should be transitioned
    automatically from "Needs Triage" to an open status.
    """
    issue_key = to_unicode(issue["key"])
    issue_status = to_unicode(issue["fields"]["status"]["name"])
    project_key = to_unicode(issue["fields"]["project"]["key"])
    if issue_status != "Needs Triage":
        print(
            "{key} has status {status}, does not need to be processed".format(
                key=issue_key, status=issue_status,
            ),
            file=sys.stderr,
        )
        return False

    # Open source pull requests do not skip Needs Triage.
    # However, if someone creates a subtask on an OSPR issue, that subtasks
    # might skip Needs Triage (it just follows the rest of the logic in this
    # function.)
    is_subtask = issue["fields"]["issuetype"]["subtask"]
    if project_key == "OSPR" and not is_subtask:
        print(
            "{key} is an open source pull request, and does not need to be processed.".format(
                key=issue_key
            ),
            file=sys.stderr,
        )
        return False

    user_url = URLObject(issue["fields"]["creator"]["self"])
    user_url = user_url.set_query_param("expand", "groups")

    user_resp = jira_get(user_url)
    user_resp.raise_for_status()

    user = user_resp.json()
    user_group_map = {g["name"]: g["self"] for g in user["groups"]["items"]}
    user_groups = set(user_group_map)

    exempt_groups = {
        # group name: set of projects that they can create non-triage issues
        "edx-employees": {"ALL"},
        "opencraft": {"SOL"},
    }
    for user_group in user_groups:
        if user_group not in exempt_groups:
            continue
        exempt_projects = exempt_groups[user_group]
        if "ALL" in exempt_projects:
            return True
        if project_key in exempt_projects:
            return True

    return False


def issue_opened(issue):
    sentry_extra_context({"issue": issue})

    issue_key = to_unicode(issue["key"])
    issue_url = URLObject(issue["self"])

    transitioned = False
    if should_transition(issue):
        # In JIRA, a "transition" is how an issue changes from one status
        # to another, like going from "Open" to "In Progress". The workflow
        # defines what transitions are allowed, and this API will tell us
        # what transitions are currently allowed by the workflow.
        # Ref: https://docs.atlassian.com/jira/REST/ondemand/#d2e4954
        transitions_url = issue_url.with_path(issue_url.path + "/transitions")
        transitions_resp = jira_get(transitions_url)
        transitions_resp.raise_for_status()
        # This transforms the API response into a simple mapping from the
        # name of the transition (like "In Progress") to the ID of the transition.
        # Note that a transition may not have the same name as the state that it
        # goes to, so a transition to go from "Open" to "In Progress" may be
        # named something like "Start Work".
        transitions = {t["name"]: t["id"] for t in transitions_resp.json()["transitions"]}

        # We attempt to transition the issue into the "Open" state for the given project
        # (some projects use a different name), so look for a transition with the right name
        new_status = None
        action = None
        for state_name in ["Open", "Design Backlog", "To Do"]:
            if state_name in transitions:
                new_status = state_name
                action = "Transitioned to '{}'".format(state_name)

        if not new_status:
            # If it's an OSPR subtask (used by teams to manage reviews), transition to team backlog
            if to_unicode(issue["fields"]["project"]["key"]) == "OSPR" and issue["fields"]["issuetype"]["subtask"]:
                new_status = "To Backlog"
                action = "Transitioned to 'To Backlog'"
            else:
                raise ValueError("No valid transition! Possibilities are {}".format(transitions.keys()))

        # This creates a new API request to tell JIRA to move the issue from
        # one status to another using the specified transition. We have to
        # tell JIRA the transition ID, so we use that mapping we set up earlier.
        body = {
            "transition": {
                "id": transitions[new_status],
            }
        }
        transition_resp = jira.post(transitions_url, json=body)
        transition_resp.raise_for_status()
        transitioned = True

    # log to stderr
    if transitioned and not action:
        action = "Transitioned to Open"
    else:
        action = "ignored"
    print(
        "{key} created by {name} ({username}), {action}".format(
            key=issue_key,
            name=to_unicode(issue["fields"]["creator"]["displayName"]),
            username=to_unicode(issue["fields"]["creator"]["name"]),
            action="Transitioned to Open" if transitioned else "ignored",
        ),
        file=sys.stderr,
    )
    return action


def github_pr_repo(issue):
    custom_fields = get_jira_custom_fields()
    pr_repo = issue["fields"].get(custom_fields["Repo"])
    parent_ref = parent_ref = issue["fields"].get("parent")
    if not pr_repo and parent_ref:
        parent_resp = get_jira_issue(parent_ref["key"])
        parent_resp.raise_for_status()
        parent = parent_resp.json()
        pr_repo = parent["fields"].get(custom_fields["Repo"])
    return pr_repo


def github_pr_num(issue):
    custom_fields = get_jira_custom_fields()
    pr_num = issue["fields"].get(custom_fields["PR Number"])
    parent_ref = parent_ref = issue["fields"].get("parent")
    if not pr_num and parent_ref:
        parent_resp = get_jira_issue(parent_ref["key"])
        parent_resp.raise_for_status()
        parent = parent_resp.json()
        pr_num = parent["fields"].get(custom_fields["PR Number"])
    try:
        return int(pr_num)
    except:
        return None


def github_pr_url(issue):
    """
    Return the pull request URL for the given JIRA issue,
    or raise an exception if they can't be determined.
    """
    pr_repo = github_pr_repo(issue)
    pr_num = github_pr_num(issue)
    if not pr_repo or not pr_num:
        issue_key = to_unicode(issue["key"])
        fail_msg = '{key} is missing "Repo" or "PR Number" fields'.format(key=issue_key)
        raise Exception(fail_msg)
    return "/repos/{repo}/pulls/{num}".format(repo=pr_repo, num=pr_num)


@jira_bp.route("/issue/updated", methods=("POST",))
def issue_updated():
    """
    Received an "issue updated" event from JIRA. See `JIRA's webhook docs`_.

    .. _JIRA's webhook docs: https://developer.atlassian.com/display/JIRADEV/JIRA+Webhooks+Overview
    """
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from JIRA: {data}".format(data=request.data))
    sentry_extra_context({"event": event})

    if current_app.debug:
        print(json.dumps(event), file=sys.stderr)

    if "issue" not in event:
        # It's rare, but we occasionally see junk data from JIRA. For example,
        # here's a real API request we've received on this handler:
        #   {"baseUrl": "https://openedx.atlassian.net",
        #    "key": "jira:1fec1026-b232-438f-adab-13b301059297",
        #    "newVersion": 64005, "oldVersion": 64003}
        # If we don't have an "issue" key, it's junk.
        return "What is this shit!?", 400

    # is this a comment?
    comment = event.get("comment")
    if comment:
        return jira_issue_comment_added(event["issue"], comment)

    # is the issue an open source pull request?
    if event["issue"]["fields"]["project"]["key"] != "OSPR":
        return "I don't care"

    # is it a pull request against an edX repo?
    pr_repo = github_pr_repo(event["issue"])
    if pr_repo and not pr_repo.startswith("edx/"):
        return "ignoring PR on external repo"

    # we don't care about OSPR subtasks
    if event["issue"]["fields"]["issuetype"]["subtask"]:
        return "ignoring subtasks"

    # don't care about feature proposals
    if event["issue"]["fields"]["issuetype"]["name"] == "Feature Proposal":
        return "ignoring feature propsals"

    # is there a changelog?
    changelog = event.get("changelog")
    if not changelog:
        # it was just someone adding a comment
        return "I don't care"

    # did the issue change status?
    status_changelog_items = [item for item in changelog["items"] if item["field"] == "status"]
    if len(status_changelog_items) == 0:
        return "I don't care"

    if not pr_repo:
        issue_key = to_unicode(event["issue"]["key"])
        fail_msg = '{key} is missing "Repo" field'.format(key=issue_key)
        fail_msg += ' {0}'.format(event["issue"]["fields"]["issuetype"])
        raise Exception(fail_msg)
    repo_labels_resp = github.get("/repos/{repo}/labels".format(repo=pr_repo))
    repo_labels_resp.raise_for_status()
    # map of label name to label URL
    repo_labels = {l["name"]: l["url"] for l in repo_labels_resp.json()}
    # map of label name lowercased to label name in the case that it is on Github
    repo_labels_lower = {name.lower(): name for name in repo_labels}

    old_status = status_changelog_items[0]["fromString"]
    new_status = status_changelog_items[0]["toString"]

    changes = []
    if new_status == "Rejected":
        change = jira_issue_rejected(event["issue"])
        changes.append(change)

    elif 'blocked' in new_status.lower():
        print("New status is: {}".format(new_status))
        print("repo_labels_lower: {}".format(repo_labels_lower))

    if new_status.lower() in repo_labels_lower:
        change = jira_issue_status_changed(event["issue"], event["changelog"])
        changes.append(change)

    if changes:
        return "\n".join(changes)
    else:
        return "no change necessary"


def jira_issue_rejected(issue):
    issue_key = to_unicode(issue["key"])

    pr_num = github_pr_num(issue)
    pr_url = github_pr_url(issue)
    issue_url = pr_url.replace("pulls", "issues")

    gh_issue_resp = github.get(issue_url)
    gh_issue_resp.raise_for_status()
    gh_issue = gh_issue_resp.json()
    sentry_extra_context({"github_issue": gh_issue})
    if gh_issue["state"] == "closed":
        # nothing to do
        msg = "{key} was rejected, but PR #{num} was already closed".format(
            key=issue_key, num=pr_num
        )
        print(msg, file=sys.stderr)
        return msg

    # Comment on the PR to explain to look at JIRA
    username = to_unicode(gh_issue["user"]["login"])
    comment = {"body": (
        "Hello @{username}: We are unable to continue with "
        "review of your submission at this time. Please see the "
        "associated JIRA ticket for more explanation.".format(username=username)
    )}
    comment_resp = github.post(issue_url + "/comments", json=comment)
    comment_resp.raise_for_status()

    # close the pull request on Github
    close_resp = github.patch(pr_url, json={"state": "closed"})
    close_resp.raise_for_status()

    return "Closed PR #{num}".format(num=pr_num)


def jira_issue_status_changed(issue, changelog):
    pr_num = github_pr_num(issue)
    pr_repo = github_pr_repo(issue)
    pr_url = github_pr_url(issue)
    issue_url = pr_url.replace("pulls", "issues")

    status_changelog = [item for item in changelog["items"] if item["field"] == "status"][0]
    old_status = status_changelog["fromString"]
    new_status = status_changelog["toString"]

    # get github issue
    gh_issue_resp = github.get(issue_url)
    gh_issue_resp.raise_for_status()
    gh_issue = gh_issue_resp.json()

    # get repo labels
    repo_labels_resp = github.get("/repos/{repo}/labels".format(repo=pr_repo))
    repo_labels_resp.raise_for_status()
    # map of label name to label URL
    repo_labels = {l["name"]: l["url"] for l in repo_labels_resp.json()}
    # map of label name lowercased to label name in the case that it is on Github
    repo_labels_lower = {name.lower(): name for name in repo_labels}

    # Get all the existing labels on this PR
    pr_labels = [label["name"] for label in gh_issue["labels"]]
    print("old labels: {}".format(pr_labels), file=sys.stderr)

    # remove old status label
    old_status_label = repo_labels_lower.get(old_status.lower(), old_status)
    print("old status label: {}".format(old_status_label), file=sys.stderr)
    if old_status_label in pr_labels:
        pr_labels.remove(old_status_label)
    # add new status label
    new_status_label = repo_labels_lower[new_status.lower()]
    print("new status label: {}".format(new_status_label), file=sys.stderr)
    if new_status_label not in pr_labels:
        pr_labels.append(new_status_label)

    print("new labels: {}".format(pr_labels), file=sys.stderr)

    # Update labels on github
    update_label_resp = github.patch(issue_url, json={"labels": pr_labels})
    update_label_resp.raise_for_status()
    return "Changed labels of PR #{num} to {labels}".format(num=pr_num, labels=pr_labels)


def jira_issue_comment_added(issue, comment):
    issue_key = to_unicode(issue["key"])

    # we want to parse comments on Course Launch issues to fill out the cert report
    # see https://openedx.atlassian.net/browse/TOOLS-19
    if issue["fields"]["project"]["key"] != "COR":
        return "I don't care"

    lines = comment['body'].splitlines()
    if len(lines) < 2:
        return "I don't care"

    # the comment that we want should have precisely these headings in this order
    headings = [
        "course ID", "audit", "audit_enrolled", "downloadable",
        "enrolled_current", "enrolled_total", "honor", "honor_enrolled",
        "notpassing", "verified", "verified_enrolled",
    ]
    HEADING_RE = re.compile(r"\w+".join(headings))
    TIMESTAMP_RE = re.compile(r"^\d\d:\d\d:\d\d ")

    # test header/content pairs
    values = None
    for header, content in zip(lines, lines[1:]):
        # if both header and content start with a timestamp, chop it off
        if TIMESTAMP_RE.match(header) and TIMESTAMP_RE.match(content):
            header = header[9:]
            content = content[9:]

        # does this have the headings we're expecting?
        if not HEADING_RE.search(header):
            # this is not the header, move on
            continue

        # this must be it! grab the values
        values = content.split()

        # check that we have the right number
        if len(values) == len(headings):
            # we got it!
            break
        else:
            # aww, we were so close...
            values = None

    if not values:
        return "Didn't find header/content pair"

    custom_fields = get_jira_custom_fields()
    fields = {
        custom_fields["Course ID"]: values[0],
        custom_fields["?"]: int(values[1]), # "audit"
        custom_fields["Enrolled Audit"]: int(values[2]),
        custom_fields["?"]: int(values[3]), # "downloadable"
        custom_fields["Current Enrolled"]: int(values[4]),
        custom_fields["Total Enrolled"]: int(values[5]),
        custom_fields["?"]: int(values[6]), # "honor"
        custom_fields["Enrolled Honor Code"]: int(values[7]),
        custom_fields["Not Passing"]: int(values[8]),
        custom_fields["?"]: int(values[9]), # "verified"
        custom_fields["Enrolled Verified"]: int(values[10]),
    }
    issue_url = issue["self"]
    update_resp = jira.put(issue_url, json={"fields": fields})
    update_resp.raise_for_status()
    return "{key} cert info updated".format(key=issue_key)


# a mapping of group name to email domain
# TODO: ??? re duplicate dict keys
domain_groups = {
    "partner-ubc": "@cs.ubc.ca",
    "partner-ubc": "@ubc.ca",
}


@jira_bp.route("/user/rescan", methods=("GET",))
def rescan_users_get():
    """
    Display a friendly HTML form for rescanning JIRA users.
    """
    return render_template("jira_rescan_users.html", domain_groups=domain_groups)


@jira_bp.route("/user/rescan", methods=("POST",))
def rescan_users():
    """
    This task goes through all users on JIRA and ensures that they are assigned
    to the correct group based on the user's email address. It's meant to be
    run regularly: once an hour or so.
    """
    requested_group = request.form.get("group")
    if requested_group:
        if requested_group not in domain_groups:
            resp = jsonify({"error": "Not found", "groups": domain_groups.keys()})
            resp.status_code = 404
            return resp
        requested_groups = {requested_group: domain_groups[requested_group]}
    else:
        requested_groups = domain_groups

    result = rescan_user_task.delay(requested_groups)
    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp
