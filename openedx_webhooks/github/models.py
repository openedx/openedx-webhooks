"""
GitHub related domain models.
"""

from functools import lru_cache

from openedx_webhooks.info import get_people_file

from ..lib.exceptions import NotFoundError
from ..lib.github.models import GithubWebHookEvent
from ..lib.webhooks_data.models import People


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
        Optional(openedx_webhooks.lib.webhooks_data.models.Person):
            Activity user.
        """
        people = People(get_people_file())
        try:
            return people.get(self.sender_login)
        except NotFoundError:
            return None
