"""Tests of tasks/github.py:pull_request_changed for opening pull requests."""

import logging
import textwrap
from datetime import datetime
from unittest import mock

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


def test_internal_pr_opened(fake_github):
    pr = fake_github.make_pull_request("openedx", user="nedbat")
    result = pull_request_changed(pr.as_json())

    assert not result.jira_issues
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    assert pull_request_projects(pr.as_json()) == set()

    result2 = close_and_reopen_pr(pr)
    assert not result2.jira_issues


def test_pr_in_private_repo_opened(fake_github):
    repo = fake_github.make_repo("edx", "some-private-repo", private=True)
    pr = repo.make_pull_request(user="some_contractor")
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    assert len(pr.list_comments()) == 0
    # some_contractor has no cla, and even in a private repo we check.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_PRIVATE
    assert pull_request_projects(pr.as_json()) == set()


@pytest.mark.parametrize("user", ["tusbar", "feanil"])
def test_pr_in_nocontrib_repo_opened(fake_github, user):
    repo = fake_github.make_repo("edx", "some-public-repo")
    pr = repo.make_pull_request(user=user)
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.NO_CONTRIBUTIONS, body)
    # User has a cla, but we aren't accepting contributions.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_NO_CONTRIBUTIONS
    assert pull_request_projects(pr.as_json()) == set()


@pytest.mark.parametrize("owner,tag", [
    ("group:arch-bom", "@openedx/arch-bom"),
    ("user:feanil", "@feanil"),
    ("feanil", "@feanil"),
])
@mock.patch("openedx_webhooks.info.get_catalog_info")
def test_pr_with_owner_repo_opened(get_catalog_info, fake_github, owner, tag, mocker):
    mocker.patch("openedx_webhooks.tasks.pr_tracking.get_github_user_info", lambda x: {"name": x})
    get_catalog_info.return_value = {
        'spec': {'owner': owner, 'lifecycle': 'production'}
    }
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform")
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert f"This repository is currently maintained by `{tag}`" in body


@pytest.mark.parametrize("lifecycle", ["production", "deprecated", None])
@mock.patch("openedx_webhooks.info.get_catalog_info")
def test_pr_without_owner_repo_opened(get_catalog_info, fake_github, lifecycle):
    get_catalog_info.return_value = {
        'spec': {'lifecycle': lifecycle}
    } if lifecycle else None
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform")
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    if lifecycle == "production":
        assert "This repository has no maintainer (yet)." in body
    else:
        assert "This repository is currently unmaintained." in body


def test_pr_opened_by_bot(fake_github):
    fake_github.make_user(login="some_bot", type="Bot")
    pr = fake_github.make_pull_request(user="some_bot")
    result = pull_request_changed(pr.as_json())
    assert not result.jira_issues
    assert len(pr.list_comments()) == 0
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_BOT
    assert pull_request_projects(pr.as_json()) == set()


def test_external_pr_opened_no_cla(fake_github):
    # No CLA, because this person is not in our database.
    fake_github.make_user(login="new_contributor", name="Newb Contributor")
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", user="new_contributor")
    prj = pr.as_json()

    result = pull_request_changed(prj)
    assert not result.jira_issues

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, None)
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
    result2 = close_and_reopen_pr(pr)
    assert not result2.jira_issues
    # Now there is one comment: closing the PR added a survey comment, but
    # re-opening it deleted it.
    assert len(pr.list_comments()) == 1


def test_external_pr_opened_with_cla(fake_github):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", number=11235)
    prj = pr.as_json()

    result = pull_request_changed(prj)
    assert not result.jira_issues

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, None)
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
    result2 = close_and_reopen_pr(pr)
    assert not result2.jira_issues
    # Now there is one comment: closing the PR added a survey comment, but
    # re-opening it deleted it.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1


def test_blended_pr_opened_with_cla(fake_github):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", title="[BD-34] Something good")
    prj = pr.as_json()
    result = pull_request_changed(prj)
    assert not result.jira_issues

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, None)
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


def test_external_pr_rescanned(fake_github):
    # Rescanning a pull request shouldn't do anything.

    # Make a pull request and process it.
    pr = fake_github.make_pull_request(user="tusbar")
    result1 = pull_request_changed(pr.as_json())

    assert not result1.jira_issues
    assert len(pr.list_comments()) == 1

    # Rescan the pull request.
    result2 = pull_request_changed(pr.as_json())

    assert not result2.jira_issues

    # No new GitHub comment was created.
    assert len(pr.list_comments()) == 1


@pytest.mark.parametrize("pr_type", ["normal", "blended", "nocla"])
def test_draft_pr_opened(pr_type, fake_github, mocker):
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
    result = pull_request_changed(prj)
    assert not result.jira_issues

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.END_OF_WIP, body)
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
    result2 = pull_request_changed(pr.as_json())
    assert not result2.jira_issues

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert not is_comment_kind(BotComment.END_OF_WIP, body)

    # Oops, it goes back to draft!
    pr.title = title1
    result3 = pull_request_changed(pr.as_json())
    assert not result3.jira_issues

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.END_OF_WIP, body)


def test_dont_add_internal_prs_to_project(fake_github):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="nedbat")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == set()


def test_add_external_prs_to_project(fake_github):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="tusbar")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT, ("openedx", 23)}


def test_dont_add_draft_prs_to_project(fake_github):
    pr = fake_github.make_pull_request(owner="openedx", repo="credentials", user="tusbar", draft=True)
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}


def test_add_to_multiple_projects(fake_github):
    pr = fake_github.make_pull_request(owner="anotherorg", repo="multi-project", user="tusbar")
    pull_request_changed(pr.as_json())
    assert pull_request_projects(pr.as_json()) == {
        settings.GITHUB_OSPR_PROJECT, ("openedx", 23), ("anotherorg", 17),
    }


def test_crash_label(fake_github):
    pr = fake_github.make_pull_request("openedx", user="nedbat")
    pr.set_labels(["crash!123"])
    with pytest.raises(Exception, match="A crash label was applied by nedbat"):
        pull_request_changed(pr.as_json())


def test_jira_labelling(fake_github, fake_jira, fake_jira_another):
    # A PR with a "jira:" label makes a Jira issue.
    pr = fake_github.make_pull_request("openedx", user="nedbat", number=99, title="Ned's PR", body="Line1\nLine2\n")
    pr.set_labels(["jira:test1"])
    assert len(pr.list_comments()) == 0

    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 1
    assert len(result.changed_jira_issues) == 1
    assert len(fake_jira.issues) == 1
    assert len(fake_jira_another.issues) == 0
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[-1].body
    jira_id = result.changed_jira_issues.pop()
    check_issue_link_in_markdown(body, jira_id)
    assert "in the private Test1 Jira" in body
    jira_issue = fake_jira.issues[jira_id.key]
    assert jira_issue.summary == "Ned's PR"
    assert jira_issue.description == textwrap.dedent("""\
        (From https://github.com/openedx/a-repo/pull/99 by https://github.com/nedbat)
        ------

        Line1
        Line2
        """
    )
    assert jira_issue.labels == {"from-GitHub"}

    # Processing the pull request again won't make another issue.
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 1
    assert len(result.changed_jira_issues) == 0
    assert len(fake_jira.issues) == 1
    assert len(fake_jira_another.issues) == 0
    assert len(pr.list_comments()) == 1


def test_jira_labelling_later(fake_github, fake_jira, fake_jira_another):
    # You can add the label later, and get a Jira issue.
    # At first, no labels, so no Jira issues:
    pr = fake_github.make_pull_request("openedx", user="nedbat", title="Yet another PR")
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 0
    assert len(result.changed_jira_issues) == 0
    assert len(fake_jira.issues) == 0
    assert len(fake_jira_another.issues) == 0

    # Make a label, get an issue:
    pr.set_labels(["jira:test1"])
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 1
    assert len(result.changed_jira_issues) == 1
    assert len(fake_jira.issues) == 1
    assert len(fake_jira_another.issues) == 0
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1

    # You can add a second label for another Jira server.
    pr.set_labels(["jira:AnotherOrg"])
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 2
    assert len(result.changed_jira_issues) == 1
    assert len(fake_jira.issues) == 1
    assert len(fake_jira_another.issues) == 1
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 2
    body = pr_comments[-1].body
    jira_id = result.changed_jira_issues.pop()
    check_issue_link_in_markdown(body, jira_id)
    assert "in the Another Org Jira" in body
    jira_issue = fake_jira_another.issues[jira_id.key]
    assert jira_issue.summary == "Yet another PR"


def test_bad_jira_labelling_no_server(fake_github):
    # What if the jira: label doesn't match one of our configured servers?
    pr = fake_github.make_pull_request("openedx", user="nedbat", title="Ned's PR")
    pr.set_labels(["jira:bogus"])
    pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.NO_JIRA_SERVER, body)

    # Processing the PR again won't add another comment.
    pull_request_changed(pr.as_json())
    assert len(pr.list_comments()) == 1


def test_bad_jira_labelling_no_repo_map(fake_github, fake_jira2, mocker):
    # What if the jira: label is good, but the repo has no mapping to a project?
    pr = fake_github.make_pull_request("openedx", repo="nomap", user="nedbat", title="Ned's PR")
    pr.set_labels(["jira:test2"])
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 0
    assert len(result.changed_jira_issues) == 0

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert is_comment_kind(BotComment.NO_JIRA_MAPPING, body)
    assert "Contact Wes Admin (@wesadmin) to set up a project." in body

    # Processing the PR again won't add another comment.
    pull_request_changed(pr.as_json())
    assert len(pr.list_comments()) == 1

    # The repo gets a mapping to a project.
    mocker.patch(
        "openedx_webhooks.tasks.pr_tracking.jira_details_for_pr",
        lambda nick, pr: ("NEWPROJ", "Task")
    )

    # Processing the PR again won't add another comment.
    pull_request_changed(pr.as_json())
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1

    # If we delete the bot's error comment and process the PR, we get a Jira issue.
    pr.delete_comment(pr_comments[0].id)
    assert len(pr.list_comments()) == 0
    result = pull_request_changed(pr.as_json())
    assert len(result.jira_issues) == 1
    assert len(result.changed_jira_issues) == 1

    assert len(fake_jira2.issues) == 1

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    jira_id = result.changed_jira_issues.pop()
    check_issue_link_in_markdown(body, jira_id)


@pytest.mark.parametrize("owner", ["user:navin", "group:auth-group"])
def test_pr_project_fields_data(fake_github, mocker, owner):
    # Create user "navin" to fake `get_github_user_info` api.
    fake_github.make_user(login='navin', name='Navin')
    mocker.patch(
        "openedx_webhooks.info.get_catalog_info",
        lambda _: {
            'spec': {'owner': owner, 'lifecycle': 'production'}
        }
    )
    created_at = datetime(2024, 12, 1)
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", created_at=created_at)
    pull_request_changed(pr.as_json())
    assert pr.repo.github.project_items['date-opened-id'] == {created_at.isoformat() + 'Z'}
    owner_type, owner_name = owner.split(":")
    if owner_type == "user":
        assert pr.repo.github.project_items['repo-owner-id'] == {f"{owner_name.title()} (@{owner_name})"}
    else:
        assert pr.repo.github.project_items['repo-owner-id'] == {f"openedx/{owner_name}"}


def test_pr_project_fields_invalid_field_name(fake_github, mocker, caplog):
    # Create user "navin" to fake `get_github_user_info` api.
    fake_github.make_user(login='navin', name='Navin')
    mocker.patch(
        "openedx_webhooks.info.get_catalog_info",
        lambda _: {
            'spec': {'owner': "user:navin", 'lifecycle': 'production'}
        }
    )
    # mock project metadata
    mocker.patch(
        "openedx_webhooks.gh_projects.get_project_metadata",
        lambda _: {
            "id": "some-project-id",
            "fields": [
                {"name": "Name", "id": "name-id", "dataType": "text"},
            ]
        }
    )
    created_at = datetime(2024, 12, 1)
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", created_at=created_at)
    pull_request_changed(pr.as_json())
    assert pr.repo.github.project_items['date-opened-id'] == set()
    assert pr.repo.github.project_items['repo-owner-id'] == set()
    error_logs = [log for log in caplog.records if log.levelno == logging.ERROR]
    expected_msgs = (
        f"Could not find field with name: Date opened in project: {settings.GITHUB_OSPR_PROJECT}",
        f"Could not find field with name: Repo Owner / Owning Team in project: {settings.GITHUB_OSPR_PROJECT}"
    )
    assert error_logs[0].msg == expected_msgs[0]
    assert error_logs[1].msg == expected_msgs[1]
