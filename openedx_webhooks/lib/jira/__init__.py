# -*- coding: utf-8 -*-
"""
Tools to work with JIRA.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from base64 import b64decode
import os

from jira import JIRA

_server = os.environ.get('JIRA_SERVER')
_oauth_info = dict(
    access_token=os.environ.get('JIRA_ACCESS_TOKEN'),
    access_token_secret=os.environ.get('JIRA_ACCESS_TOKEN_SECRET'),
    consumer_key=os.environ.get('JIRA_OAUTH_CONSUMER_KEY'),
    key_cert=b64decode(os.environ.get('JIRA_OAUTH_PRIVATE_KEY')),
)

jira = JIRA(_server, oauth=_oauth_info)
"""
(jira.JIRA): An authenticated JIRA API client session
"""
