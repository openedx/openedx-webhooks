"""Tests of code in utils.py"""

import hashlib
import hmac
import json
import re

import pytest
from freezegun import freeze_time

from openedx_webhooks.utils import (
    clear_memoized_values,
    graphql_query,
    is_valid_payload,
    memoize,
    memoize_timed,
    text_summary,
)


@pytest.mark.parametrize("args, summary", [
    (["Hello"], "Hello"),
    ([""], ""),
    (["lorem ipsum quia dolor sit amet consecte"], "lorem ipsum quia dolor sit amet consecte"),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, sed quia non numquam eius modi tempora incidunt."],
      "lorem ipsum quia d...i tempora incidunt."),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, quia non numquam eius modi tempora incidunt.", 80],
      "lorem ipsum quia dolor sit amet consec...non numquam eius modi tempora incidunt."),
])
def test_text_summary(args, summary):
    assert summary == text_summary(*args)


def test_good_graphql_query(requests_mocker):
    requests_mocker.post(
        "https://api.github.com/graphql",
        json={"data": {"name": "Something", "id": 123}},
    )
    data = graphql_query("query Something {}")
    assert requests_mocker.request_history[0].json() == {
        "query": "query Something {}",
        "variables": {},
    }
    assert data == {"name": "Something", "id": 123}


def test_bad_graphql_query(requests_mocker):
    requests_mocker.post(
        "https://api.github.com/graphql",
        json={"errors": ["You blew it"]},
    )
    with pytest.raises(Exception, match=re.escape("GraphQL error: {'errors': ['You blew it']}")):
        graphql_query("query Something {}", variables={"a":1, "b": 2})


def _make_signature(secret, payload):
    """Compute a signature from a secret and a payload."""
    return (
        'sha1=' +
        hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha1).hexdigest()
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


def test_memoize():
    vals = []
    @memoize
    def add_to_vals(x):
        vals.append(x)
        return x * 2

    with freeze_time("2020-05-14 09:00:00"):
        assert add_to_vals(10) == 20
        assert vals == [10]
        assert add_to_vals(10) == 20
        assert vals == [10]
        assert add_to_vals(15) == 30
        assert vals == [10, 15]

    with freeze_time("2020-05-14 20:00:00"):
        assert add_to_vals(10) == 20
        assert add_to_vals(15) == 30
        assert vals == [10, 15]

def test_memoize_timed():
    vals = []
    @memoize_timed(minutes=10)
    def add_to_vals_timed(x):
        vals.append(x)
        return x * 2

    with freeze_time("2020-05-14 09:00:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10]
        assert add_to_vals_timed(10) == 20
        assert vals == [10]
        assert add_to_vals_timed(15) == 30
        assert vals == [10, 15]

    with freeze_time("2020-05-14 09:05:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10, 15]
        assert add_to_vals_timed(20) == 40
        assert vals == [10, 15, 20]

    with freeze_time("2020-05-14 09:11:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10, 15, 20, 10]

def test_clear_memoized_values():
    vals = []
    @memoize
    def add_to_vals(x):
        vals.append(x)
        return x * 2

    @memoize_timed(minutes=10)
    def add_to_vals_timed(x):
        vals.append(x)
        return x * 2

    assert add_to_vals(10) == 20
    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20]

    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20]

    clear_memoized_values()

    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20, 15, 20]
