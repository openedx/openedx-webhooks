# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import pytest


@pytest.fixture(autouse=True)
def patch_get_people(people, mocker):
    mocker.patch(
        'openedx_webhooks.github.models.get_people', return_value=people
    )
