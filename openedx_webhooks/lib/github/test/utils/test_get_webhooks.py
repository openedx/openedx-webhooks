# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from openedx_webhooks.lib.github.utils import get_webhooks


def test_get_hooks(hooks, repo):
    expected = [hooks[0], hooks[2]]
    result = list(get_webhooks(repo, 'http://test.me'))
    assert result == expected


def test_get_no_hooks(repo):
    expected = []
    result = list(get_webhooks(repo, 'http://test.you'))
    assert result == expected
