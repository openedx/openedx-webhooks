# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from datetime import datetime

import pytest
import pytz

from openedx_webhooks.lib.github.models import GithubWebHookEvent


@pytest.fixture
def issue_comment(issue_comment_payload):
    return GithubWebHookEvent('issue_comment', issue_comment_payload)


@pytest.fixture
def pull_request_review():
    payload = {
        'action': 'submitted',
        'pull_request': {
            'html_url': 'https://example.com/pull/1',
            'updated_at': '2016-10-24T18:19:44Z',
        },
        'sender': {
            'login': 'pr-sender',
        },
    }
    return GithubWebHookEvent('pull_request_review', payload)


class TestGithubWebHookEventResource:
    def test_issue(self, issue_comment):
        assert issue_comment._event_resource == 'issue'

    def test_pr(self, pull_request_review):
        assert pull_request_review._event_resource == 'pull_request'

    def test_other(self):
        event = GithubWebHookEvent('something_else', None)
        assert event._event_resource == 'something_else'


def test_githubwebhookevent_action(pull_request_review):
    assert pull_request_review.action == 'submitted'


def test_githubwebhookevent_desc(issue_comment):
    assert issue_comment.description == 'issue_comment: edited'


class TestGithubWebHookEventHtmlUrl:
    def test_issue(self, issue_comment):
        assert issue_comment.html_url == 'https://example.com/issue/1'

    def test_pr(self, pull_request_review):
        assert pull_request_review.html_url == 'https://example.com/pull/1'


def test_githubwebhookevent_sender_login(issue_comment):
    assert issue_comment.sender_login == 'issue-sender'


class TestGithubWebHookEventUpdatedAt:
    def test_issue(self, issue_comment):
        expected = pytz.UTC.localize(datetime(2016, 10, 24, 18, 53, 10))
        assert issue_comment.updated_at == expected

    def test_pr(self, pull_request_review):
        expected = pytz.UTC.localize(datetime(2016, 10, 24, 18, 19, 44))
        assert pull_request_review.updated_at == expected
