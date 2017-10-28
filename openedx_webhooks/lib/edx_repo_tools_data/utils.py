# -*- coding: utf-8 -*-
"""
Utilities for working with `edx/repo-tools-data`.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import yaml

from ..github.decorators import inject_gh
from ..github.utils import get_repo_contents


def _get_entity(gh, yaml_file, return_type):
    contents = get_repo_contents(gh, 'edx/repo-tools-data', yaml_file)
    return return_type(yaml.safe_load(contents))


@inject_gh
def get_orgs(gh):
    """
    Fetch `orgs.yaml` from GitHub repo.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session

    Returns:
        openedx_webhooks.lib.edx_repo_tools_data.models.Orgs
    """
    from .models import Orgs
    orgs = _get_entity(gh, 'orgs.yaml', Orgs)
    return orgs


@inject_gh
def get_people(gh):
    """
    Fetch `people.yaml` from GitHub repo.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session

    Returns:
        openedx_webhooks.lib.edx_repo_tools_data.models.People
    """
    from .models import People
    people = _get_entity(gh, 'people.yaml', People)
    return people
