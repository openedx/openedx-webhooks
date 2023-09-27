"""
Jira manipulations.
"""

from typing import Any, Dict, List, Optional

from openedx_webhooks.auth import get_jira_session
from openedx_webhooks.utils import (
    log_check_response,
)


def update_jira_issue(
        jira_nick: str,
        issue_key: str,
        summary: Optional[str]=None,
        description: Optional[str]=None,
        labels: Optional[List[str]]=None,
    ) -> None:
    """
    Update some fields on a Jira issue.
    """
    fields: Dict[str, Any] = {}
    notify = "false"
    if summary is not None:
        fields["summary"] = summary
        notify = "true"
    if description is not None:
        fields["description"] = description
        notify = "true"
    if labels is not None:
        fields["labels"] = labels
    assert fields
    # Note: notifyUsers=false only works if the bot is an admin in the project.
    # Contrary to the docs, if the bot is not an admin, the setting isn't ignored,
    # the request fails.
    url = f"/rest/api/2/issue/{issue_key}?notifyUsers={notify}"
    resp = get_jira_session(jira_nick).put(url, json={"fields": fields})
    log_check_response(resp)
