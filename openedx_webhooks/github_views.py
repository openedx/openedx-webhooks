# coding=utf-8
"""
These are the views that process webhook events coming from Github.
"""

from __future__ import unicode_literals, print_function

import sys
import json
from collections import defaultdict

from flask import Blueprint, request, render_template, make_response, url_for, jsonify
from flask_dance.contrib.github import github
from celery import group

from openedx_webhooks import sentry
from openedx_webhooks.info import (
    get_people_file, get_repos_file,
    is_internal_pull_request, is_contractor_pull_request,
    )
from openedx_webhooks.utils import paginated_get, minimal_wsgi_environ
from openedx_webhooks.tasks.github import (
    pull_request_opened, pull_request_closed, rescan_repository
)

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
    sentry.client.extra_context({"event": event})

    if "pull_request" not in event and "hook" in event and "zen" in event:
        # this is a ping
        repo = event.get("repository", {}).get("full_name")
        print("ping from {repo}".format(repo=repo), file=sys.stderr)
        return "PONG"

    pr = event["pull_request"]
    repo = pr["base"]["repo"]["full_name"].decode('utf-8')
    action = event["action"]
    ignored_actions = set(("labeled", "synchronize"))
    if action in ignored_actions:
        msg = "Ignoring {action} events from github".format(action=action)
        return msg, 200

    if action == "opened":
        result = pull_request_opened.delay(pr, wsgi_environ=minimal_wsgi_environ())
    elif action == "closed":
        result = pull_request_closed.delay(pr)
    else:
        print(
            "Received {action} event on PR #{num} against {repo}, don't know how to handle it".format(
                action=event["action"],
                repo=pr["base"]["repo"]["full_name"].decode('utf-8'),
                num=pr["number"],
            ),
            file=sys.stderr
        )
        return "Don't know how to handle this.", 400

    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/rescan", methods=("GET", "POST"))
def rescan():
    """
    Used to pick up PRs that might not have tickets associated with them.
    """
    if request.method == "GET":
        # just render the form
        return render_template("github_rescan.html")
    repo = request.form.get("repo") or "edx/edx-platform"
    inline = request.form.get("inline", False)
    if repo == 'all' and inline:
        return "Don't be silly."

    if inline:
        return jsonify(rescan_repository(repo))

    if repo == 'all':
        repos = get_repos_file(session=github).keys()
        workflow = group(
            rescan_repository.s(repo, wsgi_environ=minimal_wsgi_environ())
            for repo in repos
        )
        group_result = workflow.delay()
        group_result.save()  # this is necessary for groups, for some reason
        status_url = url_for("tasks.group_status", group_id=group_result.id, _external=True)
    else:
        result = rescan_repository.delay(repo, wsgi_environ=minimal_wsgi_environ())
        status_url = url_for("tasks.status", task_id=result.id, _external=True)

    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/process_pr", methods=("GET", "POST"))
def process_pr():
    if request.method == "GET":
        return render_template("github_process_pr.html")
    repo = request.form.get("repo", "")
    if not repo:
        resp = jsonify({"error": "Pull request repo required"})
        resp.status_code = 400
        return resp
    num = request.form.get("number")
    if not num:
        resp = jsonify({"error": "Pull request number required"})
        resp.status_code = 400
        return resp
    num = int(num)
    pr_resp = github.get("/repos/{repo}/pulls/{num}".format(repo=repo, num=num))
    if not pr_resp.ok:
        resp = jsonify({"error": pr_resp.text})
        resp.status_code = 400
        return resp
    pr = pr_resp.json()
    if not pr["base"]["repo"]["permissions"]["admin"]:
        resp = jsonify({
            "error": "This bot does not have permissions for repo {}. Please manually make an OSPR ticket on JIRA.".format(repo)
        })
        resp.status_code = 400
        return resp

    result = pull_request_opened.delay(
        pr, ignore_internal=False, check_contractor=False,
        wsgi_environ=minimal_wsgi_environ(),
    )
    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/install", methods=("GET", "POST"))
def install():
    if request.method == "GET":
        return render_template("install.html")
    repo = request.form.get("repo", "")
    if repo:
        repos = (repo,)
    else:
        repos = get_repos_file(session=github).keys()

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
        sentry.client.extra_context({"repo": repo, "body": body})

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


@github_bp.route("/check_contributors", methods=("GET", "POST"))
def check_contributors():
    if request.method == "GET":
        return render_template("github_check_contributors.html")
    repo = request.form.get("repo", "")
    if repo:
        repos = (repo,)
    else:
        repos = get_repos_file(session=github).keys()

    people = get_people_file(session=github)
    people_lower = {username.lower() for username in people.keys()}

    missing_contributors = defaultdict(set)
    for repo in repos:
        sentry.client.extra_context({"repo": repo})
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
