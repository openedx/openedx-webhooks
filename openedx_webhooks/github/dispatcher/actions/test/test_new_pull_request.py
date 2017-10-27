# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from collections import namedtuple

from openedx_webhooks.github.dispatcher.actions.new_pull_request import (
    should_not_process_event
)

Event = namedtuple('Event', ['action', 'openedx_user'])
User = namedtuple('User', ['is_robot', 'is_committer'])


class TestShouldNotProcessEvent:
    def test_not_opened(self):
        event = Event('closed', None)
        assert should_not_process_event(event) is True

    def test_opened(self):
        event = Event('opened', None)
        assert should_not_process_event(event) is False

    def test_is_robot(self):
        user = User(True, False)
        event = Event('opened', user)
        assert should_not_process_event(event) is True

    def test_is_committer(self):
        user = User(False, True)
        event = Event('opened', user)
        assert should_not_process_event(event) is True

    def test_community_member(self):
        user = User(False, False)
        event = Event('opened', user)
        assert should_not_process_event(event) is False
