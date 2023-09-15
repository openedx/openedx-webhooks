"""Tests of task/github.py:pull_request_changed for closing pull requests."""

import pytest

from openedx_webhooks.bot_comments import (
    BotComment,
    is_comment_kind,
)
from openedx_webhooks.tasks.github import pull_request_changed
from .helpers import check_issue_link_in_markdown, random_text

# These tests should run when we want to test flaky GitHub behavior.
pytestmark = pytest.mark.flaky_github


def test_internal_pr_closed(is_merged, fake_github, fake_jira):
    pr = fake_github.make_pull_request("openedx", user="nedbat", state="closed", merged=is_merged)
    pr.add_comment(user="nedbat", body="This is great")
    pr.add_comment(user="feanil", body="Eh, it's ok")
    pull_request_changed(pr.as_json())

    # No Jira issue for this PR, so we should have never talked to Jira.
    assert len(fake_jira.requests_made()) == 0


@pytest.fixture
def closed_pull_request(is_merged, fake_github, fake_jira):
    """
    Create a closed pull request and an issue key for it.

    Returns (pr, issue_key)
    """
    pr = fake_github.make_pull_request(
        user="tusbar",
        title=random_text(),
        )
    issue_key, _ = pull_request_changed(pr.as_json())

    assert issue_key is None
    pr.add_comment(user="nedbat", body="Please make some changes")
    pr.add_comment(user="tusbar", body="OK, I made the changes")
    pr.close(merge=is_merged)

    fake_jira.reset_mock()

    return pr, issue_key


def test_external_pr_closed(fake_jira, closed_pull_request):
    pr, _ = closed_pull_request
    pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    body = pr_comments[-1].body
    assert "survey" in body
    assert is_comment_kind(BotComment.SURVEY, body)


def test_external_pr_closed_but_issue_deleted(fake_jira, closed_pull_request):
    # A closing pull request, but its Jira issue has been deleted.
    pr, old_issue_key = closed_pull_request

    issue_id, anything_happened = pull_request_changed(pr.as_json())

    assert issue_id is None
    assert anything_happened

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 4    # 1 welcome, closed_pull_request makes two, 1 survey
    # We leave the old issue id in the comment.
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, old_issue_key)


def test_external_pr_closed_but_issue_in_status(fake_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request is already in the
    # status we want to move it to.
    pr, _ = closed_pull_request

    pull_request_changed(pr.as_json())

    # Issue is already correct, so nothing was transitioned.
    assert fake_jira.requests_made(method="POST") == []


def test_cc_pr_closed(fake_github, fake_jira, is_merged):
    # When a core committer merges a pull request, ping the champions.
    # But when it's closed without merging, no ping.
    # Use body=None here to test missing bodies also.
    pr = fake_github.make_pull_request(user="felipemontoya", owner="openedx", repo="edx-platform", body=None)
    pull_request_changed(pr.as_json())

    pr.close(merge=is_merged)
    pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 2    # 1 welcome, 1 survey

    # Processing it again won't change anything.
    pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 2    # 1 welcome, 1 survey
