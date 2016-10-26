# -*- coding: utf-8 -*-
"""
Tools to work with GitHub.

This package also contains a special ``bin/`` directory, which has
scripts to interact with GitHub.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from github3 import GitHub

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
except ImportError:
    pass

_token = os.getenv('GITHUB_PERSONAL_TOKEN')

gh = GitHub(token=_token)
"""
(github3.GitHub): An authenticated GitHub API client session
"""
