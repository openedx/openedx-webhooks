"""
Generic GitHub domain models.
"""

from __future__ import annotations

import dataclasses

from openedx_webhooks.types import PrDict

class GithubWebHookRequestHeader:
    """
    Represent a GitHub webhook request header.

    Attributes:
        headers (flask.Request.headers): HTTP headers as received by Flask
    """

    def __init__(self, headers):
        """
        Init.

        Arguments:
            headers (flask.Request.headers): HTTP headers as received by Flask
        """
        self.headers = headers

    @property
    def event_type(self):
        """
        str: The webhook event type.
        """
        return self.headers.get('X-Github-Event')

    @property
    def signature(self):
        """
        str: Hash signature of the payload.
        """
        return self.headers.get('X-Hub-Signature')


@dataclasses.dataclass(frozen=True)
class PrId:
    """An id of a pull request, with three parts used by GitHub."""
    full_name: str
    number: int

    @classmethod
    def from_pr_dict(cls, pr: PrDict) -> PrId:
        return cls(pr["base"]["repo"]["full_name"], pr["number"])

    def __str__(self):
        return f"{self.full_name}#{self.number}"

    @property
    def org(self):
        org, _, _ = self.full_name.partition("/")
        return org
