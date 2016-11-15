# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest
from jira import JIRA


@pytest.fixture
def jira_client(mocker):
    jira = mocker.Mock(spec_set=JIRA)
    return jira
