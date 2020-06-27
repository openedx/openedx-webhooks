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


def test_internal_pr_merged(merged, reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="nedbat", state="closed", merged=merged)
    pr.add_comment(user="nedbat", body="This is great")
    pr.add_comment(user="feanil", body="Eh, it's ok")

    with reqctx:
        pull_request_closed(pr.as_json())

    # No Jira issue for this PR, so we should have never talked to Jira.
    assert len(fake_jira.request_history()) == 0


@pytest.fixture
def closed_pull_request(merged, reqctx, fake_github, fake_jira):
    """
    Create a closed pull request.

    Returns (pr, issue)
    """
    pr = fake_github.make_pull_request(user="tusbar", state="closed", merged=merged)
    issue = fake_jira.make_issue()
    with reqctx:
        bot_comment = github_community_pr_comment(pr.as_json(), jira_issue=issue)
    pr.add_comment(user=fake_github.login, body=bot_comment)
    pr.add_comment(user="nedbat", body="Please make some changes")
    pr.add_comment(user="tusbar", body="OK, I made the changes")
    return pr, issue


def test_external_pr_merged(merged, reqctx, fake_jira, closed_pull_request):
    pr, issue = closed_pull_request

    with reqctx:
        pull_request_closed(pr.as_json())

    # We moved the Jira issue to Merged or Rejected.
    expected_status = "Merged" if merged else "Rejected"
    assert fake_jira.get_issue_status(issue) == expected_status


def test_external_pr_merged_but_issue_deleted(reqctx, fake_jira, closed_pull_request):
    # A closing pull request, but its Jira issue has been deleted.
    pr, issue = closed_pull_request
    fake_jira.delete_issue(issue)

    with reqctx:
        pull_request_closed(pr.as_json())

    # Issue was deleted, so nothing was transitioned.
    assert len(fake_jira.transition_issue_post.request_history) == 0


def test_external_pr_merged_but_issue_in_status(merged, reqctx, fake_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request is already in the
    # status we want to move it to.
    pr, issue = closed_pull_request
    fake_jira.set_issue_status(issue, "Merged" if merged else "Rejected")

    with reqctx:
        pull_request_closed(pr.as_json())

    # Issue is already correct, so nothing was transitioned.
    assert len(fake_jira.transition_issue_post.request_history) == 0


def test_external_pr_merged_but_issue_cant_transition(reqctx, fake_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request can't transition
    # to the status we want to move it to.
    pr, _ = closed_pull_request

    # Make a new set of transitions, but leave out the two we might need.
    fake_jira.TRANSITIONS = dict(fake_jira.TRANSITIONS)
    del fake_jira.TRANSITIONS["Merged"]
    del fake_jira.TRANSITIONS["Rejected"]

    with reqctx:
        with pytest.raises(Exception, match="cannot be transitioned directly from status Needs Triage to status"):
            pull_request_closed(pr.as_json())

    # No valid transition, so nothing was transitioned.
    assert len(fake_jira.transition_issue_post.request_history) == 0
