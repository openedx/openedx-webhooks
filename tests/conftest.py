
import os
import os.path
import re
import unittest.mock as mock

import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session

import openedx_webhooks
import openedx_webhooks.utils

from .fake_github import FakeGitHub
from .fake_jira import FakeJira


@pytest.yield_fixture
def requests_mocker():
    """Make requests_mock available as a fixture."""
    mocker = requests_mock.Mocker(real_http=False, case_sensitive=True)
    mocker.start()
    try:
        yield mocker
    finally:
        mocker.stop()


@pytest.fixture
def fake_repo_data(requests_mocker):
    def _repo_data_callback(request, _):
        """Read repo_data data from local data."""
        filename = request.path.split("/")[-1]
        repo_data_dir = os.path.join(os.path.dirname(__file__), "repo_data")
        with open(os.path.join(repo_data_dir, filename)) as data:
            return data.read()

    RAW_HOST = "raw.githubusercontent.com"
    requests_mocker.get(
        re.compile(f"https://{RAW_HOST}/edx/repo-tools-data/master/"),
        text=_repo_data_callback,
    )


class FakeBlueprint:
    def __init__(self, token):
        self.token = token
        self.client_id = "FooId"
        self.client_secret = "FooSecret"


@pytest.fixture
def mock_github_bp(mocker):
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


@pytest.fixture
def fake_github(requests_mocker, mock_github_bp, fake_repo_data):
    the_fake_github = FakeGitHub(login="webhook-bot")
    the_fake_github.install_mocks(requests_mocker)
    return the_fake_github


@pytest.fixture
def mock_jira_bp(mocker):
    token = {"access_token": "faketoken", "token_type": "bearer"}
    jira_session = OAuth2Session(
        base_url="https://openedx.atlassian.net/",
        blueprint=FakeBlueprint(token),
    )
    mocker.patch("flask_dance.contrib.jira.jira", jira_session)
    mock_bp = mock.Mock()
    mock_bp.session = jira_session
    mocker.patch("openedx_webhooks.tasks.github.jira_bp", mock_bp)


@pytest.fixture
def fake_jira(mock_jira_bp, requests_mocker):
    the_fake_jira = FakeJira()
    the_fake_jira.install_mocks(requests_mocker)
    return the_fake_jira


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
