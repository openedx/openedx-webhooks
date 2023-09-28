"""Settings for how the webhook should behave."""

import os
from typing import Optional

from openedx_webhooks.types import GhProject


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


GITHUB_PERSONAL_TOKEN = os.environ.get("GITHUB_PERSONAL_TOKEN", None)

# The project all OSPRs should be added to.
# This should be in the form of org:num, like "openedx:19"
GITHUB_OSPR_PROJECT = read_project_setting("GITHUB_OSPR_PROJECT")

# The project all Blended pull requests should be added to.
GITHUB_BLENDED_PROJECT = read_project_setting("GITHUB_BLENDED_PROJECT")
