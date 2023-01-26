"""Helpers for tests."""

import contextlib
import random
import re
import unittest.mock
from typing import Optional


def check_good_markdown(text: str) -> None:
    """
    Make some checks of Markdown text.

    These are meant to catch mistakes in templates or code producing Markdown.

    Returns:
        Nothing.  Will raise an exception with a failure message if something
        is wrong.
    """
    if text.startswith((" ", "\n", "\t")):
        raise ValueError(f"Markdown shouldn't start with whitespace: {text!r}")

    # HTML comments must be on a line by themselves or the Markdown won't
    # render properly.
    if re.search(".<!--", text):
        raise ValueError(f"Markdown shouldn't have an HTML comment in the middle of a line: {text!r}")
    if re.search("-->.", text):
        raise ValueError(f"Markdown shouldn't have an HTML comment with following text: {text!r}")

    # We should never link to something called "None".
    if re.search(r"\[None\]\(", text):
        raise ValueError(f"Markdown has a link to None: {text!r}")

    # We should never link to a url with None as a component.
    if re.search(r"\]\([^)]*/None[/)]", text):
        raise ValueError(f"Markdown has a link to a None url: {text!r}")


def check_issue_link_in_markdown(text: str, issue_id: str) -> None:
    """
    Check that `text` has properly links to `issue_id`.

    Args:
        text: Markdown text.
        issue_id: A JIRA issue id, which can be None.

    Returns:
        Nothing.  Will raise an exception with a failure message if something
        is wrong.
    """
    if issue_id is not None:
        jira_link = "[{id}](https://test.atlassian.net/browse/{id})".format(id=issue_id)
        assert jira_link in text, f"Markdown is missing a link to {issue_id}"
    else:
        assert "/browse/" not in text, "Markdown links to JIRA when we have no issue id"


def random_text() -> str:
    """
    Generate a random text string.
    """
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    words = []
    for _ in range(random.randint(4, 10)):
        words.append("".join(random.choice(alphabet) for _ in range(random.randrange(1, 6))))
    return " ".join(words)


def check_good_graphql(text: str) -> None:
    """
    Do some simple checks of a GraphQL query.

    Returns:
        Nothing.  Will raise an exception with a failure message if something
        is wrong.
    """
    # Remove all comments.
    code = re.sub(r"(?m)#.*$", "", text)

    # The first word should be "query" or "mutation".
    first = code.split(None, 1)[0]
    if first not in {"query", "mutation"}:
        raise ValueError(f"GraphQL query starts with wrong word: {text!r}")

    # Parens should be balanced.
    stack = []
    pairs = {")": "(", "}": "{", "]": "["}
    for ch in code:
        if ch in pairs.values():
            stack.append(ch)
        elif ch in pairs.keys():            # pylint: disable=consider-iterating-dictionary
            if not stack or stack[-1] != pairs[ch]:
                raise ValueError(f"GraphQL query has unbalanced parens: {text!r}")
            stack.pop()
    if stack:
        raise ValueError(f"GraphQL query has unbalanced parens: {text!r}")


@contextlib.contextmanager
def jira_server(server: Optional[str]):
    """
    Use a particular JIRA_SERVER for a chunk of code.

    Args:
        server: a string like "https://myjira.atlassian.net", or None for no
            JIRA server.

    """
    with unittest.mock.patch("openedx_webhooks.settings.JIRA_SERVER", server):
        yield
