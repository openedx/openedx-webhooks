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
from openedx_webhooks.info import get_jira_issue_key
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


def test_external_pr_opened_no_cla(has_jira, fake_github, fake_jira):
    # No CLA, because this person is not in people.yaml
    fake_github.make_user(login="new_contributor", name="Newb Contributor")
    pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", user="new_contributor")
    prj = pr.as_json()

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True

    if has_jira:
        assert issue_id.startswith("OSPR-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == 1
        issue = fake_jira.issues[issue_id]
        assert issue.contributor_name == "Newb Contributor"
        assert issue.customer is None
        assert issue.pr_number == prj["number"]
        assert issue.repo == prj["base"]["repo"]["full_name"]
        assert issue.url == prj["html_url"]
        assert issue.description == prj["body"]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        assert issue.labels == set()

        # Check that the Jira issue was moved to Community Manager Review.
        assert issue.status == "Community Manager Review"
    else:
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
    if has_jira:
        expected_labels.add("community manager review")
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

    if has_jira:
        issue = fake_jira.issues[issue_id]
        assert issue.status == "Community Manager Review"
    else:
        assert len(fake_jira.issues) == 0


def test_external_pr_opened_with_cla(has_jira, fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", number=11235)
    prj = pr.as_json()

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    if has_jira:
        assert issue_id is not None
        assert issue_id.startswith("OSPR-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == 1
        issue = fake_jira.issues[issue_id]
        assert issue.contributor_name == "Bertrand Marron"
        assert issue.customer == ["IONISx"]
        assert issue.pr_number == 11235
        assert issue.repo == "openedx/some-code"
        assert issue.url == prj["html_url"]
        assert issue.description == prj["body"]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        assert issue.labels == set()

        # Check that the Jira issue is in Needs Triage.
        assert issue.status == "Needs Triage"
    else:
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
    if has_jira:
        expected_labels.add("needs triage")
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

    if has_jira:
        issue = fake_jira.issues[issue_id]
        # Re-opening a pull request should put Jira back its state before the closing.
        assert issue.status == "Needs Triage"
    else:
        assert len(fake_jira.issues) == 0


def test_psycho_reopening(fake_github, fake_jira):
    # Check that close/re-open/close/re-open etc will properly track the jira status.
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", number=11235)
    prj = pr.as_json()

    issue_id, _ = pull_request_changed(prj)

    issue = fake_jira.issues[issue_id]
    for status in ["Waiting on Author", "Needs Triage", "Architecture Review", "Changes Requested"]:
        issue.status = status
        issue_id2, anything_happened2 = close_and_reopen_pr(pr)
        assert issue_id2 == issue_id
        assert anything_happened2 is True

        issue = fake_jira.issues[issue_id]
        # Re-opening a pull request should put Jira back its state before the closing.
        assert issue.status == status


def test_core_committer_pr_opened(has_jira, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="felipemontoya", owner="openedx", repo="edx-platform")
    prj = pr.as_json()

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    if has_jira:
        assert issue_id is not None
        assert issue_id.startswith("OSPR-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == 1
        issue = fake_jira.issues[issue_id]
        assert issue.contributor_name == "Felipe Montoya"
        assert issue.customer == ["EduNEXT"]
        assert issue.pr_number == prj["number"]
        assert issue.repo == prj["base"]["repo"]["full_name"]
        assert issue.url == prj["html_url"]
        assert issue.description == prj["body"]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        assert issue.labels == {"core-committer"}

        # Check that the Jira issue was moved to Waiting on Author
        assert issue.status == "Waiting on Author"
    else:
        assert issue_id is None
        assert len(fake_jira.issues) == 0

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id)
    assert "Thanks for the pull request, @felipemontoya!" in body
    assert is_comment_kind(BotComment.CORE_COMMITTER, body)
    assert not is_comment_kind(BotComment.NEED_CLA, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"open-source-contribution"}
    if has_jira:
        expected_labels.add("waiting on author")
    assert pr.labels == expected_labels
    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == CLA_STATUS_GOOD
    # It should have been put in the OSPR project.
    assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}


EXAMPLE_PLATFORM_MAP_1_2 = {
    "child": {
        "id": "14522",
        "self": "https://test.atlassian.net/rest/api/2/customFieldOption/14522",
        "value": "Course Level Insights"
    },
    "id": "14209",
    "self": "https://test.atlassian.net/rest/api/2/customFieldOption/14209",
    "value": "Researcher & Data Experiences"
}

@pytest.mark.parametrize("with_epic", [
    pytest.param(False, id="epic:no"),
    pytest.param(True, id="epic:yes"),
])
def test_blended_pr_opened_with_cla(with_epic, has_jira, fake_github, fake_jira):
    pr = fake_github.make_pull_request(owner="openedx", repo="some-code", user="tusbar", title="[BD-34] Something good")
    prj = pr.as_json()
    total_issues = 0
    if with_epic:
        epic = fake_jira.make_issue(
            project="BLENDED",
            blended_project_id="BD-34",
            blended_project_status_page="https://thewiki/bd-34",
            platform_map_1_2=EXAMPLE_PLATFORM_MAP_1_2,
        )
        total_issues += 1

    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    if has_jira:
        assert issue_id is not None
        assert issue_id.startswith("BLENDED-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == total_issues + 1
        issue = fake_jira.issues[issue_id]
        assert issue.contributor_name == "Bertrand Marron"
        assert issue.customer == ["IONISx"]
        assert issue.pr_number == prj["number"]
        assert issue.repo == "openedx/some-code"
        assert issue.url == prj["html_url"]
        assert issue.description == prj["body"]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        assert issue.labels == {"blended"}
        if with_epic:
            assert issue.epic_link == epic.key
            assert issue.platform_map_1_2 == EXAMPLE_PLATFORM_MAP_1_2
        else:
            assert issue.epic_link is None
            assert issue.platform_map_1_2 is None

        # Check that the Jira issue is in Needs Triage.
        assert issue.status == "Needs Triage"
    else:
        assert issue_id is None
        assert len(fake_jira.issues) == total_issues

    # Check the GitHub comment that was created.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    check_issue_link_in_markdown(body, issue_id)
    assert "Thanks for the pull request, @tusbar!" in body
    has_project_link = "the [BD-34](https://thewiki/bd-34) project page" in body
    assert has_project_link == (with_epic and has_jira)
    assert is_comment_kind(BotComment.BLENDED, body)
    assert not is_comment_kind(BotComment.NEED_CLA, body)

    # Check the GitHub labels that got applied.
    expected_labels = {"blended"}
    if has_jira:
        expected_labels.add("needs triage")
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

    assert anything_happened1 is True
    assert len(pr.list_comments()) == 1

    # Rescan the pull request.
    issue_id2, anything_happened2 = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id1
    assert anything_happened2 is False

    # No Jira issue was created.
    assert len(fake_jira.issues) == 1

    # No new GitHub comment was created.
    assert len(pr.list_comments()) == 1


def test_changing_pr_title(fake_github, fake_jira):
    # After the Jira issue is created, changing the title of the pull request
    # will update the title of the issue.
    pr = fake_github.make_pull_request(
        user="tusbar",
        title="These are my changes, please take them.",
    )

    issue_id1, _ = pull_request_changed(pr.as_json())

    issue = fake_jira.issues[issue_id1]
    assert issue.summary == "These are my changes, please take them."
    # The bot made one comment on the PR.
    assert len(pr.list_comments()) == 1

    # Someone transitions the issue to a new state, and adds a label.
    issue.status = "Blocked by Other Work"
    issue.labels.add("my-label")

    # Author updates the title.
    pr.title = "This is the best!"
    issue_id2, _ = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id1
    issue = fake_jira.issues[issue_id2]
    # The issue title has changed.
    assert issue.summary == "This is the best!"
    # The bot didn't make another comment.
    assert len(pr.list_comments()) == 1
    # The issue shouldn't have changed status.
    assert issue.status == "Blocked by Other Work"
    # The issue should still have the ad-hoc label.
    assert "my-label" in issue.labels


def test_changing_pr_description(fake_github, fake_jira):
    # After the Jira issue is created, changing the body of the pull request
    # will update the description of the issue.
    pr = fake_github.make_pull_request(
        user="tusbar",
        title="These are my changes, please take them.",
        body="Blah blah lots of description.",
    )

    issue_id1, _ = pull_request_changed(pr.as_json())

    issue = fake_jira.issues[issue_id1]
    assert issue.summary == "These are my changes, please take them."
    assert issue.description == "Blah blah lots of description."
    # The bot made one comment on the PR.
    assert len(pr.list_comments()) == 1

    # The issue is in the correct initial state.
    assert issue.status == "Needs Triage"

    # Someone changes the issue status.
    issue.status = "Blocked by Other Work"
    labels = pr.labels
    labels.remove("needs triage")
    labels.add("blocked by other work")
    pr.set_labels(labels)

    # Author updates the description of the PR.
    pr.body = "OK, now I am really describing things."
    issue_id2, _ = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id1
    issue = fake_jira.issues[issue_id2]
    # The issue title hasn't changed, but the description has.
    assert issue.summary == "These are my changes, please take them."
    assert issue.description == "OK, now I am really describing things."
    # The bot didn't make another comment.
    assert len(pr.list_comments()) == 1

    # The issue should still be in the changed status, and the PR labels should
    # still be right.
    assert issue.status == "Blocked by Other Work"
    assert pr.labels == {"blocked by other work", "open-source-contribution"}


def test_title_change_changes_jira_project(fake_github, fake_jira):
    """
    A blended developer opens a PR, but forgets to put "[BD]" in the title.
    """
    # The blended project exists:
    epic = fake_jira.make_issue(
        project="BLENDED",
        blended_project_id="BD-34",
        blended_project_status_page="https://thewiki/bd-34",
        platform_map_1_2=EXAMPLE_PLATFORM_MAP_1_2,
    )

    # The developer makes a pull request, but forgets the right syntax in the title.
    pr = fake_github.make_pull_request(user="tusbar", title="This is for BD-34")

    ospr_id, anything_happened = pull_request_changed(pr.as_json())

    # An OSPR issue was made.
    assert ospr_id is not None
    assert ospr_id.startswith("OSPR-")
    assert anything_happened is True
    assert ospr_id in fake_jira.issues

    # Someone assigns an ad-hoc label to the PR.
    pr.repo.add_label(name="pretty")
    pr.labels.add("pretty")

    # The developer changes the title.
    pr.title = "This is for [BD-34]."
    issue_id, anything_happened = pull_request_changed(pr.as_json())

    assert anything_happened is True
    assert issue_id is not None
    assert issue_id.startswith("BLENDED-")

    # The original issue has been deleted.
    assert ospr_id not in fake_jira.issues

    # The bot comment now mentions the new issue.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert f"I've created [{issue_id}](" in body
    assert f"The original issue {ospr_id} has been deleted." in body

    # The new issue has all the Blended stuff.
    issue = fake_jira.issues[issue_id]
    prj = pr.as_json()
    assert issue.contributor_name == "Bertrand Marron"
    assert issue.customer == ["IONISx"]
    assert issue.pr_number == prj["number"]
    assert issue.repo == "an-org/a-repo"
    assert issue.url == prj["html_url"]
    assert issue.description == prj["body"]
    assert issue.issuetype == "Pull Request Review"
    assert issue.summary == prj["title"]
    assert issue.labels == {"blended"}
    assert issue.epic_link == epic.key
    assert issue.platform_map_1_2 == EXAMPLE_PLATFORM_MAP_1_2

    # Check that the Jira issue is in Needs Triage.
    assert issue.status == "Needs Triage"

    # The pull request has to be associated with the new issue.
    assert get_jira_issue_key(prj) == (True, issue_id)

    # The pull request still has the ad-hoc label.
    assert "pretty" in pr.labels


def test_title_change_but_issue_already_moved(fake_github, fake_jira):
    """
    A blended developer opens a PR, but forgets to put "[BD]" in the title.
    In the meantime, someone already moved the OSPR issue to BLENDED.
    """
    # The blended project exists:
    epic = fake_jira.make_issue(
        project="BLENDED",
        blended_project_id="BD-34",
        blended_project_status_page="https://thewiki/bd-34",
    )

    # The developer makes a pull request, but forgets the right syntax in the title.
    pr = fake_github.make_pull_request(user="tusbar", title="This is for BD-34")
    ospr_id, anything_happened = pull_request_changed(pr.as_json())

    # An OSPR issue was made.
    assert ospr_id is not None
    assert ospr_id.startswith("OSPR-")
    assert anything_happened is True
    assert ospr_id in fake_jira.issues

    # Someone moves the Jira issue.
    issue = fake_jira.find_issue(ospr_id)
    fake_jira.move_issue(issue, "BLENDED")

    # The developer changes the title.
    pr.title = "This is for [BD-34]."
    issue_id, anything_happened = pull_request_changed(pr.as_json())

    assert anything_happened is True
    assert issue_id is not None
    assert issue_id.startswith("BLENDED-")

    # The original issue is still available, but with a new key.
    assert fake_jira.find_issue(ospr_id) is not None

    # The bot comment now mentions the new issue.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert f"I've created [{issue_id}](" in body
    # but doesn't say the old issue is deleted.
    assert "The original issue" not in body
    assert "More details are on" in body

    issue = fake_jira.issues[issue_id]
    prj = pr.as_json()
    assert issue.contributor_name == "Bertrand Marron"
    assert issue.customer == ["IONISx"]
    assert issue.pr_number == prj["number"]
    assert issue.repo == "an-org/a-repo"
    assert issue.url == prj["html_url"]
    assert issue.description == prj["body"]
    assert issue.issuetype == "Pull Request Review"
    assert issue.summary == prj["title"] == "This is for [BD-34]."
    assert issue.labels == {"blended"}
    assert issue.epic_link == epic.key

    # Check that the Jira issue is in Needs Triage.
    assert issue.status == "Needs Triage"

    # The pull request has to be associated with the new issue.
    assert get_jira_issue_key(prj) == (True, issue_id)


@pytest.mark.parametrize("pr_type", ["normal", "blended", "committer", "nocla"])
@pytest.mark.parametrize("jira_got_fiddled", [
    pytest.param(False, id="jira:notfiddled"),
    pytest.param(True, id="jira:fiddled"),
])
def test_draft_pr_opened(pr_type, jira_got_fiddled, has_jira, fake_github, fake_jira, mocker):
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
        initial_status = "Needs Triage"
        pr = fake_github.make_pull_request(user="tusbar", title=title1)
    elif pr_type == "blended":
        title1 = "[BD-34] Something good (WIP)"
        title2 = "[BD-34] Something good"
        initial_status = "Needs Triage"
        pr = fake_github.make_pull_request(user="tusbar", title=title1)
    elif pr_type == "committer":
        initial_status = "Waiting on Author"
        pr = fake_github.make_pull_request(user="felipemontoya", owner="openedx", repo="edx-platform", title=title1)
    else:
        assert pr_type == "nocla"
        initial_status = "Community Manager Review"
        fake_github.make_user(login="new_contributor", name="Newb Contributor")
        pr = fake_github.make_pull_request(owner="openedx", repo="edx-platform", user="new_contributor", title=title1)

    prj = pr.as_json()
    issue_id, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    if has_jira:
        assert issue_id is not None
        assert issue_id.startswith("BLENDED-" if pr_type == "blended" else "OSPR-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == 1
        issue = fake_jira.issues[issue_id]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        if pr_type == "normal":
            assert issue.labels == set()
        elif pr_type == "blended":
            assert issue.labels == {"blended"}
        elif pr_type == "committer":
            assert issue.labels == {"core-committer"}
        else:
            assert pr_type == "nocla"
            assert issue.labels == set()

        # Because of "WIP", the Jira issue is in "Waiting on Author", unless
        # there's no CLA.
        if pr_type == "nocla":
            assert issue.status == "Community Manager Review"
        else:
            assert issue.status == "Waiting on Author"
    else:
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
    if has_jira:
        expected_labels.add("community manager review" if pr_type == "nocla" else "waiting on author")
    assert pr.labels == expected_labels
    if pr_type == "normal":
        assert is_comment_kind(BotComment.WELCOME, body)
    elif pr_type == "blended":
        assert is_comment_kind(BotComment.BLENDED, body)
    elif pr_type == "committer":
        assert is_comment_kind(BotComment.CORE_COMMITTER, body)
    else:
        assert pr_type == "nocla"
        assert is_comment_kind(BotComment.NEED_CLA, body)

    # Check the status check applied to the latest commit.
    assert pr.status(CLA_CONTEXT) == (CLA_STATUS_BAD if pr_type == "nocla" else CLA_STATUS_GOOD)
    if pr_type == "blended":
        assert pull_request_projects(pr.as_json()) == {settings.GITHUB_BLENDED_PROJECT}
    else:
        assert pull_request_projects(pr.as_json()) == {settings.GITHUB_OSPR_PROJECT}

    if has_jira and jira_got_fiddled:
        # Someone changes the status from "Waiting on Author" manually.
        issue.status = "Architecture Review"

    # The author updates the PR, no longer draft.
    pr.title = title2
    issue_id2, _ = pull_request_changed(pr.as_json())

    assert issue_id2 == issue_id
    if has_jira:
        issue = fake_jira.issues[issue_id]
        assert issue.summary == title2
    else:
        assert len(fake_jira.issues) == 0

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert 'This is currently a draft pull request' not in body
    assert 'click "Ready for Review"' not in body

    if has_jira:
        if jira_got_fiddled:
            assert issue.status == "Architecture Review"
            assert "architecture review" in pr.labels
            assert initial_status.lower() not in pr.labels
        else:
            assert issue.status == initial_status
            assert initial_status.lower() in pr.labels

    # Oops, it goes back to draft!
    pr.title = title1
    issue_id3, _ = pull_request_changed(pr.as_json())

    assert issue_id3 == issue_id
    if has_jira:
        issue = fake_jira.issues[issue_id]
        assert issue.summary == title1
    else:
        assert len(fake_jira.issues) == 0

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    body = pr_comments[0].body
    assert 'This is currently a draft pull request' in body
    assert 'click "Ready for Review"' in body

    if has_jira:
        if jira_got_fiddled:
            # We don't change the Jira status again if the PR goes back to draft.
            assert issue.status == "Architecture Review"
            assert "architecture review" in pr.labels
            assert initial_status.lower() not in pr.labels
        else:
            assert issue.status == initial_status
            assert initial_status.lower() in pr.labels


def test_handle_closed_pr(is_merged, has_jira, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="tusbar", number=11237, state="closed", merged=is_merged)
    prj = pr.as_json()
    issue_id1, anything_happened = pull_request_changed(prj)

    assert anything_happened is True
    if has_jira:
        assert issue_id1 is not None
        assert issue_id1.startswith("OSPR-")

        # Check the Jira issue that was created.
        assert len(fake_jira.issues) == 1
        issue = fake_jira.issues[issue_id1]
        assert issue.contributor_name == "Bertrand Marron"
        assert issue.customer == ["IONISx"]
        assert issue.pr_number == 11237
        assert issue.url == prj["html_url"]
        assert issue.description == prj["body"]
        assert issue.issuetype == "Pull Request Review"
        assert issue.summary == prj["title"]
        assert issue.labels == set()

        # Check that the Jira issue is in the right state.
        assert issue.status == ("Merged" if is_merged else "Rejected")
    else:
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
    if has_jira:
        expected_labels.add("merged" if is_merged else "rejected")
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


def test_extra_fields_are_ok(fake_github, fake_jira):
    # If someone adds platform map information to the Jira issue, it won't
    # trigger an update.
    pr = fake_github.make_pull_request(
        user="tusbar",
        title="These are my changes, please take them.",
        additions=1776,
        deletions=1492,
    )

    issue_id1, _ = pull_request_changed(pr.as_json())

    issue = fake_jira.issues[issue_id1]
    assert issue.summary == "These are my changes, please take them."
    # The bot made one comment on the PR.
    assert len(pr.list_comments()) == 1

    # Someone adds platform map and label to the Jira.
    issue.platform_map_1_2 = EXAMPLE_PLATFORM_MAP_1_2
    issue.labels.add("my-label")

    # PR gets rescanned.
    issue_id2, happened = pull_request_changed(pr.as_json())

    assert not happened
    assert issue_id2 == issue_id1
    issue = fake_jira.issues[issue_id2]
    # The bot didn't make another comment.
    assert len(pr.list_comments()) == 1
    # The issue should still have the ad-hoc label.
    assert "my-label" in issue.labels


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
