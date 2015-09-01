# coding=utf-8
"""
These are the views that process webhook events coming from Github.
"""

from __future__ import unicode_literals, print_function

import sys
import json
import re
from datetime import date
from collections import defaultdict

import bugsnag
from iso8601 import parse_date
from flask import Blueprint, request, render_template, make_response, url_for, jsonify
from flask_dance.contrib.github import github
from flask_dance.contrib.jira import jira

from openedx_webhooks.info import (
    get_people_file, get_repos_file,
    is_internal_pull_request, is_contractor_pull_request,
    )
from openedx_webhooks.utils import memoize, paginated_get
from openedx_webhooks.jira_views import get_jira_custom_fields

github_bp = Blueprint('github_views', __name__)


@github_bp.route("/pr", methods=("POST",))
def pull_request():
    """
    Process a `PullRequestEvent`_ from Github.

    .. _PullRequestEvent: https://developer.github.com/v3/activity/events/types/#pullrequestevent
    """
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
    repo = pr["base"]["repo"]["full_name"].decode('utf-8')
    if event["action"] == "opened":
        return pr_opened(pr, bugsnag_context)
    if event["action"] == "closed":
        return pr_closed(pr, bugsnag_context)
    if event["action"] == "labeled":
        return "Ignoring labeling events from github", 200
    if event["action"] == "synchronize":
        return "Ignoring synchronize events from github", 200

    print(
        "Received {action} event on PR #{num} against {repo}, don't know how to handle it".format(
            action=event["action"],
            repo=pr["base"]["repo"]["full_name"].decode('utf-8'),
            num=pr["number"],
        ),
        file=sys.stderr
    )
    return "Don't know how to handle this.", 400


def rescan_repo(repo):
    """
    rescans a single repo for new prs
    """
    bugsnag_context = {"repo": repo}
    bugsnag.configure_request(meta_data=bugsnag_context)
    url = "/repos/{repo}/pulls".format(repo=repo)
    created = {}

    for pull_request in paginated_get(url, session=github):
        bugsnag_context["pull_request"] = pull_request
        bugsnag.configure_request(meta_data=bugsnag_context)
        if not get_jira_issue_key(pull_request) and not is_internal_pull_request(pull_request):
            text = pr_opened(pull_request, bugsnag_context=bugsnag_context)
            if "created" in text:
                jira_key = text[8:]
                created[pull_request["number"]] = jira_key

    print(
        "Created {num} JIRA issues on repo {repo}. PRs are {prs}".format(
            num=len(created), repo=repo, prs=created.keys(),
        ),
        file=sys.stderr
    )
    return created


@github_bp.route("/rescan", methods=("GET", "POST"))
def rescan():
    """
    Used to pick up PRs that might not have tickets associated with them.
    """
    if request.method == "GET":
        # just render the form
        return render_template("github_rescan.html")
    repo = request.form.get("repo") or "edx/edx-platform"

    if repo.startswith('all'):
        repos = get_repos_file().keys()
        repos.remove("edx/edx-platform")
        num_repos = len(repos)

        if repo == 'all.1':
            repos = repos[:num_repos/2]
        elif repo == 'all.2':
            repos = repos[num_repos/2:]

        created = {}
        for repo in repos:
            created.update(rescan_repo(repo))
    else:
        created = rescan_repo(repo)

    resp = make_response(json.dumps(created), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp


@github_bp.route("/process_pr", methods=("GET", "POST"))
def process_pr():
    if request.method == "GET":
        return render_template("github_process_pr.html")
    repo = request.form.get("repo", "")
    if not repo:
        resp = jsonify({"error": "repo required"})
        resp.status_code = 400
        return resp
    num = request.form.get("number")
    if not num:
        resp = jsonify({"error": "num required"})
        resp.status_code = 400
        return resp
    num = int(num)
    pr_resp = github.get("/repos/{repo}/pulls/{num}".format(repo=repo, num=num))
    if not pr_resp.ok:
        resp = jsonify({"error": pr_resp.text})
        resp.status_code = 400
        return resp
    return pr_opened(pr_resp.json(), ignore_internal=False, check_contractor=False)


@github_bp.route("/install", methods=("GET", "POST"))
def install():
    if request.method == "GET":
        return render_template("install.html")
    repo = request.form.get("repo", "")
    if repo:
        repos = (repo,)
    else:
        repos = get_repos_file().keys()

    api_url = url_for("github_views.pull_request", _external=True)
    success = []
    failed = []
    for repo in repos:
        url = "/repos/{repo}/hooks".format(repo=repo)
        body = {
            "name": "web",
            "events": ["pull_request"],
            "config": {
                "url": api_url,
                "content_type": "json",
            }
        }
        bugsnag_context = {"repo": repo, "body": body}
        bugsnag.configure_request(meta_data=bugsnag_context)

        hook_resp = github.post(url, json=body)
        if hook_resp.ok:
            success.append(repo)
        else:
            failed.append((repo, hook_resp.text))

    if failed:
        resp = make_response(json.dumps(failed), 502)
    else:
        resp = make_response(json.dumps(success), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp


@memoize
def github_whoami():
    self_resp = github.get("/user")
    rate_limit_info = {k: v for k, v in self_resp.headers.items() if "ratelimit" in k}
    print("Rate limits: {}".format(rate_limit_info), file=sys.stderr)
    self_resp.raise_for_status()
    return self_resp.json()


def pr_opened(pr, ignore_internal=True, check_contractor=True, bugsnag_context=None):
    bugsnag_context = bugsnag_context or {}
    user = pr["user"]["login"].decode('utf-8')
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    if ignore_internal and is_internal_pull_request(pr):
        # not an open source pull request, don't create an issue for it
        print(
            "@{user} opened PR #{num} against {repo} (internal PR)".format(
                user=user, repo=repo, num=num,
            ),
            file=sys.stderr
        )
        return "internal pull request"

    if check_contractor and is_contractor_pull_request(pr):
        # don't create a JIRA issue, but leave a comment
        comment = {
            "body": github_contractor_pr_comment(pr),
        }
        url = "/repos/{repo}/issues/{num}/comments".format(
            repo=repo, num=num,
        )
        comment_resp = github.post(url, json=comment)
        comment_resp.raise_for_status()
        return "contractor pull request"

    issue_key = get_jira_issue_key(pr)
    if issue_key:
        msg = "Already created {key} for PR #{num} against {repo}".format(
            key=issue_key,
            num=pr["number"],
            repo=pr["base"]["repo"]["full_name"],
        )
        print(msg, file=sys.stderr)
        return msg

    repo = pr["base"]["repo"]["full_name"].decode('utf-8')
    people = get_people_file()
    custom_fields = get_jira_custom_fields()

    if user in people:
        user_name = people[user].get("name", "")
    else:
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

    resp = jira.post("/rest/api/2/issue", json=new_issue)
    resp.raise_for_status()
    new_issue_body = resp.json()
    issue_key = new_issue_body["key"].decode('utf-8')
    bugsnag_context["new_issue"]["key"] = issue_key
    bugsnag.configure_request(meta_data=bugsnag_context)
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

    print(
        "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
            user=user, repo=repo,
            num=pr["number"], issue=issue_key,
        ),
        file=sys.stderr
    )
    return "created {key}".format(key=issue_key)


def pr_closed(pr, bugsnag_context=None):
    bugsnag_context = bugsnag_context or {}
    repo = pr["base"]["repo"]["full_name"].decode('utf-8')

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
    transitions_resp.raise_for_status()

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
        issue_resp.raise_for_status()
        issue = issue_resp.json()
        bugsnag_context["jira_issue"] = issue
        bugsnag.configure_request(meta_data=bugsnag_context)
        current_status = issue["fields"]["status"]["name"].decode("utf-8")
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
    print(
        "PR #{num} against {repo} was {action}, moving {issue} to status {status}".format(
            num=pr["number"],
            repo=repo,
            action="merged" if merged else "closed",
            issue=issue_key,
            status="Merged" if merged else "Rejected",
        ),
        file=sys.stderr
    )
    return "closed!"


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


@github_bp.route("/check_contributors", methods=("GET", "POST"))
def check_contributors():
    if request.method == "GET":
        return render_template("github_check_contributors.html")
    repo = request.form.get("repo", "")
    if repo:
        repos = (repo,)
    else:
        repos = get_repos_file().keys()

    people = get_people_file()
    people_lower = {username.lower() for username in people.keys()}

    missing_contributors = defaultdict(set)
    for repo in repos:
        bugsnag_context = {"repo": repo}
        bugsnag.configure_request(meta_data=bugsnag_context)
        contributors_url = "/repos/{repo}/contributors".format(repo=repo)
        contributors = paginated_get(contributors_url, session=github)
        for contributor in contributors:
            if contributor["login"].lower() not in people_lower:
                missing_contributors[repo].add(contributor["login"])

    # convert sets to lists, so jsonify can handle them
    output = {
        repo: list(contributors)
        for repo, contributors in missing_contributors.items()
    }
    return jsonify(output)
