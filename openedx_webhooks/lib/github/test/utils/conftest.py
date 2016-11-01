# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import namedtuple

import pytest

Hook = namedtuple('Hook', ['name', 'config', 'active'])
Repo = namedtuple('Repo', ['iter_hooks'])


@pytest.fixture
def hooks():
    hooks = [
        Hook(name='web', config={'url': 'http://test.me'}, active=True),
        Hook(name='travis', config={'url': 'http://travis'}, active=True),
        Hook(name='web', config={'url': 'http://test.me'}, active=False),
        Hook(name='trello', config={'url': 'http://test.me'}, active=True),
        Hook(name='web', config={'url': 'http://test.inactive'}, active=False),
    ]
    return hooks


@pytest.fixture
def repo(hooks):
    repo = Repo(iter_hooks=lambda: hooks)
    return repo
