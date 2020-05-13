"""
Utilities for working with `edx/repo-tools-data`.
"""

import yaml

from ..github.decorators import inject_gh
from .models import People


@inject_gh
def get_people(gh):
    """
    Fetch `people.yaml` from GitHub repo.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session

    Returns:
        openedx_webhooks.lib.edx_repo_tools_data.models.People
    """
    repo = gh.repository('edx', 'repo-tools-data')
    raw = repo.contents('people.yaml').decoded
    return People(yaml.safe_load(raw))
