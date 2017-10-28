# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import pytest

from openedx_webhooks.github.models import GithubEvent


@pytest.fixture
def event(github_client):
    event = GithubEvent(github_client, 'type', {})
    return event


def test_sender(github_client):
    expected = 'active-person'
    payload = {
        'sender': {
            'login': expected,
        },
    }
    event = GithubEvent(github_client, 'type', payload)
    assert event.openedx_user.login == expected


def test_unknown_sender(github_client):
    payload = {
        'sender': {
            'login': 'unknown',
        },
    }
    event = GithubEvent(github_client, 'type', payload)
    assert event.openedx_user is None


class TestIsByKnownUser:
    def test_known_current_user(self, event, active_person, mocker):
        _patch_user(mocker, active_person)
        assert event.is_by_known_user is True

    def test_known_expired_user(self, event, expired_person, mocker):
        _patch_user(mocker, expired_person)
        assert event.is_by_known_user is True

    def test_unkown_user(self, event, mocker):
        _patch_user(mocker, None)
        assert event.is_by_known_user is False


class TestIsByCurrentUser:
    def test_known_current_user(self, event, active_person, mocker):
        _patch_user(mocker, active_person)
        assert event.is_by_current_user is True

    def test_known_expired_user(self, event, expired_person, mocker):
        _patch_user(mocker, expired_person)
        assert event.is_by_current_user is False

    def test_unkown_user(self, event, mocker):
        _patch_user(mocker, None)
        assert event.is_by_current_user is False


class TestIsByEdxUser:
    def test_edx_user(self, event, active_edx_person, mocker):
        _patch_user(mocker, active_edx_person)
        assert event.is_by_edx_user is True

    def test_non_edx_user(self, event, active_non_edx_person, mocker):
        _patch_user(mocker, active_non_edx_person)
        assert event.is_by_edx_user is False


class TestIsByRobot:
    def test_robot(self, event, robot, mocker):
        _patch_user(mocker, robot)
        assert event.is_by_robot is True

    def test_non_edx_user(self, event, active_person, mocker):
        _patch_user(mocker, active_person)
        assert event.is_by_robot is False


def _patch_user(mocker, person):
    mocker.patch(
        'openedx_webhooks.github.models.GithubEvent.openedx_user',
        new_callable=mocker.PropertyMock,
        return_value=person
    )
