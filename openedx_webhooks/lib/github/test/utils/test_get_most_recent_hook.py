from collections import namedtuple

import arrow
import pytest

from openedx_webhooks.lib.github.utils import _get_most_recent_hook

Hook = namedtuple('Hook', ['active', 'updated_at'])
now = arrow.utcnow()


@pytest.fixture
def single_active():
    hooks = [Hook(active=True, updated_at=now.datetime)]
    return hooks


@pytest.fixture
def single_inactive():
    hooks = [Hook(active=False, updated_at=now.datetime)]
    return hooks


@pytest.fixture
def multiple_active():
    hooks = [
        Hook(active=True, updated_at=now.shift(months=-10).datetime),
        Hook(active=True, updated_at=now.shift(days=-10).datetime),
        Hook(active=True, updated_at=now.datetime),
    ]
    return hooks


@pytest.fixture
def multiple_inactive():
    hooks = [
        Hook(active=False, updated_at=now.shift(months=-10).datetime),
        Hook(active=False, updated_at=now.shift(days=-10).datetime),
        Hook(active=False, updated_at=now.datetime),
    ]
    return hooks


@pytest.fixture
def multiple_mixed():
    hooks = [
        Hook(active=True, updated_at=now.shift(months=-10).datetime),
        Hook(active=True, updated_at=now.shift(days=-10).datetime),
        Hook(active=False, updated_at=now.datetime),
    ]
    return hooks


def test_no_hooks():
    assert _get_most_recent_hook([]) is None


def test_single_active(single_active):
    assert _get_most_recent_hook(single_active) == single_active[0]


def test_single_inactive(single_inactive):
    assert _get_most_recent_hook(single_inactive) == single_inactive[0]


def test_multiple_active(multiple_active):
    assert _get_most_recent_hook(multiple_active) == multiple_active[2]


def test_multiple_inactive(multiple_inactive):
    assert _get_most_recent_hook(multiple_inactive) == multiple_inactive[2]


def test_multiple_mixed(multiple_mixed):
    assert _get_most_recent_hook(multiple_mixed) == multiple_mixed[1]
