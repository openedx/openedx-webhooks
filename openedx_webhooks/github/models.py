# -*- coding: utf-8 -*-
"""
GitHub related domain models.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from functools32 import lru_cache

from ..lib.edx_repo_tools_data.utils import get_people as _get_people
from ..lib.exceptions import NotFoundError
from ..lib.github.models import GithubWebHookEvent

get_people = lru_cache()(_get_people)


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
    def openedx_user(self):
        """
        Optional(openedx_webhooks.lib.edx_repo_tools_data.models.Person):
            Activity user.
        """
        people = get_people(self.gh)
        try:
            return people.get(self.sender_login)
        except NotFoundError:
            return None

    @property
    def is_by_known_user(self):
        return bool(self.openedx_user)

    @property
    def is_by_current_user(self):
        return (
            self.is_by_known_user
            and not self.openedx_user.has_agreement_expired
        )

    @property
    def is_by_edx_user(self):
        return self.is_by_known_user and self.openedx_user.is_edx_user

    @property
    def is_by_contractor(self):
        return self.is_by_known_user and self.openedx_user.is_contractor

    @property
    def is_by_committer(self):
        return self.is_by_known_user and self.openedx_user.is_committer

    @property
    def is_by_robot(self):
        return self.is_by_known_user and self.openedx_user.is_robot
