"""
Helpers for Celery tasks.
"""

from celery.utils.log import get_task_logger
from flask import Blueprint, jsonify

from openedx_webhooks import celery, log_level
from openedx_webhooks.utils import requires_auth


# Set up Celery logging.
logger = get_task_logger(__name__)
logger.setLevel(log_level)

# Use this to show the logging configuration if you need to debug it.
#  import logging_tree
#  from openedx_webhooks.debug import print_long
#  print_long("logging_tree output", logging_tree.format.build_description())

# create a Flask blueprint for getting task status info
tasks = Blueprint('tasks', __name__)

@tasks.route('/status/<task_id>')
@requires_auth
def status(task_id):
    result = celery.AsyncResult(task_id)
    return jsonify({
        "status": result.state,
        "info": result.info,
    })

@tasks.route('/statusrepr/<task_id>')
@requires_auth
def statusrepr(task_id):
    """Get the status of a task, but repr() everything so we can see JSON failures from /status/<task_id>"""
    result = celery.AsyncResult(task_id)
    return jsonify({
        "status": repr(result.state),
        "info": repr(result.info),
    })

@tasks.route('/status/group:<group_id>')
@requires_auth
def group_status(group_id):
    # NOTE: This will only work if the GroupResult
    # has previously called .save() on itself
    group_result = celery.GroupResult.restore(group_id)
    completed_task_ids = []
    failed_task_ids = []
    pending_task_ids = []
    for result in group_result.results:
        if result.successful():
            completed_task_ids.append(result.id)
        elif result.failed():
            failed_task_ids.append(result.id)
        else:
            pending_task_ids.append(result.id)
    return jsonify({
        "task_count": len(group_result.results),
        "completed_task_count": len(completed_task_ids),
        "completed_task_ids": completed_task_ids,
        "failed_task_count": len(failed_task_ids),
        "failed_task_info": failed_task_ids,
        "pending_task_count": len(pending_task_ids),
        "pending_task_info": pending_task_ids,
    })
