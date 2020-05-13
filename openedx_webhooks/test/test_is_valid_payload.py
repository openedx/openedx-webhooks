import hmac
import json
from hashlib import sha1

import pytest

from openedx_webhooks.utils import is_valid_payload


def _make_signature(secret, payload):
    return (
        'sha1=' +
        hmac.new(secret.encode(), msg=payload, digestmod=sha1).hexdigest()
    )


@pytest.fixture
def secret1():
    return 'top secret'


@pytest.fixture
def secret2():
    return 'not so top secret'


@pytest.fixture
def payload():
    return json.dumps('payload').encode("utf8")


@pytest.fixture
def signature(secret1, payload):
    return _make_signature(secret1, payload)


def test_everything_matches(secret1, signature, payload):
    assert is_valid_payload(secret1, signature, payload) is True


def test_mismatched_signature(secret1, secret2, payload):
    wrong_signature = _make_signature(secret2, payload)
    assert is_valid_payload(secret1, wrong_signature, payload) is False


def test_bad_secret(secret2, signature, payload):
    assert is_valid_payload(secret2, signature, payload) is False


def test_mismatched_payload(secret1, signature):
    wrong_payload = json.dumps('x').encode("utf8")
    assert is_valid_payload(secret1, signature, wrong_payload) is False
