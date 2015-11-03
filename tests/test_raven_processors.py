from __future__ import unicode_literals
import pytest


def test_requests_processor(app, mocker, betamax_session):
    # setup sentry client
    sentry = app.extensions['sentry']
    mocker.patch.object(sentry.client, "send")
    mocker.patch.object(sentry.client, "is_enabled", return_value=True)

    # throw an HTTPError with requests
    response = betamax_session.get("http://httpbin.org/status/404")
    try:
        response.raise_for_status()
    except Exception as exc:
        sentry.captureException()

    # assert on what the sentry client tried to send to getsentry.com
    assert sentry.client.send.called
    sentry_args = sentry.client.send.call_args[1]
    serialized_url = sentry.client.transform("http://httpbin.org/status/404")
    assert sentry_args['extra']['request_url'] == serialized_url

