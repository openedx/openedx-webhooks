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
    # TODO: We need to untangle this, there are **four** `return`s in this function!
    try:
        event = request.get_json()
    except ValueError:
        msg = "Invalid JSON from Github: {data}".format(data=request.data)
        print(msg, file=sys.stderr)
        raise ValueError(msg)
    sentry.client.extra_context({"event": event})

    if "pull_request" not in event and "hook" in event and "zen" in event:
        # this is a ping
        repo = event.get("repository", {}).get("full_name")
        print("ping from {repo}".format(repo=repo), file=sys.stderr)
        return "PONG"

    pr = event["pull_request"]
    PR_NUMBER = pr['number']
    repo = pr["base"]["repo"]["full_name"].decode('utf-8')
    action = event["action"]
    # `synchronize` action is when a new commit is made for the PR
    ignored_actions = set(("labeled", "synchronize"))
    if action in ignored_actions:
        msg = "Ignoring {action} events from github".format(action=action)
        print(msg, file=sys.stderr)
        return msg, 200

    _msg = "{}/pull/{} {}".format(repo, PR_NUMBER, action)
    if action == "opened":
        msg = "{}, processing…".format(_msg)
        print(msg, file=sys.stderr)
        result = pull_request_opened.delay(pr, wsgi_environ=minimal_wsgi_environ())
    elif action == "closed":
        msg = "{}, processing…".format(_msg)
        print(msg, file=sys.stderr)
        result = pull_request_closed.delay(pr)
    else:
        msg = "{}, rejecting with `400 Bad request`".format(_msg)
        print(msg, file=sys.stderr)
        # TODO: Is this really kosher? We should do no-op, not reject the request!
        return "Don't know how to handle this.", 400

    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    print("Job status URL: {}".format(status_url), file=sys.stderr)
    return resp


@github_bp.route("/rescan", methods=("GET",))
def rescan_get():
    """
    Display a friendly HTML form for rescanning GitHub pull requests.
    """
    return render_template("github_rescan.html")


@github_bp.route("/rescan", methods=("POST",))
def rescan():
    """
    Re-scan GitHub repositories to find pull requests that need OSPR issues
    on JIRA, and do not have them. If this method finds pull requests that are
    missing JIRA issues, it will automatically process those pull requests
    just as though the pull request was newly created.

    Note that this rescan functionality is the reason why
    :func:`~openedx_webhooks.tasks.github.pull_request_opened`
    must be idempotent. It could run many times over the same pull request.
    """
    repo = request.form.get("repo") or "edx/edx-platform"
    inline = request.form.get("inline", False)
    if repo == 'all' and inline:
        return "Don't be silly."

    if inline:
        return jsonify(rescan_repository(repo))

    if repo == 'all':
        repos = get_repos_file().keys()
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


@github_bp.route("/process_pr", methods=("GET",))
def process_pr_get():
    """
    Display a friendly HTML form for processing or re-processing a pull request.
    """
    return render_template("github_process_pr.html")


@github_bp.route("/process_pr", methods=("POST",))
def process_pr():
    """
    Process (or re-process) a pull request.

    Normally, when a pull request is opened, we check to see if the author is
    an edX employee, or a contractor working for edX. If so, we don't process
    the pull request normally -- either it is skipped, or we add an informative
    comment without making a JIRA ticket. Using this endpoint will skip those
    checks. We will make a JIRA ticket if one doesn't already exist, without
    checking to see if the author is special.
    """
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

    repo_resp = github.get("/repos/{repo}".format(repo=repo))
    repo_json = repo_resp.json()
    if not repo_json["permissions"]["admin"]:
        resp = jsonify({
            "error": "This bot does not have permissions for repo '{}'.\n\nPlease manually make an OSPR ticket on JIRA.".format(repo)
        })
        resp.status_code = 400
        return resp

    pr = pr_resp.json()
    result = pull_request_opened.delay(
        pr, ignore_internal=False, check_contractor=False,
        wsgi_environ=minimal_wsgi_environ(),
    )
    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/install", methods=("GET",))
def install_get():
    """
    Display a friendly HTML form for installing GitHub webhooks
    into a repo.
    """
    return render_template("install.html")


@github_bp.route("/install", methods=("POST",))
def install():
    """
    Install GitHub webhooks for a repo.
    """
    repo = request.form.get("repo", "")
    if repo:
        repos = [repo]
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


@github_bp.route("/check_contributors", methods=("GET",))
def check_contributors_get():
    """
    Display a friendly HTML form for identifying missing contributors in a
    repository.
    """
    return render_template("github_check_contributors.html")


@github_bp.route("/check_contributors", methods=("POST",))
def check_contributors():
    """
    Identify missing contributors: people who have commits in a repository,
    but who are not listed in the AUTHORS file.
    """
    repo = request.form.get("repo", "")
    if repo:
        repos = (repo,)
    else:
        repos = get_repos_file().keys()

    people = get_people_file()
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
