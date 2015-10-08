import sys
import logging
from celery.utils.log import get_task_logger
from flask import Blueprint, jsonify
from openedx_webhooks import celery
from openedx_webhooks.oauth import github_bp, jira_bp

# set up logging
logger = get_task_logger(__name__)
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s: %(message)s [%(name)s]')
stderr_handler.setFormatter(formatter)
logger.addHandler(stderr_handler)


# create a Flask blueprint for getting task status info
tasks = Blueprint('tasks', __name__)

@tasks.route('/status/<task_id>')
def status(task_id):
    result = celery.AsyncResult(task_id)
    subtask_count = 0
    completed_subtask_count = 0
    failed_subtask_count = 0
    for subtask in result.children:
        subtask_count += 1
        if subtask.successful():
            completed_subtask_count += 1
        if subtask.failed():
            failed_subtask_count += 1

    return jsonify({
        "status": result.state,
        "subtask_count": subtask_count,
        "completed_subtask_count": completed_subtask_count,
        "failed_subtask_count": failed_subtask_count,
    })


# Working in a Celery task means we can't take advantage of Flask-Dance's
# session proxies, so we'll explicitly define the sessions here.
github_session = github_bp.session
jira_session = jira_bp.session
