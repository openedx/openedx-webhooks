"""Tests of tasks/github.py:pull_request_changed for opening pull requests."""

import pytest

from openedx_webhooks import settings
from openedx_webhooks.bot_comments import (
    BotComment,
    is_comment_kind,
)
from openedx_webhooks.cla_check import (
    CLA_CONTEXT,
    CLA_STATUS_BAD,
    CLA_STATUS_BOT,
    CLA_STATUS_GOOD,
    CLA_STATUS_NO_CONTRIBUTIONS,
    CLA_STATUS_PRIVATE,
)
from openedx_webhooks.gh_projects import pull_request_projects
from openedx_webhooks.tasks.github import pull_request_changed

from .helpers import check_issue_link_in_markdown

# These tests should run when we want to test flaky GitHub behavior.
pytestmark = pytest.mark.flaky_github


def close_and_reopen_pr(pr):
    """For testing re-opening, close the pr, process it, then re-open it."""
    pr.close(merge=False)
    pull_request_changed(pr.as_json())
    pr.reopen()
    prj = pr.as_json()
    prj["hook_action"] = "reopened"
    return pull_request_changed(prj)


def test_internal_pr_opened(fake_github, fake_jira):
    pr = fake_github.make_pull_request("openedx", user="nedbat")
    key, anything_happened = pull_request_changed(pr.as_json())

    assert key is None
    assert anything_happened is True
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    assert pull_request_projects(pr.as_json()) == set()

    key, anything_happened2 = close_and_reopen_pr(pr)
    assert key is None
    assert anything_happened2 is False


def test_pr_in_private_repo_opened(fake_github, fake_jira):
    repo = fake_github.make_repo("edx", "some-private-repo", private=True)
    pr = repo.make_pull_request(user="some_contractor")
    key, anything_happened = pull_request_changed(pr.as_json())
    assert key is None
    assert anything_happened is True
    assert len(pr.list_comments()) == 0
    # some_contractor has no cla, and even in a private repo we check.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_PRIVATE
    assert pull_request_projects(pr.as_json()) == set()


@pytest.mark.parametrize("user", ["tusbar", "feanil"])
def test_pr_in_nocontrib_repo_opened(fake_github, fake_jira, user):
    repo = fake_github.make_repo("edx", "some-public-repo")
    pr = repo.make_pull_request(user=user)
    key, anything_happened = pull_request_changed(pr.as_json())
    assert key is None
    assert anything_happened is True
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.NO_CONTRIBUTIONS, body)
    # tusbar has a cla, but we aren't accepting contributions.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_NO_CONTRIBUTIONS
    assert pull_request_projects(pr.as_json()) == set()


def test_pr_opened_by_bot(fake_github, fake_jira):
    fake_github.make_user(login="some_bot", type="Bot")
    pr = fake_github.make_pull_request(user="some_bot")
    key, anything_happened = pull_request_changed(pr.as_json())
    assert key is None
    assert anything_happened is True
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_BOT
    assert pull_request_projects(pr.as_json()) == set()


def test_external_pr_opened_no_cla(fake_github, fake_jira):
    # No CLA, because this person is not in our database.
    fake_github.make_user(login="new_contributor", name="Newb Contributor")
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", user="new_contributor")
    prj = pr.as_json()

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    assert issue_id is None
    assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id)
    assert "Thanks for the pull request, @new_contributor!" in body
    assert is_comment_kind(BotComment.NEED_CLA, body)
    assert is_comment_kind(BotComment.WELCOME, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"open-source-contribution"}
    assert pr.labels == expected_labels

    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_BAD
    # It should have been put in the OSPR project.
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}

    # Test re-opening.
    issue_id2, anything_happened2 = close_and_reopen_pr(pr)
    assert issue_id2 == issue_id
    assert anything_happened2 is True
    # Now there is one comment: closing the PR added a survey comment, but
    # re-opening it deleted it.
    assert len(pr.list_comments()) == 1

    assert len(fake_jira.issues) == 0


def test_external_pr_opened_with_cla(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", number=11235)
    prj = pr.as_json()

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    assert issue_id is None
    assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id)
    assert "Thanks for the pull request, @tusbar!" in body
    assert is_comment_kind(BotComment.WELCOME, body)
    assert not is_comment_kind(BotComment.NEED_CLA, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"open-source-contribution"}
    assert pr.labels == expected_labels

    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    # It should have been put in the OSPR project.
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}

    # Test re-opening.
    issue_id2, anything_happened2 = close_and_reopen_pr(pr)
    assert issue_id2 == issue_id
    assert anything_happened2 is True
    # Now there is one comment: closing the PR added a survey comment, but
    # re-opening it deleted it.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    assert len(fake_jira.issues) == 0


def test_blended_pr_opened_with_cla(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", title="[BD-34] Something good")
    prj = pr.as_json()
    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    assert issue_id is None
    assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id)
    assert "Thanks for the pull request, @tusbar!" in body
    has_project_link = "the [BD-34](https://thewiki/bd-34) project page" in body
    assert not has_project_link
    assert is_comment_kind(BotComment.BLENDED, body)
    assert not is_comment_kind(BotComment.NEED_CLA, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"blended"}
    assert pr.labels == expected_labels
    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    # It should have been put in the Blended project.
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_BLENDED_PROJECT}


def test_external_pr_rescanned(fake_github, fake_jira):
    # Rescanning a pull request shouldn't do anything.

    # Make a pull request and process it.
    pr = fake_github.make_pull_request(user="tusbar")
    issue_id1, anything_happened1 = pull_request_changed(pr.as_json())

    assert issue_id1 is None
    assert anything_happened1 is True
    assert len(pr.list_comments()) == 1

    # Rescan the pull request.
    issue_id2, anything_happened2 = pull_request_changed(pr.as_json())

    assert issue_id2 is None
    assert anything_happened2 is False

    # No new GitHub comment was created.
    assert len(pr.list_comments()) == 1


def test_title_change_changes_jira_project(fake_github, fake_jira):
    """
    A blended developer opens a PR, but forgets to put "[BD]" in the title.
    """
    # The developer makes a pull request, but forgets the right syntax in the title.
    pr = fake_github.make_pull_request(user="tusbar", title="This is for BD-34")

    ospr_id, anything_happened = pull_request_changed(pr.as_json())

    # An OSPR issue was not made.
    assert ospr_id is None
    assert anything_happened is True

    # Someone assigns an ad-hoc label to the PR.
    pr.repo.add_label(name="pretty")
    pr.labels.add("pretty")

    # The developer changes the title.
    pr.title = "This is for [BD-34]."
    issue_id, anything_happened = pull_request_changed(pr.as_json())

    assert anything_happened is True
    assert issue_id is None

    # The bot comment now mentions the new issue.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1

    # The pull request still has the ad-hoc label.
    assert "pretty" in pr.labels


@pytest.mark.parametrize("pr_type", ["normal", "blended", "nocla"])
def test_draft_pr_opened(pr_type, fake_github, fake_jira, mocker):
    # pylint: disable=too-many-statements

    # Set the GITHUB_STATUS_LABEL variable with a set() of labels that should map to jira issues.
    # We set this explicitly here because the production version of the list can change and we don't
    # want that to break the test.
    github_status_labels = {
        "needs triage",
        "waiting on author",
        "community manager review",
    }
    mocker.patch("openedx_webhooks.tasks.pr_tracking.GITHUB_STATUS_LABELS", github_status_labels)

    # Open a WIP pull request.
    title1 = "WIP: broken"
    title2 = "Fixed and done"
    if pr_type == "normal":
        pr = fake_github.make_pull_request(user="tusbar", title=title1)
    elif pr_type == "blended":
        title1 = "[BD-34] Something good (WIP)"
        title2 = "[BD-34] Something good"
        pr = fake_github.make_pull_request(user="tusbar", title=title1)
    else:
        assert pr_type == "nocla"
        fake_github.make_user(login="new_contributor", name="Newb Contributor")
        pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", user="new_contributor", title=title1)

    prj = pr.as_json()
    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    assert issue_id is None
    assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert 'This is currently a draft pull request' in body
    assert 'click "Ready for Review"' in body
    expected_labels = set()
    expected_labels.add("blended" if pr_type == "blended" else "open-source-contribution")
    assert pr.labels == expected_labels
    if pr_type == "normal":
        assert is_comment_kind(BotComment.WELCOME, body)
    elif pr_type == "blended":
        assert is_comment_kind(BotComment.BLENDED, body)
    else:
        assert pr_type == "nocla"
        assert is_comment_kind(BotComment.NEED_CLA, body)

    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == (CLA_STATUS_BAD if pr_type == "nocla" else CLA_STATUS_GOOD)
    if pr_type == "blended":
        assert pull_request_projects(pr.as_json()) == {settings.GITHUB_BLENDED_PROJECT}
    else:
        assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}

    # The author updates the PR, no longer draft.
    pr.title = title2
    issue_id2, _ = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id
    assert len(fake_jira.issues) == 0

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert 'This is currently a draft pull request' not in body
    assert 'click "Ready for Review"' not in body

    # Oops, it goes back to draft!
    pr.title = title1
    issue_id3, _ = pull_request_changed(pr.as_json())

    assert issue_id3 == issue_id
    assert len(fake_jira.issues) == 0

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert 'This is currently a draft pull request' in body
    assert 'click "Ready for Review"' in body


def test_handle_closed_pr(is_merged, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="tusbar", number=11237, state="closed", merged=is_merged)
    prj = pr.as_json()
    issue_id1, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    assert issue_id1 is None
    assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id1)
    if is_merged:
        assert "Although this pull request is already merged," in body
    else:
        assert "Although this pull request is already closed," in body
    assert is_comment_kind(BotComment.WELCOME, body)
    assert is_comment_kind(BotComment.WELCOME_CLOSED, body)
    assert not is_comment_kind(BotComment.NEED_CLA, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"open-source-contribution"}
    assert pr.labels == expected_labels
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}

    # Rescan the pull request.
    num_issues = len(fake_jira.issues)
    issue_id2, anything_happened2 = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id1
    assert anything_happened2 is False

    # No Jira issue was created.
    assert len(fake_jira.issues) == num_issues

    # No new GitHub comment was created.
    assert len(pr.list_comments()) == 1


def test_dont_add_internal_prs_to_project(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="nedbat")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == set()


def test_add_external_prs_to_project(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="tusbar")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT, ("openedx", 23)}


def test_dont_add_draft_prs_to_project(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="tusbar", draft=True)
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}


def test_add_to_multiple_projects(fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="anotherorg", repo="multi-project", user="tusbar")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {
        settings.GITHUB_OSPR_PROJECT, ("openedx", 23), ("anotherorg", 17),
    }
