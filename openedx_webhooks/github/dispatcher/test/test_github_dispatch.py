# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals


from openedx_webhooks.github.dispatcher import dispatch


class DummyRule:
    def run(self, event_type, event):
        pass


class DummyHeader:
    def __init__(self, headers):
        self.event_type = 'event_type'


def test_dispatch(mocker):
    mocker.patch(
        'openedx_webhooks.github.dispatcher.GithubWebHookRequestHeader',
        DummyHeader
    )

    rules = [DummyRule(), DummyRule()]
    for r in rules:
        mocker.spy(r, 'run')

    dispatch('header', 'event', rules)

    for r in rules:
        r.run.assert_called_once_with('event_type', 'event')
