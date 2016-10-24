# -*- coding: utf-8 -*-
"""
Tasks that update JIRA in some way.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from collections import namedtuple

from ..lib.jira import jira
from ..lib.jira.utils import (
    convert_to_jira_datetime_string, find_allowed_values, make_fields_lookup
)

JiraGithubPrFieldNames = namedtuple('_JiraGithubPrFieldNames', (
    'LAST_UPDATED_AT',
    'LAST_UPDATED_BY',
    'LATEST_ACTION',
    'LATEST_BY_EDX',
))

JIRA_PR_FIELDS = JiraGithubPrFieldNames(
    LAST_UPDATED_AT='GitHub PR Last Updated At',
    LAST_UPDATED_BY='GitHub PR Last Updated By',
    LATEST_ACTION='GitHub Latest Action',
    LATEST_BY_EDX='GitHub Latest Action By edX',
)

JIRA_FIELDS_ID_LOOKUP = make_fields_lookup(JIRA_PR_FIELDS._asdict().values())
"""
Dict[str, str]: Mapping of JIRA field names to IDs
"""


def _make_edx_action_choices(find_allowed_values=find_allowed_values):
    # TODO: Test
    values = find_allowed_values(
        'OSPR',
        'Pull Request Review',
        'GitHub Latest Action By edX'
    )
    choices = {
        True: next(v for v in values if v['value'] == 'Yes'),
        False: next(v for v in values if v['value'] == 'No'),
    }
    return choices

JIRA_EDX_ACTION_CHOICES = _make_edx_action_choices()
"""
Dict[bool, Dict[str, str]]: Mapping of Boolean values to JIRA choices for
    ``OSPR:Pull Request Review:GitHub Latest Action By edX`` field
"""


def update_latest_github_activity(
        issue_id, description, login, updated_at, is_edx_user, jira=jira
):
    """
    Update JIRA issue with latest GitHub activity data.

    Arguments:
        issue_id (str): The JIRA issue ID
        description (str): Description of GitHub activity
        login (str): GitHub login of user who generated the activity
        updated_at (datetime.datetime): Datetime of when the activity happened
        is_edx_user (bool): Is the user associated with edX?
        jira (jira.JIRA): JIRA API client instance
    """
    issue = jira.issue(issue_id)
    update_dt = convert_to_jira_datetime_string(updated_at)
    latest_by_edx = JIRA_EDX_ACTION_CHOICES[is_edx_user]

    fields = {
        JIRA_PR_FIELDS.LATEST_ACTION: description,
        JIRA_PR_FIELDS.LAST_UPDATED_BY: login,
        JIRA_PR_FIELDS.LAST_UPDATED_AT: update_dt,
        JIRA_PR_FIELDS.LATEST_BY_EDX: latest_by_edx,
    }

    fields = {JIRA_FIELDS_ID_LOOKUP[k]: v for k, v in fields.items()}

    issue.update(fields)
