from datetime import datetime

import pytest
import pytz
from jira import Issue

import openedx_webhooks
from openedx_webhooks.github.dispatcher.actions.github_activity import run


@pytest.fixture(autouse=True)
def patch_find_issues(mocker):
    issue = mocker.Mock(spec=Issue)
    issue.id = '123'
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.github_activity'
        '.find_issues_for_pull_request'
    ), return_value=[issue])


@pytest.fixture(autouse=True)
def patch_update_latest_github_activity(mocker):
    mocker.patch(
        'openedx_webhooks.github.dispatcher.actions.github_activity'
        '.update_latest_github_activity'
    )


class TestProcess:
    def _test_user(
            self, github_client, jira_client, _payload, login, is_edx_user
    ):
        payload = _payload.copy()
        payload['sender']['login'] = login
        run(github_client, jira_client, 'issue_comment', payload)

        func = (
            openedx_webhooks.github.dispatcher.actions.github_activity
            .find_issues_for_pull_request
        )
        func.assert_called_once_with(
            jira_client, 'https://example.com/issue/1'
        )

        func = (
            openedx_webhooks.github.dispatcher.actions.github_activity
            .update_latest_github_activity
        )
        dt = pytz.UTC.localize(datetime(2016, 10, 24, 18, 53, 10))
        func.assert_called_once_with(
            jira_client, '123', 'issue_comment: edited', login, dt, is_edx_user
        )

    def test_robot(self, github_client, jira_client):
        payload = {
            'sender': {
                'login': 'robot',
            },
        }
        run(github_client, jira_client, 'type', payload)
        func = (
            openedx_webhooks.github.dispatcher.actions.github_activity
            .find_issues_for_pull_request
        )
        func.assert_not_called()

        func = (
            openedx_webhooks.github.dispatcher.actions.github_activity
            .update_latest_github_activity)
        func.assert_not_called()

    def test_unknown_user(
            self, github_client, jira_client, issue_comment_payload
    ):
        self._test_user(
            github_client, jira_client, issue_comment_payload, 'unknown',
            is_edx_user=False
        )

    def test_edx_user(self, github_client, jira_client, issue_comment_payload):
        self._test_user(
            github_client, jira_client, issue_comment_payload,
            'active-edx-person', is_edx_user=True
        )
