"""
These are the views that process webhook events coming from Github.
"""

import logging

from celery import group
from flask import current_app as app
from flask import (
    Blueprint, jsonify, render_template, request, url_for
)
from flask_dance.contrib.github import github

from openedx_webhooks.debug import is_debug, print_long_json
from openedx_webhooks.lib.github.models import GithubWebHookRequestHeader
from openedx_webhooks.lib.rq import q
from openedx_webhooks.tasks.github import pull_request_changed_task, rescan_repository
from openedx_webhooks.utils import (
    is_valid_payload, minimal_wsgi_environ, paginated_get,
    sentry_extra_context
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
    action = event["action"]
    repo = event["repository"]["full_name"]
    keys = set(event.keys()) - {"action", "sender", "repository", "organization", "installation"}
    if is_debug(__name__):
        print_long_json("Incoming GitHub event", event)
    else:
        logger.info(f"Incoming GitHub event: {repo=!r}, {action=!r}, keys: {' '.join(sorted(keys))}")

    q.enqueue(
        'openedx_webhooks.github.dispatcher.dispatch',
        dict(request.headers),
        event,
    )

    # There used to be two webhook endpoints.  This is the two of them
    # concatenated, just to combine them in the simplest possible way.
    # One of them is above this comment, the other is below.

    sentry_extra_context({"event": event})

    if "pull_request" not in event and "hook" in event and "zen" in event:
        # this is a ping
        repo = event.get("repository", {}).get("full_name")
        logger.info(f"ping from {repo}")
        return "PONG"

    # This handler code only expected pull_request creation events, so ignore
    # other events.
    if "pull_request" not in event:
        return "Thank you", 202

    pr = event["pull_request"]
    pr_number = pr["number"]
    action = event["action"]

    pr_activity = f"{repo} #{pr_number} {action!r}"
    if action in ["opened", "edited", "closed", "synchronize", "ready_for_review", "converted_to_draft"]:
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
    :func:`~openedx_webhooks.tasks.github.pull_request_changed`
    must be idempotent. It could run many times over the same pull request.
    """
    repo = request.form.get("repo") or "edx/edx-platform"
    inline = request.form.get("inline", False)
    if repo == 'all' and inline:
        return "Don't be silly."

    if inline:
        # Calling a celery task directly: the args don't match the def.
        return jsonify(rescan_repository(repo))     # pylint: disable=no-value-for-parameter

    if repo.startswith('all:'):
        org = repo[4:]
        org_url = "https://api.github.com/orgs/{org}/repos".format(org=org)
        repo_names = [repo_name['full_name'] for repo_name in paginated_get(org_url)]
        workflow = group(
            rescan_repository.s(repository, wsgi_environ=minimal_wsgi_environ())
            for repository in repo_names
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
            "error": (
                "This bot does not have permissions for repo {!r}.\n\n".format(repo) +
                "Please manually make an OSPR ticket on JIRA."
            )
        })
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
def generate_error():
    """
    Used to generate an error message to test error handling
    """
    raise Exception("Error from generate_error")
