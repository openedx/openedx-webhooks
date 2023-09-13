"""Settings for how the webhook should behave."""

import os
from types import SimpleNamespace
from typing import Mapping, Optional

from openedx_webhooks.types import GhProject


settings = SimpleNamespace()


def settings_from_environment(env: Mapping) -> None:
    # The Jira server to use.  Missing or "" will become None,
    # meaning don't use Jira at all.
    settings.JIRA_SERVER = env.get("JIRA_SERVER", None) or None
    settings.JIRA_USER_EMAIL = env.get("JIRA_USER_EMAIL", None)
    settings.JIRA_USER_TOKEN = env.get("JIRA_USER_TOKEN", None)

    settings.GITHUB_PERSONAL_TOKEN = env.get("GITHUB_PERSONAL_TOKEN", None)

    # The project all OSPRs should be added to.
    # This should be in the form of org:num, like "openedx:19"
    settings.GITHUB_OSPR_PROJECT = read_project_setting(env, "GITHUB_OSPR_PROJECT")

    # The project all Blended pull requests should be added to.
    settings.GITHUB_BLENDED_PROJECT = read_project_setting(env, "GITHUB_BLENDED_PROJECT")


def read_project_setting(env: Mapping, setting_name: str) -> Optional[GhProject]:
    """Read a project spec from a setting.

    Project number NUM in org ORG is specified as ``ORG:NUM``.

    Returns:
        ("ORG", NUM) if the setting is present.
        None if the setting is missing.
    """
    project = env.get(setting_name, None)
    if project is not None:
        org, num = project.split(":")
        return (org, int(num))
    return None


# Read our settings from the real environment.
settings_from_environment(os.environ)


# Made-up values to use while testing.
class TestSettings:
    GITHUB_BLENDED_PROJECT = ("blendorg", 42)
    GITHUB_OSPR_PROJECT = ("testorg", 17)
    GITHUB_PERSONAL_TOKEN = "github_pat_FooBarBaz"
    JIRA_SERVER = "https://test.atlassian.net"
    JIRA_USER_EMAIL = "someone@megacorp.com"
    JIRA_USER_TOKEN = "xyzzy-123-plugh"
