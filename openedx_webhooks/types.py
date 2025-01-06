"""Types specific to openedx_webhooks."""

from __future__ import annotations

import dataclasses
from typing import Dict, Tuple

# A pull request as described by a JSON object.
PrDict = Dict

# A pull request comment as described by a JSON object.
PrCommentDict = Dict

# A Jira issue described by a JSON object.
JiraDict = Dict

# A GitHub project: org name, and number.
GhProject = Tuple[str, int]

# A GitHub project metadata json object.
GhPrMetaDict = Dict


@dataclasses.dataclass(frozen=True)
class PrId:
    """An id of a pull request, with a repo full_name and an id."""
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


@dataclasses.dataclass(frozen=True)
class JiraServer:
    """A Jira server and its credentials."""
    # The URL of the Jira server.
    server: str

    # The user email and token to use for credentials.
    email: str
    token: str

    # A description of the server, suitable for the bot to comment,
    # "I created an issue in {{ description }}." or
    # "There's no project in {{ description }}."
    description: str

    # The URL to get jira-mapping.yaml from.
    mapping: str

    # A textual description of how to contact the admin of the server, suitable
    # for use in a bot comment: "Contact {{ contact }} to add a mapping."
    contact: str = ""


@dataclasses.dataclass(frozen=True)
class JiraId:
    """A JiraServer nickname and an issue key."""
    nick: str
    key: str

    def asdict(self):
        return dataclasses.asdict(self)
