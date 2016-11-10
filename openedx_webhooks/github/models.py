# -*- coding: utf-8 -*-
"""
GitHub related domain models.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from ..lib.edx_repo_tools_data.utils import get_people
from ..lib.github.models import GithubWebHookEvent


class GithubEvent(GithubWebHookEvent):
    """
    A GitHub webhook event.

    Attributes:
        gh (github3.GitHub): An authenticated GitHub API client session
        event_type (str): GitHub event type
        event (Dict[str, Any]): The parsed event payload
    """

    def __init__(self, gh, event_type, event):
        """
        Init.

        Arguments:
            gh (github3.GitHub): An authenticated GitHub API client session
            event_type (str): GitHub event type
            event (Dict[str, Any]): The parsed event payload
        """
        super(GithubEvent, self).__init__(event_type, event)
        self.gh = gh

    @property
    def sender(self):
        """
        openedx_webhooks.lib.edx_repo_tools_data.models.Person: Activity user.
        """
        people = get_people(self.gh)
        return people.get(self.sender_login)
