"""
Tasks that update JIRA in some way.
"""

from ..lib.jira.decorators import inject_jira
from ..lib.jira.utils import (
    convert_to_jira_datetime_string, find_allowed_values, make_fields_lookup
)

LAST_UPDATED_AT = 'Github PR Last Updated At'
LAST_UPDATED_BY = 'Github PR Last Updated By'
LATEST_ACTION = 'Github Latest Action'
LATEST_BY_EDX = 'Github Latest Action by edX'


def _make_edx_action_choices(jira):
    """
    Map of Boolean values to JIRA choices.

    Specifically for ``OSPR:Pull Request Review:GitHub Latest Action By edX``
    field.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session

    Returns:
        Dict[bool, Dict[str, str]]: Mapping of Boolean values to JIRA choices
    """
    values = find_allowed_values(
        jira,
        'OSPR',
        'Pull Request Review',
        LATEST_BY_EDX
    )
    choices = {
        True: next(v for v in values if v['value'] == 'Yes'),
        False: next(v for v in values if v['value'] == 'No'),
    }
    return choices


@inject_jira
def update_latest_github_activity(
        jira, issue_id, description, login, updated_at, is_edx_user
):
    """
    Update JIRA issue with latest GitHub activity data.

    Arguments:
        jira (jira.JIRA): JIRA API client instance
        issue_id (str): The JIRA issue ID
        description (str): Description of GitHub activity
        login (str): GitHub login of user who generated the activity
        updated_at (datetime.datetime): Datetime of when the activity happened
        is_edx_user (bool): Is the user associated with edX?
    """
    update_dt = convert_to_jira_datetime_string(updated_at)
    latest_action_by_edx_choices = _make_edx_action_choices(jira)
    latest_by_edx = latest_action_by_edx_choices[is_edx_user]

    field_map = {
        LAST_UPDATED_AT: update_dt,
        LAST_UPDATED_BY: login,
        LATEST_ACTION: description,
        LATEST_BY_EDX: latest_by_edx,
    }

    field_ids = make_fields_lookup(jira, field_map.keys())

    fields = {field_ids[k]: v for k, v in field_map.items()}

    jira.issue(issue_id).update(fields)
