"""Tests of task/github.py:pull_request_closed."""

import pytest

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    pull_request_closed,
)


@pytest.mark.parametrize("merged", [False, True])
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


@pytest.mark.parametrize("merged", [False, True])
def test_external_pr_merged(merged, reqctx, mock_github, mock_jira):
    pr = mock_github.make_closed_pull_request(user="tusbar", merged=merged)
    issue = mock_jira.make_issue()
    with reqctx:
        comment = github_community_pr_comment(pr, jira_issue=issue)
    comment_data = {
        "user": {"login": mock_github.WEBHOOK_BOT_NAME},
        "body": comment,
    }
    mock_github.mock_comments(pr, [comment_data])
    transitions_post = mock_jira.transitions_post(issue)

    with reqctx:
        pull_request_closed(pr)

    # We moved the Jira issue to Merged or Rejected.
    transition_id = mock_jira.TRANSITIONS["Merged" if merged else "Rejected"]
    assert transitions_post.request_history[0].json() == {
        "transition": {"id": transition_id}
    }
