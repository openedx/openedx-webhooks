"""Tests of pull_request_changed_task retrying when GitHub rate-limits us."""

from datetime import datetime, timezone

import pytest
from celery.exceptions import Retry
from freezegun import freeze_time

import openedx_webhooks
from openedx_webhooks.cla_check import CLA_CONTEXT, CLA_STATUS_GOOD
from openedx_webhooks.tasks.github import pull_request_changed_task
from openedx_webhooks.utils import RateLimited

from .helpers import RATE_LIMIT_BODY

RESET_AT = 1700000000


class FailStatusPost:
    """
    Middleware for FakeGitHub: the first POST of a commit status fails.
    """
    def __init__(self, status_code, body, headers=None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        self.tripped = False

    def middleware(self, request, context):
        if self.tripped or request.method != "POST" or "/statuses/" not in request.path:
            return None
        self.tripped = True
        context.status_code = self.status_code
        context.headers.update(self.headers)
        return self.body


@pytest.mark.parametrize("now, countdown", [
    (RESET_AT - 100, 105),
    (RESET_AT + 100, 5),
])
def test_rate_limited_task_retries(fake_github, requests_mocker, mocker, now, countdown):
    fake_github.add_middleware(FailStatusPost(403, RATE_LIMIT_BODY, {
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(RESET_AT),
    }).middleware)
    pr = fake_github.make_pull_request("openedx", "some-code", user="tusbar")
    retry = mocker.patch.object(pull_request_changed_task, "retry", side_effect=Retry("later"))

    with freeze_time(datetime.fromtimestamp(now, timezone.utc)):
        with pytest.raises(Retry):
            pull_request_changed_task(pr.as_json())

    retry.assert_called_once()
    kwargs = retry.call_args.kwargs
    assert kwargs["countdown"] == countdown
    assert isinstance(kwargs["exc"], RateLimited)
    assert kwargs["exc"].reset_at == RESET_AT
    # The refused POST was the last request: nothing else was tried against
    # the exhausted budget.
    assert requests_mocker.last_request.method == "POST"
    assert "/statuses/" in requests_mocker.last_request.path
    assert pr.status(CLA_CONTEXT) is None
    assert len(pr.list_comments()) == 0

    # The task is idempotent: running it again does the work.
    pull_request_changed_task(pr.as_json())
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    assert len(pr.list_comments()) == 1


def test_other_failures_do_not_retry(fake_github, mocker):
    fake_github.add_middleware(FailStatusPost(500, {"message": "Server Error"}).middleware)
    pr = fake_github.make_pull_request("openedx", user="nedbat")
    retry = mocker.patch.object(pull_request_changed_task, "retry", side_effect=Retry("later"))

    with pytest.raises(ExceptionGroup) as excinfo:
        pull_request_changed_task(pr.as_json())

    retry.assert_not_called()
    assert "Server Error" in str(excinfo.value.exceptions[0])


def test_task_wrapper_lets_retry_through():
    """
    The ContextTask base class turns exceptions into traceback strings, but
    Retry is how Task.retry() talks to the worker, so it must get through.
    """
    celery = openedx_webhooks.celery
    assert celery.Task.__name__ == "ContextTask"

    @celery.task(bind=True, name="tests.retrying")
    def retrying(self):
        raise self.retry(countdown=1)

    @celery.task(name="tests.failing")
    def failing():
        raise ValueError("boom")

    with pytest.raises(Retry):
        retrying()

    assert "ValueError: boom" in failing()
