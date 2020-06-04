
import os
import unittest.mock as mock

import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session

import openedx_webhooks
import openedx_webhooks.utils

from .mock_github import MockGitHub
from .mock_jira import MockJira


@pytest.yield_fixture
def requests_mocker():
    """Make requests_mock available as a fixture."""
    mocker = requests_mock.Mocker(real_http=False, case_sensitive=True)
    mocker.start()
    try:
        yield mocker
    finally:
        mocker.stop()


class FakeBlueprint:
    def __init__(self, token):
        self.token = token
        self.client_id = "FooId"
        self.client_secret = "FooSecret"


@pytest.fixture
def mock_github(mocker, requests_mocker):
    github_token = os.environ.get("GITHUB_TOKEN", "faketoken")
    token = {"access_token": github_token, "token_type": "bearer"}
    github_session = OAuth2Session(
        base_url="https://api.github.com/",
        blueprint=FakeBlueprint(token),
    )
    mocker.patch("flask_dance.contrib.github.github", github_session)
    mock_bp = mock.Mock()
    mock_bp.session = github_session
    mocker.patch("openedx_webhooks.info.github_bp", mock_bp)
    mocker.patch("openedx_webhooks.tasks.github.github_bp", mock_bp)
    the_mock_github = MockGitHub(requests_mocker)
    return the_mock_github


@pytest.fixture
def mock_jira(mocker, requests_mocker):
    token = {"access_token": "faketoken", "token_type": "bearer"}
    jira_session = OAuth2Session(
        base_url="https://openedx.atlassian.net/",
        blueprint=FakeBlueprint(token),
    )
    mocker.patch("flask_dance.contrib.jira.jira", jira_session)
    mock_bp = mock.Mock()
    mock_bp.session = jira_session
    mocker.patch("openedx_webhooks.tasks.github.jira_bp", mock_bp)
    the_mock_jira = MockJira(requests_mocker)
    return the_mock_jira


@pytest.fixture
def app():
    return openedx_webhooks.create_app(config="testing")


@pytest.fixture
def reqctx(app):
    """
    Needed to make the app understand it's running under HTTPS
    """
    return app.test_request_context(
        '/', base_url="https://openedx-webhooks.herokuapp.com"
    )


@pytest.fixture(autouse=True)
def reset_all_memoized_functions():
    """Clears the values cached by @memoize before each test. Applied automatically."""
    openedx_webhooks.utils.clear_memoized_values()
