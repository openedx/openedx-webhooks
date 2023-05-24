"""Settings for how the webhook should behave."""

import os
from typing import Optional

from openedx_webhooks.types import GhProject


# The Jira server to use.  Missing or "" will become None,
# meaning don't use Jira at all.
JIRA_SERVER = os.environ.get("JIRA_SERVER", None) or None
JIRA_USER_EMAIL = os.environ.get("JIRA_USER_EMAIL", None)
JIRA_USER_TOKEN = os.environ.get("JIRA_USER_TOKEN", None)

GITHUB_PERSONAL_TOKEN = os.environ.get("GITHUB_PERSONAL_TOKEN", None)


def read_project_setting(setting_name: str) -> Optional[GhProject]:
    """Read a project spec from a setting.

    Project number NUM in org ORG is specified as ``ORG:NUM``.

    Returns:
        ("ORG", NUM) if the setting is present.
        None if the setting is missing.
    """
    project = os.environ.get(setting_name, None)
    if project is not None:
        org, num = project.split(":")
        return (org, int(num))
    return None


# The project all OSPRs should be added to.
# This should be in the form of org:num, like "openedx:19"
GITHUB_OSPR_PROJECT = read_project_setting("GITHUB_OSPR_PROJECT")

# The project all Blended pull requests should be added to.
GITHUB_BLENDED_PROJECT = read_project_setting("GITHUB_BLENDED_PROJECT")


# Made-up values to use while testing.
class TestSettings:
    GITHUB_BLENDED_PROJECT = ("blendorg", 42)
    GITHUB_OSPR_PROJECT = ("testorg", 17)
    GITHUB_PERSONAL_TOKEN = "github_pat_FooBarBaz"
    JIRA_SERVER = "https://test.atlassian.net"
    JIRA_USER_EMAIL = "someone@megacorp.com"
    JIRA_USER_TOKEN = "xyzzy-123-plugh"
