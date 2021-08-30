"""
Utilities for working with `edx/repo-tools-data`.
"""

import yaml

from ..github.client import get_authenticated_gh_client
from .models import People


def get_people():
    """
    Fetch `people.yaml` from GitHub repo.

    Returns:
        openedx_webhooks.lib.edx_repo_tools_data.models.People
    """
    gh = get_authenticated_gh_client()
    repo = gh.repository('edx', 'repo-tools-data')
    raw = repo.file_contents('people.yaml').decoded
    return People(yaml.safe_load(raw))
