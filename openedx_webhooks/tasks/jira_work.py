import requests

from openedx_webhooks.oauth import jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import (
    log_check_response,
    sentry_extra_context,
)

def transition_jira_issue(issue_key, status_name):
    """
    Transition a Jira issue to a new status.

    Returns:
        True if the issue was changed.

    """
    assert status_name is not None
    jira = jira_bp.session
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    transitions_resp = jira.get(transition_url)
    log_check_response(transitions_resp, raise_for_status=False)
    if transitions_resp.status_code == requests.codes.not_found:
        # JIRA issue has been deleted
        logger.info(f"Issue {issue_key} doesn't exist")
        return False
    transitions_resp.raise_for_status()

    transitions = transitions_resp.json()["transitions"]
    sentry_extra_context({"transitions": transitions})

    transition_id = None
    for t in transitions:
        if t["to"]["name"] == status_name:
            transition_id = t["id"]
            break

    if not transition_id:
        # maybe the issue is *already* in the right status?
        issue_url = "/rest/api/2/issue/{key}".format(key=issue_key)
        issue_resp = jira.get(issue_url)
        issue_resp.raise_for_status()
        issue = issue_resp.json()
        sentry_extra_context({"jira_issue": issue})
        current_status = issue["fields"]["status"]["name"]
        if current_status == status_name:
            logger.info(f"Issue {issue_key} is already in status {status_name}")
            return False

        # nope, raise an error message
        fail_msg = (
            "Issue {key} cannot be transitioned directly from status {curr_status} "
            "to status {new_status}. Valid status transitions are: {valid}".format(
                key=issue_key,
                new_status=status_name,
                curr_status=current_status,
                valid=", ".join(t["to"]["name"] for t in transitions),
            )
        )
        logger.error(fail_msg)
        raise Exception(fail_msg)

    logger.info(f"Changing status on issue {issue_key} to {status_name}")
    transition_resp = jira.post(transition_url, json={
        "transition": {
            "id": transition_id,
        }
    })
    log_check_response(transition_resp)
    return True
