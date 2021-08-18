"""
Update JIRA issue with latest GitHub activity.
"""

from ....jira.tasks import update_latest_github_activity
from ....lib.github.decorators import inject_gh
from ....lib.jira.client import get_authenticated_jira_client
from ...models import GithubEvent
from .utils import find_issues_for_pull_request

EVENT_TYPES = (
    'issue_comment',
    'pull_request',
    'pull_request_review',
    'pull_request_review_comment',
)


@inject_gh
def run(gh, event_type, raw_event, jira_client=None):
    """
    Update each corresponding JIRA issue with GitHub activity.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        event_type (str): GitHub event type
        raw_event (Dict[str, Any]): The parsed event payload
    """
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
