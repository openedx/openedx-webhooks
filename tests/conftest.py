import base64
import os
import os.path
import random
import re
import unittest.mock as mock

import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session
from requests.packages.urllib3.response import is_fp_closed

import openedx_webhooks
import openedx_webhooks.utils


class FakeBlueprint:
    def __init__(self, token):
        self.token = token
        self.client_id = "FooId"
        self.client_secret = "FooSecret"

@pytest.fixture
def github_session():
    github_token = os.environ.get("GITHUB_TOKEN", "faketoken")
    token = {"access_token": github_token, "token_type": "bearer"}
    session = OAuth2Session(
        base_url="https://api.github.com/",
        blueprint=FakeBlueprint(token),
    )
    return session

@pytest.fixture
def jira_session():
    token = {"access_token": "faketoken", "token_type": "bearer"}
    session = OAuth2Session(
        base_url="https://openedx.atlassian.net/",
        blueprint=FakeBlueprint(token),
    )
    return session


@pytest.fixture
def mock_github(mocker, github_session):
    mocker.patch("flask_dance.contrib.github.github", github_session)
    mock_bp = mock.Mock()
    mock_bp.session = github_session
    mocker.patch("openedx_webhooks.info.github_bp", mock_bp)
    mocker.patch("openedx_webhooks.tasks.github.github_bp", mock_bp)
    return github_session


class MockJira:
    """A mock implementation of the Jira API."""
    CONTRIBUTOR_NAME = "custom_101"
    CUSTOMER = "custom_102"
    PR_NUMBER = "custom_103"
    REPO = "custom_104"
    URL = "customfield_10904"   # This one is hard-coded

    def __init__(self, requests_mocker):
        requests_mocker.get(
            "https://openedx.atlassian.net/rest/api/2/field",
            json=[
                {"id": self.CONTRIBUTOR_NAME, "name": "Contributor Name", "custom": True},
                {"id": self.CUSTOMER, "name": "Customer", "custom": True},
                {"id": self.PR_NUMBER, "name": "PR Number", "custom": True},
                {"id": self.REPO, "name": "Repo", "custom": True},
                {"id": self.URL, "name": "URL", "custom": True},
            ]
        )
        self.new_issue_post = requests_mocker.post(
            "https://openedx.atlassian.net/rest/api/2/issue",
            json=self.new_issue_callback,
        )
        self.created_issues = []

    def new_issue_callback(self, request, _):
        """Responds to the API endpoint for creating new issues."""
        project = request.json()["fields"]["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        self.created_issues.append(key)
        return {"key": key}


@pytest.fixture
def mock_jira(mocker, jira_session, requests_mocker):
    mocker.patch("flask_dance.contrib.jira.jira", jira_session)
    mock_bp = mock.Mock()
    mock_bp.session = jira_session
    mocker.patch("openedx_webhooks.tasks.github.jira_bp", mock_bp)
    mock_jira = MockJira(requests_mocker)
    return mock_jira


@pytest.yield_fixture
def requests_mocker():
    mocker = requests_mock.Mocker(real_http=False)
    mocker.start()
    try:
        yield mocker
    finally:
        mocker.stop()


@pytest.fixture(autouse=True)
def fake_repo_data(requests_mocker):
    """Read repo_data data from local data.  Applied automatically."""
    repo_data_dir = os.path.join(os.path.dirname(__file__), "repo_data")
    def repo_data_callback(request, context):
        context.status_code = 200
        filename = request.path.split("/")[-1]
        with open(os.path.join(repo_data_dir, filename)) as data:
            return data.read()

    requests_mocker.get(
        re.compile("https://raw.githubusercontent.com/edx/repo-tools-data/master/"),
        text=repo_data_callback,
    )

@pytest.fixture(autouse=True)
def fake_bot_whoami(requests_mocker):
    """If we ask who we are, we are the bot."""
    requests_mocker.get(
        "https://api.github.com/user",
        json={
            "login": "the-bot",
        }
    )


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
