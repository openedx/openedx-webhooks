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
from .new_pull_request_helpers import (
    create_contractor_comment, create_ospr, create_ospr_comment
)

EVENT_TYPES = (
    'pull_request',
)


@inject_jira
@inject_gh
def run(gh, jira, event_type, raw_event):
    event = GithubEvent(gh, event_type, raw_event)
    if should_not_process_event(event):
        return

    user = event.openedx_user
    is_known_user = bool(user)
    is_current_user = is_known_user and not user.has_agreement_expired
    is_contractor = is_current_user and user.is_contractor

    if is_contractor:
        create_contractor_comment(gh, event)
    elif is_current_user:
        ospr_info = create_ospr(jira, event)
        create_ospr_comment(gh, event, ospr_info)
    else:
        ospr_info = create_ospr(jira, event, 'Awaiting Author')
        create_ospr_comment(gh, event, ospr_info)


def should_not_process_event(event):
    if event.action != 'opened':
        return True

    user = event.openedx_user
    is_known_user = bool(user)
    condition = is_known_user and (user.is_robot or user.is_committer)
    return condition
