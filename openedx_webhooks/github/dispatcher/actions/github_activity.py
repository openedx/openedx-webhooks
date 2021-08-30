"""
Update JIRA issue with latest GitHub activity.
"""

from ....jira.tasks import update_latest_github_activity
from ....lib.github.client import get_authenticated_gh_client
from ....lib.jira.client import get_authenticated_jira_client
from ...models import GithubEvent
from .utils import find_issues_for_pull_request

EVENT_TYPES = (
    'issue_comment',
    'pull_request',
    'pull_request_review',
    'pull_request_review_comment',
)


def run(event_type, raw_event, github_client=None, jira_client=None):
    """
    Update each corresponding JIRA issue with GitHub activity.

    Arguments:
        event_type (str): GitHub event type
        raw_event (Dict[str, Any]): The parsed event payload
    """
    gh = github_client or get_authenticated_gh_client()
    event = GithubEvent(gh, event_type, raw_event)
    is_known_user = bool(event.openedx_user)

    if is_known_user and event.openedx_user.is_robot:
        return

    is_edx_user = is_known_user and event.openedx_user.is_edx_user

    jira = jira_client or get_authenticated_jira_client()
    issues = find_issues_for_pull_request(jira, event.html_url)
    for issue in issues:
        update_latest_github_activity(
            jira,
            issue.id,
            event.description,
            event.sender_login,
            event.updated_at,
            is_edx_user,
        )
