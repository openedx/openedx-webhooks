"""
Utilities for working with JIRA.
"""

import arrow

from .decorators import inject_jira
from .models import JiraFields


def convert_to_jira_datetime_string(dt):
    """
    Convert a datetime to format expected by JIRA's API.

    If the input datetime doesn't contain `tzinfo`, it is assumed to be UTC.

    For example: ``'2016-10-23T08:22:54.706-0700'``

    Arguments:
        dt (datetime.datetime)

    Returns:
        str
    """
    return arrow.get(dt).format('YYYY-MM-DDTHH:mm:ss.SSSZ')


@inject_jira
def find_allowed_values(jira, project_key, issue_type_name, field_name):
    """
    Find allowed values for a given JIRA field.

    Certain JIRA field types (such as Radio Buttons) have enumerated
    allowed values. This function retrieves those values in a format
    which can used to set the value for that field while creating or
    editing an issue.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        project_key (str): The JIRA project key
        issue_type_name (str): Name of the issue type within the project
        field_name (str): Name of the field within the issue type

    Returns:
        List[Dict[str, str]]: List of allowed values in JIRA spec format
    """
    meta = jira.createmeta(
        project_key,
        issuetypeNames=issue_type_name,
        expand='projects.issuetypes.fields',
    )
    fields = meta['projects'][0]['issuetypes'][0]['fields']
    field_id = make_fields_lookup(jira, [field_name])[field_name]
    return fields[field_id]['allowedValues']


@inject_jira
def make_fields_lookup(jira, names=[]):
    """
    Make a map of JIRA field names to IDs.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        names (List[str]): List of field names we want to look up

    Returns:
        Dict[str, str]: {field_name: field_id, ...}
    """
    fields = JiraFields(jira.fields())
    lookup = {}
    for name in names:
        field = fields.get_by_name(name)
        lookup[field.name] = field.id
    return lookup
