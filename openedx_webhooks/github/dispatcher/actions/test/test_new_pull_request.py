# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from collections import namedtuple

from openedx_webhooks.github.dispatcher.actions.new_pull_request import (
    should_not_process_event
)

Event = namedtuple('Event', ['action', 'is_by_committer', 'is_by_robot'])


class TestShouldNotProcessEvent:
    def test_not_opened(self):
        event = Event('closed', False, False)
        assert should_not_process_event(event) is True

    def test_opened(self):
        event = Event('opened', False, False)
        assert should_not_process_event(event) is False

    def test_is_robot(self):
        event = Event('opened', False, True)
        assert should_not_process_event(event) is True

    def test_is_committer(self):
        event = Event('opened', True, False)
        assert should_not_process_event(event) is True
