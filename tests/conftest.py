import os
import os.path
import re
import unittest.mock as mock
from typing import Dict

import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session

import openedx_webhooks
import openedx_webhooks.utils
import openedx_webhooks.info

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

    requests_mocker.get(
        re.compile(f"https://raw.githubusercontent.com/edx/repo-tools-data/master/"),
        text=_repo_data_callback,
    )


@pytest.yield_fixture(scope="session", autouse=True)
def hard_cache_repotools_yaml_files(session_mocker):
    """
    Reading yaml files is slowish, and these data files don't change.
    Read them once per test run, and re-use the data.
    """
    real_read_repotools_yaml_file = openedx_webhooks.info._read_repotools_yaml_file
    repotools_files: Dict[str, Dict] = {}
    def new_read_repotools_yaml_file(filename):
        data = repotools_files.get(filename)
        if data is None:
            data = real_read_repotools_yaml_file(filename)
            repotools_files[filename] = data
        return data
    session_mocker.patch("openedx_webhooks.info._read_repotools_yaml_file", new_read_repotools_yaml_file)


class FakeBlueprint:
    def __init__(self, token):
        self.token = token
        self.client_id = "FooId"
        self.client_secret = "FooSecret"


def pytest_addoption(parser):
    parser.addoption(
        "--percent-404",
        action="store",
        help="What percent of HTTP requests should fail with a 404",
        default="0",
    )

@pytest.fixture
def fake_github(pytestconfig, mocker, requests_mocker, fake_repo_data):
    fraction_404 = float(pytestconfig.getoption("percent_404")) / 100.0
    the_fake_github = FakeGitHub(login="webhook-bot", fraction_404=fraction_404)
    the_fake_github.install_mocks(requests_mocker)
    if fraction_404:
        # Make the retry sleep a no-op so it won't slow the tests.
        mocker.patch("openedx_webhooks.utils.retry_sleep", lambda x: None)
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
    mocker.patch("openedx_webhooks.oauth.jira_bp", mock_bp)


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


@pytest.fixture(params=[False, True])
def is_merged(request):
    """Makes tests try both merged and closed pull requests."""
    return request.param


