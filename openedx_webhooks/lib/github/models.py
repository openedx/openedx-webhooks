"""
Generic GitHub domain models.
"""

from __future__ import annotations

import dataclasses

from openedx_webhooks.types import PrDict

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
