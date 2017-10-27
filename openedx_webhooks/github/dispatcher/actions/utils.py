# -*- coding: utf-8 -*-
"""
Utilities for GitHub webhook handler actions.
"""
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from ....lib.github.decorators import inject_gh


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


@inject_gh
def create_pull_request_comment(gh, event, comment):
    pr_number = event.event_resource['number']
    issue = gh.issue(event.repo_owner_login, event.repo_name, pr_number)
    issue.create_comment(comment)
