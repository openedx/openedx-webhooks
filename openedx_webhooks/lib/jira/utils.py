# -*- coding: utf-8 -*-
"""
Utilities for working with JIRA.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import arrow

from . import jira
from .models import JiraFields


def convert_to_jira_datetime_string(dt):
    """
    Convert a datetime to format expected by JIRA's API.

    For example: ``'2016-10-23T08:22:54.706-0700'``

    Arguments:
        dt (datetime.datetime)

    Returns:
        str
    """
    # TODO: Test
    return arrow.get(dt).format('YYYY-MM-DDTHH:mm:ss.SSSZ')


def find_allowed_values(project_key, issue_type_name, field_name, jira=jira):
    """
    Find allowed values for a given JIRA field.

    Certain JIRA field types (such as Radio Buttons) have enumerated
    allowed values. This function retrieves those values in a format
    which can used to set the value for that field while creating or
    editing an issue.

    Arguments:
        project_key (str): The JIRA project key
        issue_type_name (str): Name of the issue type within the project
        field_name (str): Name of the field within the issue type
        jira (jira.JIRA): An authenticated JIRA API client session

    Returns:
        List[Dict[str, str]]: List of allowed values in JIRA spec format
    """
    meta = jira.createmeta(
        project_key,
        issuetypeNames=issue_type_name,
        expand='projects.issuetypes.fields',
    )
    fields = meta['projects'][0]['issuetypes'][0]['fields']
    field_id = make_fields_lookup([field_name])[field_name]
    return fields[field_id]['allowedValues']


def make_fields_lookup(names=[], jira=jira):
    """
    Make a map of JIRA field names to IDs.

    Arguments:
        names (List[str]): List of field names we want to look up
        jira (jira.JIRA): An authenticated JIRA API client session

    Returns:
        Dict[str, str]: {field_name: field_id, ...}
    """
    # TODO: Test
    fields = JiraFields(jira.fields())
    lookup = {}
    for name in names:
        field = fields.get_by_name(name)
        lookup[field.name] = field.id
    return lookup
