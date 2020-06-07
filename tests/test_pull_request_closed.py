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

    with reqctx:
        pull_request_closed(pr)

    # We moved the Jira issue to Merged or Rejected.
    expected_status = "Merged" if merged else "Rejected"
    assert mock_jira.get_issue_status(issue) == expected_status


def test_external_pr_merged_but_issue_deleted(reqctx, mock_jira, closed_pull_request):
    # A closing pull request, but its Jira issue has been deleted.
    pr, issue = closed_pull_request
    mock_jira.delete_issue(issue)

    with reqctx:
        pull_request_closed(pr)

    # Issue was deleted, so nothing was transitioned.
    assert len(mock_jira.transition_issue_post.request_history) == 0


def test_external_pr_merged_but_issue_in_status(merged, reqctx, mock_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request is already in the
    # status we want to move it to.
    pr, issue = closed_pull_request
    mock_jira.set_issue_status(issue, "Merged" if merged else "Rejected")

    with reqctx:
        pull_request_closed(pr)

    # Issue is already correct, so nothing was transitioned.
    assert len(mock_jira.transition_issue_post.request_history) == 0


def test_external_pr_merged_but_issue_cant_transition(reqctx, mock_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request can't transition
    # to the status we want to move it to.
    pr, _ = closed_pull_request

    # Make a new set of transitions, but leave out the two we might need.
    mock_jira.TRANSITIONS = dict(mock_jira.TRANSITIONS)
    del mock_jira.TRANSITIONS["Merged"]
    del mock_jira.TRANSITIONS["Rejected"]

    with reqctx:
        with pytest.raises(Exception, match="cannot be transitioned directly from status Needs Triage to status"):
            pull_request_closed(pr)

    # No valid transition, so nothing was transitioned.
    assert len(mock_jira.transition_issue_post.request_history) == 0
