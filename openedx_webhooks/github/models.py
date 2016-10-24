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
        event_type (str): GitHub event type
        event (Dict[str, Any]): The parsed event payload
        get_people (Callable[[], ..lib.edx_repo_tools_data.models.People]):
            Function used to get `people.yaml` folks
    """

    def __init__(self, event_type, event, get_people=get_people):
        """
        Init.

        Arguments:
            event_type (str): GitHub event type
            event (Dict[str, Any]): The parsed event payload
            get_people (Callable[[], ..lib.edx_repo_tools_data.models.People]):
                Function used to get `people.yaml` folks
        """
        super(GithubEvent, self).__init__(event_type, event)
        self.get_people = get_people

    @property
    def is_edx_user(self):
        """
        bool: Is the user who sent the event part of edX.
        """
        return self.user.is_edx_user

    @property
    def user(self):
        """
        openedx_webhooks.lib.edx_repo_tools_data.models.Person: Activity user.
        """
        people = self.get_people()
        return people.get(self.sender_login)
