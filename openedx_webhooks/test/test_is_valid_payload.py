"""Tests of is_valid_payload."""

import hmac
import json
from hashlib import sha1

import pytest

from openedx_webhooks.utils import is_valid_payload


def _make_signature(secret, payload):
    """Compte a signature from a secret and a payload."""
    return (
        'sha1=' +
        hmac.new(secret.encode(), msg=payload, digestmod=sha1).hexdigest()
    )


SECRET1 = "top secret"
SECRET2 = "not so top secret"
PAYLOAD = json.dumps('payload').encode("utf8")


def test_everything_matches():
    signature = _make_signature(SECRET1, PAYLOAD)
    assert is_valid_payload(SECRET1, signature, PAYLOAD) is True


def test_mismatched_signature():
    wrong_signature = _make_signature(SECRET2, PAYLOAD)
    assert is_valid_payload(SECRET1, wrong_signature, PAYLOAD) is False


def test_bad_secret():
    signature = _make_signature(SECRET1, PAYLOAD)
    assert is_valid_payload(SECRET2, signature, PAYLOAD) is False


def test_mismatched_payload():
    signature = _make_signature(SECRET1, PAYLOAD)
    wrong_payload = json.dumps('x').encode("utf8")
    assert is_valid_payload(SECRET1, signature, wrong_payload) is False
