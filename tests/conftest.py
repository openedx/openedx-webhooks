import os
import pytest
import betamax
import openedx_webhooks

if not os.path.exists('tests/cassettes'):
    os.makedirs('tests/cassettes')

record_mode = 'none' if os.environ.get('CI') else 'once'

with betamax.Betamax.configure() as config:
    config.cassette_library_dir = 'tests/cassettes/'
    config.default_cassette_options['record_mode'] = record_mode


@pytest.fixture
def app(request):
    return openedx_webhooks.create_app(config="testing")
