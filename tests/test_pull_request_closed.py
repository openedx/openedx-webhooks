"""Tests of task/github.py:pull_request_closed."""

import pytest

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    pull_request_closed,
)


@pytest.fixture(params=[False, True])
def merged(request):
    """Makes tests try both merged and closed pull requests."""
    return request.param


def test_internal_pr_merged(merged, reqctx, mock_github, mock_jira):
    pr = mock_github.make_closed_pull_request(user="nedbat", merged=merged)
    mock_github.mock_comments(pr, [
        {"user": {"login": "nedbat"}, "body": "This is great"},
        {"user": {"login": "feanil"}, "body": "Eh, it's ok"},
    ])
    with reqctx:
        pull_request_closed(pr)

    # No Jira issue for this PR, so we should have never talked to Jira.
    assert len(mock_jira.request_history()) == 0


@pytest.fixture
def closed_pull_request(merged, reqctx, mock_github, mock_jira):
    """
    Create a closed pull request.

    Returns (pr, issue)
    """
    pr = mock_github.make_closed_pull_request(user="tusbar", merged=merged)
    issue = mock_jira.make_issue()
    with reqctx:
        bot_comment = github_community_pr_comment(pr, jira_issue=issue)
    comments_data = [
        {"user": {"login": mock_github.WEBHOOK_BOT_NAME}, "body": bot_comment},
        {"user": {"login": "nedbat"}, "body": "Please make some changes"},
        {"user": {"login": "tusbar"}, "body": "OK, I made the changes"},
    ]
    mock_github.mock_comments(pr, comments_data)
    return pr, issue


def test_external_pr_merged(merged, reqctx, mock_jira, closed_pull_request):
    pr, issue = closed_pull_request
    transitions_post = mock_jira.transitions_post(issue)

    with reqctx:
        pull_request_closed(pr)

    # We moved the Jira issue to Merged or Rejected.
    transition_id = mock_jira.TRANSITIONS["Merged" if merged else "Rejected"]
    assert transitions_post.request_history[0].json() == {
        "transition": {"id": transition_id}
    }


def test_external_pr_merged_but_issue_deleted(merged, reqctx, mock_jira, closed_pull_request):
    pr, issue = closed_pull_request
    transitions_post = mock_jira.transitions_post(issue)
    mock_jira.delete_issue(issue)

    with reqctx:
        pull_request_closed(pr)

    # Issue was deleted, so nothing was transitioned.
    assert len(transitions_post.request_history) == 0


def test_external_pr_merged_but_issue_in_status(merged, reqctx, mock_jira, closed_pull_request):
    pr, issue = closed_pull_request
    transitions_post = mock_jira.transitions_post(issue)
    mock_jira.set_issue_status(issue, "Merged" if merged else "Rejected")

    with reqctx:
        pull_request_closed(pr)

    # Issue is already correct, so nothing was transitioned.
    assert len(transitions_post.request_history) == 0
