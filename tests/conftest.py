import os
import base64
import pytest
import betamax
import responses as responses_module
from requests_oauthlib import OAuth2Session
from flask_dance.contrib.github import make_github_blueprint
import openedx_webhooks
from raven.contrib.flask import make_client as make_sentry_client
from raven.base import DummyClient

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


@pytest.fixture
def github_session(request):
    """
    Like Betamax's built-in `betamax_session`, but with GitHub auth set up.
    """
    cassette_name = ''

    if request.module is not None:
        cassette_name += request.module.__name__ + '.'

    if request.cls is not None:
        cassette_name += request.cls.__name__ + '.'

    cassette_name += request.function.__name__

    github_token = os.environ.get("GITHUB_TOKEN", "faketoken")
    token = {"access_token": github_token, "token_type": "bearer"}
    session = OAuth2Session(token=token)
    recorder = betamax.Betamax(session)
    recorder.use_cassette(cassette_name)
    recorder.start()
    request.addfinalizer(recorder.stop)
    return session


@pytest.yield_fixture
def responses():
    responses_module.mock.start()
    yield responses_module.mock
    responses_module.mock.stop()
    responses_module.mock.reset()


@pytest.fixture
def app(request):
    _app = openedx_webhooks.create_app(config="testing")
    # use a dummy Sentry session, so that we don't actually
    # contact getsentry.com when running tests
    _app.extensions['sentry'].client = make_sentry_client(DummyClient, app=_app)
    # and return!
    return _app


@pytest.fixture
def reqctx(app):
    """
    Needed to make the app understand it's running under HTTPS
    """
    return app.test_request_context(
        '/', base_url="https://openedx-webhooks.herokuapp.com"
    )
