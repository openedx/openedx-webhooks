# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import pytest

from openedx_webhooks.lib.exceptions import NotFoundError


class TestGet:
    def test_get(self, people):
        expected = 'active-person'
        assert people.get(expected).login == expected

    def test_miss(self, people):
        with pytest.raises(NotFoundError):
            people.get('foo')
