# -*- coding: utf-8 -*-
"""
Open a new JIRA OSPR issue if new PR is opened by a community member.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from ....lib.github.decorators import inject_gh
from ....lib.jira.decorators import inject_jira
from ...models import GithubEvent
from .utils import find_issues_for_pull_request

EVENT_TYPES = (
    'pull_request',
)


@inject_jira
@inject_gh
def create_ospr_from_event(gh, jira, event):
    """
    Update each corresponding JIRA issue with GitHub activity.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        jira (jira.JIRA): An authenticated JIRA API client session
        event_type (str): GitHub event type
        raw_event (Dict[str, Any]): The parsed event payload
    """
    is_known_user = bool(event.openedx_user)

    if is_known_user and event.openedx_user.is_robot:
        return

    is_edx_user = is_known_user and event.openedx_user.is_edx_user

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


@inject_gh
def run(gh, event_type, raw_event):
    event = GithubEvent(gh, event_type, raw_event)
    if event.action != 'opened':
        return
    create_ospr_from_event(event)
