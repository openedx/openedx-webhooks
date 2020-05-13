import base64
import os
import os.path
import re
import unittest.mock as mock

import betamax
import pytest
import requests_mock
from flask_dance.consumer.requests import OAuth2Session
from requests.packages.urllib3.response import is_fp_closed

import openedx_webhooks
import openedx_webhooks.utils

if not os.path.exists('tests/cassettes'):
    os.makedirs('tests/cassettes')

record_mode = 'none' if os.environ.get('CI') else 'once'

with betamax.Betamax.configure() as config:
    config.cassette_library_dir = 'tests/cassettes/'
    config.default_cassette_options['record_mode'] = record_mode
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        config.define_cassette_placeholder(
            '<GITHUB-TOKEN>',
            base64.b64encode(github_token.encode('utf-8'))
        )
        config.define_cassette_placeholder(
            '<GITHUB-TOKEN>',
            github_token.encode('utf-8')
        )

class FakeBlueprint(object):
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
def betamax_github_session(request, github_session):
    """
    Like Betamax's built-in `betamax_session`, but with GitHub auth set up.
    """
    cassette_name = ''

    if request.module is not None:
        cassette_name += request.module.__name__ + '.'

    if request.cls is not None:
        cassette_name += request.cls.__name__ + '.'

    cassette_name += request.function.__name__

    recorder = betamax.Betamax(github_session)
    recorder.use_cassette(cassette_name)
    recorder.start()
    request.addfinalizer(recorder.stop)
    return github_session


@pytest.fixture
def mock_github(mocker, betamax_github_session):
    mocker.patch("flask_dance.contrib.github.github", betamax_github_session)
    mock_bp = mock.Mock()
    mock_bp.session = betamax_github_session
    mocker.patch("openedx_webhooks.info.github_bp", mock_bp)
    mocker.patch("openedx_webhooks.tasks.github.github_bp", mock_bp)
    return betamax_github_session


@pytest.yield_fixture
def requests_mocker():
    mocker = requests_mock.Mocker(real_http=True)
    mocker.start()
    yield mocker
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
