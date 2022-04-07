"""
These are the views that process webhook events coming from Github.
"""

import logging

from flask import current_app as app
from flask import (
    Blueprint, jsonify, render_template, request, url_for
)
from flask_dance.contrib.github import github

from openedx_webhooks.debug import is_debug, print_long_json
from openedx_webhooks.info import get_bot_username
from openedx_webhooks.lib.github.models import GithubWebHookRequestHeader
from openedx_webhooks.lib.rq import q
from openedx_webhooks.tasks.github import (
    pull_request_changed_task, rescan_repository, rescan_repository_task,
    rescan_organization_task,
)
from openedx_webhooks.utils import (
    is_valid_payload, minimal_wsgi_environ, sentry_extra_context, requires_auth
)

github_bp = Blueprint('github_views', __name__)
logger = logging.getLogger(__name__)


@github_bp.route('/hook-receiver', methods=('POST',))
def hook_receiver():
    """
    Process incoming GitHub webhook events.

    1.  Make sure the payload hashes to the proper signature. If not,
        reject the request with http status of 403.
    2.  Send a job to the queue with details of the event.
    3.  Respond with http status 202.

    Returns:
        A response, or Tuple[str, int]: Message payload and HTTP status code
    """
    headers = GithubWebHookRequestHeader(request.headers)

    # TODO: Once we adopt payload signature validation for all web hooks,
    #       add as decorator, or somehow into Blueprint
    secret = app.config.get('GITHUB_WEBHOOKS_SECRET')
    if not is_valid_payload(secret, headers.signature, request.data):
        msg = "Rejecting because signature doesn't match!"
        logging.info(msg)
        return msg, 403

    event = request.get_json()

    if "pull_request" not in event and "hook" in event and "zen" in event:
        # this is a ping
        repo = event.get("repository", {}).get("full_name")
        logger.info(f"ping from {repo}")
        return "PONG"

    action = event["action"]
    repo = event["repository"]["full_name"]
    who = event.get("sender", {}).get("login", "someone")
    keys = set(event.keys()) - {"action", "sender", "repository", "organization", "installation"}
    if is_debug(__name__):
        print_long_json("Incoming GitHub event", event)
    else:
        logger.info(f"Incoming GitHub event: {repo=!r}, {action=!r}, {who=!r}, keys: {' '.join(sorted(keys))}")

    # When the bot comments on a pull request, it causes an event, which gets
    # sent to webhooks, including us.  We don't have to do anything for our
    # own comment events.
    if who == get_bot_username() and "comment" in event:
        return "No thanks", 202

    # This can't authenticate with Jira now, so don't do it:
    # q.enqueue(
    #     'openedx_webhooks.github.dispatcher.dispatch',
    #     dict(request.headers),
    #     event,
    # )

    # There used to be two webhook endpoints.  This is the two of them
    # concatenated, just to combine them in the simplest possible way.
    # One of them is above this comment, the other is below.

    sentry_extra_context({"event": event})

    # This handler code only expected pull_request creation events, so ignore
    # other events.
    if "pull_request" not in event:
        return "Thank you", 202

    pr = event["pull_request"]
    pr_number = pr["number"]
    action = event["action"]
    pr["hook_action"] = event["action"]

    pr_activity = f"{repo} #{pr_number} {action!r}"
    if action in ["opened", "edited", "closed", "synchronize", "ready_for_review", "converted_to_draft", "reopened"]:
        logger.info(f"{pr_activity}, processing...")
        result = pull_request_changed_task.delay(pr, wsgi_environ=minimal_wsgi_environ())
    else:
        logger.info(f"{pr_activity}, ignoring...")
        return "Nothing for me to do", 200

    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    logger.info(f"Job status URL: {status_url}")

    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/rescan", methods=("GET",))
@requires_auth
def rescan_get():
    """
    Display a friendly HTML form for rescanning GitHub pull requests.
    """
    return render_template("github_rescan.html")


@github_bp.route("/rescan", methods=("POST",))
@requires_auth
def rescan():
    """
    Re-scan GitHub repositories to find pull requests that need OSPR issues
    on JIRA, and do not have them. If this method finds pull requests that are
    missing JIRA issues, it will automatically process those pull requests
    just as though the pull request was newly created.

    Note that this rescan functionality is the reason why
    :func:`~openedx_webhooks.tasks.github.pull_request_changed`
    must be idempotent. It could run many times over the same pull request.
    """
    repo = request.form.get("repo")
    inline = bool(request.form.get("inline", False))

    rescan_kwargs = dict(
        allpr=bool(request.form.get("allpr", False)),
        dry_run=bool(request.form.get("dry_run", False)),
        earliest=request.form.get("earliest", ""),
        latest=request.form.get("latest", ""),
    )

    if repo.startswith('all:'):
        if inline:
            return "Don't be silly."

        org = repo[4:]
        result = rescan_organization_task.delay(org, wsgi_environ=minimal_wsgi_environ(), **rescan_kwargs)
    elif inline:
        return jsonify(rescan_repository(repo, **rescan_kwargs))
    else:
        result = rescan_repository_task.delay(repo, wsgi_environ=minimal_wsgi_environ(), **rescan_kwargs)

    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/process_pr", methods=("GET",))
@requires_auth
def process_pr_get():
    """
    Display a friendly HTML form for processing or re-processing a pull request.
    """
    return render_template("github_process_pr.html")


@github_bp.route("/process_pr", methods=("POST",))
@requires_auth
def process_pr():
    """
    Process (or re-process) a pull request.
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

    pr = pr_resp.json()
    result = pull_request_changed_task.delay(pr, wsgi_environ=minimal_wsgi_environ())
    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


@github_bp.route("/generate_error", methods=("GET",))
@requires_auth
def generate_error():
    """
    Used to generate an error message to test error handling
    """
    raise Exception("Error from generate_error")
