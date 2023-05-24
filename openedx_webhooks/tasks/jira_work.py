"""
Jira manipulations.
"""

from typing import Any, Dict, List, Optional

import requests

from openedx_webhooks.auth import get_jira_session
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import (
    get_jira_custom_fields,
    log_check_response,
    sentry_extra_context,
)

def delete_jira_issue(issue_key):
    """
    Delete an issue from Jira.
    """
    resp = get_jira_session().delete(f"/rest/api/2/issue/{issue_key}")
    log_check_response(resp)


def find_issues_for_pull_request(jira, pull_request_url):
    """
    Find corresponding JIRA issues for a given GitHub pull request.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        pull_request_url (str)

    Returns:
        jira.client.ResultList[jira.Issue]
    """
    jql = 'project=OSPR AND cf[10904]="{}"'.format(pull_request_url)
    return jira.search_issues(jql)


def transition_jira_issue(issue_key, status_name):
    """
    Transition a Jira issue to a new status.

    Returns:
        True if the issue was changed.

    """
    assert status_name is not None
    transition_url = (
        "/rest/api/2/issue/{key}/transitions"
        "?expand=transitions.fields".format(key=issue_key)
    )
    transitions_resp = get_jira_session().get(transition_url)
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
        issue_resp = get_jira_session().get(issue_url)
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
    transition_resp = get_jira_session().post(transition_url, json={
        "transition": {
            "id": transition_id,
        }
    })
    log_check_response(transition_resp)
    return True


def update_jira_issue(
        issue_key: str,
        summary: Optional[str]=None,
        description: Optional[str]=None,
        labels: Optional[List[str]]=None,
        epic_link: Optional[str]=None,
        extra_fields: Optional[Dict[str, str]]=None,
    ):
    """
    Update some fields on a Jira issue.
    """
    fields: Dict[str, Any] = {}
    notify = "false"
    custom_fields = get_jira_custom_fields()
    if summary is not None:
        fields["summary"] = summary
        notify = "true"
    if description is not None:
        fields["description"] = description
        notify = "true"
    if labels is not None:
        fields["labels"] = labels
    if epic_link is not None:
        fields[custom_fields["Epic Link"]] = epic_link
    if extra_fields is not None:
        for name, value in extra_fields.items():
            fields[custom_fields[name]] = value
    assert fields
    # Note: notifyUsers=false only works if the bot is an admin in the project.
    # Contrary to the docs, if the bot is not an admin, the setting isn't ignored,
    # the request fails.
    url = f"/rest/api/2/issue/{issue_key}?notifyUsers={notify}"
    resp = get_jira_session().put(url, json={"fields": fields})
    log_check_response(resp)
