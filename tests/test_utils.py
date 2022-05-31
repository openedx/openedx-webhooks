"""Tests of code in utils.py"""

import re

import pytest

from openedx_webhooks.utils import graphql_query, text_summary


@pytest.mark.parametrize("args, summary", [
    (["Hello"], "Hello"),
    ([""], ""),
    (["lorem ipsum quia dolor sit amet consecte"], "lorem ipsum quia dolor sit amet consecte"),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, sed quia non numquam eius modi tempora incidunt."],
      "lorem ipsum quia d...i tempora incidunt."),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, sed quia non numquam eius modi tempora incidunt.", 80],
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
