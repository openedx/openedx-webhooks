# -*- coding: utf-8 -*-
"""
GitHub client instance.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from github3 import GitHub

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
except ImportError:  # pragma: no cover
    pass

_token = os.getenv('GITHUB_PERSONAL_TOKEN')

# (github3.GitHub): An authenticated GitHub API client session
github_client = GitHub(token=_token)
