# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import pytest
from github3 import GitHub


@pytest.fixture
def github_client(mocker):
    return mocker.Mock(spec_set=GitHub)
