# -*- coding: utf-8 -*-
"""
Utilities for working with `edx/repo-tools-data`.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from base64 import b64decode

import yaml

from ..github import gh
from .models import People


def get_people():
    """
    Fetch `people.yaml` from GitHub repo.

    Returns:
        openedx_webhooks.lib.edx_repo_tools_data.models.People
    """
    repo = gh.repository('edx', 'repo-tools-data')
    raw = repo.contents('people.yaml').decoded
    return People(yaml.safe_load(raw))
