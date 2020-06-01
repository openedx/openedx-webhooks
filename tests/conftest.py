
import os
import os.path
import random
import re
import unittest.mock as mock
from datetime import datetime

import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session

import openedx_webhooks
import openedx_webhooks.utils


@pytest.yield_fixture
def requests_mocker():
    """Make requests_mock available as a fixture."""
    mocker = requests_mock.Mocker(real_http=False)
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


class MockGitHub:
    """A mock implementation of the GitHub API."""

    WEBHOOK_BOT_NAME = "the-webhook-bot"

    def __init__(self, requests_mocker):
        self.requests_mocker = requests_mocker
        self.requests_mocker.get(
            "https://api.github.com/user",
            json={"login": self.WEBHOOK_BOT_NAME}
        )

        self.requests_mocker.get(
            re.compile("https://raw.githubusercontent.com/edx/repo-tools-data/master/"),
            text=self._repo_data_callback,
        )

    def _repo_data_callback(self, request, _):
        """Read repo_data data from local data."""
        repo_data_dir = os.path.join(os.path.dirname(__file__), "repo_data")
        filename = request.path.split("/")[-1]
        with open(os.path.join(repo_data_dir, filename)) as data:
            return data.read()

    def make_pull_request(
        self,
        user, title="generic title", body="generic body", number=1,
        base_repo_name="edx/edx-platform", head_repo_name=None,
        base_ref="master", head_ref="patch-1", user_type="User",
        created_at=None
    ):
        """Create fake pull request data."""
        # This should really use a framework like factory_boy.
        created_at = created_at or datetime.now().replace(microsecond=0)
        if head_repo_name is None:
            head_repo_name = f"{user}/edx-platform"
        return {
            "user": {
                "login": user,
                "type": user_type,
                "url": f"https://api.github.com/users/{user}",
            },
            "number": number,
            "title": title,
            "body": body,
            "created_at": created_at.isoformat(),
            "head": {
                "repo": {
                    "full_name": head_repo_name,
                },
                "ref": head_ref,
            },
            "base": {
                "repo": {
                    "full_name": base_repo_name,
                },
                "ref": base_ref,
            },
            "html_url": f"https://github.com/{base_repo_name}/pull/{number}",
        }

    def mock_comments(self, pr, comments):
        """Mock the requests to get comments on a PR."""
        self.requests_mocker.get(
            "https://api.github.com/repos/{repo}/issues/{num}/comments".format(
                repo=pr["base"]["repo"]["full_name"],
                num=pr["number"],
            ),
            json=comments,
        )



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
    mock_github = MockGitHub(requests_mocker)
    return mock_github


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
            json=self._new_issue_callback,
        )
        self.created_issues = []

    def _new_issue_callback(self, request, _):
        """Responds to the API endpoint for creating new issues."""
        project = request.json()["fields"]["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        self.created_issues.append(key)
        return {"key": key}


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
    mock_jira = MockJira(requests_mocker)
    return mock_jira


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
