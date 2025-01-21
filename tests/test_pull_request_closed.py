"""Tests of task/github.py:pull_request_changed for closing pull requests."""

import pytest

from openedx_webhooks.bot_comments import (
    BotComment,
)
from openedx_webhooks.cla_check import (
    CLA_CONTEXT,
    CLA_STATUS_GOOD,
    CLA_STATUS_NO_CONTRIBUTIONS,
)
from openedx_webhooks.gh_projects import pull_request_projects
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
        owner="openedx",
        user="tusbar",
        title=random_text(),
        )
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    pr.add_comment(user="nedbat", body="Please make some changes")
    pr.add_comment(user="tusbar", body="OK, I made the changes")
    pr.close(merge=is_merged)

    fake_jira.reset_mock()

    return pr


def test_external_pr_closed_but_issue_deleted(fake_jira, closed_pull_request):
    # A closing pull request, but its Jira issue has been deleted.
    pr = closed_pull_request

    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 3    # 1 welcome, closed_pull_request makes two
    # We leave the old issue id in the comment.
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, None)


def test_external_pr_closed_but_issue_in_status(fake_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request is already in the
    # status we want to move it to.
    pr = closed_pull_request

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
    assert len(pr_comments) == 1    # welcome comment

    # Processing it again won't change anything.
    pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1    # welcome comment


@pytest.mark.parametrize("org", ["openedx", "edx"])
def test_pr_closed_after_employee_leaves(org, is_merged, fake_github, mocker):
    # Ned is internal.
    pr = fake_github.make_pull_request(org, user="nedbat")
    result = pull_request_changed(pr.as_json())

    assert not result.jira_issues
    # No comments, labels or projects because Ned is internal.
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    assert pr.labels == set()
    assert pull_request_projects(pr.as_json()) == set()

    # Ned is fired for malfeasance.
    mocker.patch("openedx_webhooks.tasks.pr_tracking.is_internal_pull_request", lambda pr: False)

    # His PR is closed.
    pr.close(merge=is_merged)
    result = pull_request_changed(pr.as_json())

    assert not result.jira_issues
    # We don't want the bot to write a comment on a closed pull request.
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    assert pr.labels == set()
    assert pull_request_projects(pr.as_json()) == set()


def test_pr_closed_labels(fake_github, is_merged):
    """
    Test whether obsolete labels are removed on closing merge requests
    """
    pr = fake_github.make_pull_request(
        user="newuser",
        owner="openedx",
        repo="edx-platform",
        body=None,
    )
    pr.set_labels({"open-source-contribution", "waiting on author", "needs test run", "custom label 1"})

    pr.close(merge=is_merged)
    pull_request_changed(pr.as_json())
    assert pr.labels == {"open-source-contribution", "custom label 1"}
