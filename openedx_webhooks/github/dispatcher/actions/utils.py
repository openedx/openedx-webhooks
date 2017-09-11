# -*- coding: utf-8 -*-
"""
Utilities for GitHub webhook handler actions.
"""
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)


def find_issues_for_pull_request(jira, pull_request_url):
    """
    Find corresponding JIRA issues for a given GitHub pull request.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        pull_request_url (str)

    Returns:
        jira.client.ResultList[jira.Issue]
    """
    jql = 'project=OSPR AND url="{}"'.format(pull_request_url)
    return jira.search_issues(jql)
