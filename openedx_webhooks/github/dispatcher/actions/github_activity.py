# -*- coding: utf-8 -*-
"""
Update JIRA issue with latest GitHub activity.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from ....jira.tasks import update_latest_github_activity
from ....lib.github.decorators import inject_gh
from ....lib.jira.decorators import inject_jira
from ...models import GithubEvent
from .utils import find_issues_for_pull_request

EVENT_TYPES = (
    'issue_comment',
    'pull_request',
    'pull_request_review',
    'pull_request_review_comment',
)


@inject_jira
@inject_gh
def run(gh, jira, event_type, raw_event):
    """
    Update each corresponding JIRA issue with GitHub activity.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        jira (jira.JIRA): An authenticated JIRA API client session
        event_type (str): GitHub event type
        raw_event (Dict[str, Any]): The parsed event payload
    """
    event = GithubEvent(gh, event_type, raw_event)

    if event.is_by_robot:
        return

    issues = find_issues_for_pull_request(jira, event.html_url)
    for issue in issues:
        update_latest_github_activity(
            jira,
            issue.id,
            event.description,
            event.sender_login,
            event.updated_at,
            event.is_by_edx_user,
        )
