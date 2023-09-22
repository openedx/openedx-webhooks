"""Settings for how the webhook should behave."""

import os
from types import SimpleNamespace
from typing import Mapping, Optional

from openedx_webhooks.types import GhProject


# The global settings object.
settings = SimpleNamespace()


def settings_from_environment(env: Mapping) -> None:
    """Update `settings` from a dict of environment variables."""
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
