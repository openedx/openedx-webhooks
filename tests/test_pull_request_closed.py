"""Tests of task/github.py:pull_request_changed for closing pull requests."""

from datetime import datetime

import pytest

from openedx_webhooks.info import get_bot_username, pull_request_has_cla
from openedx_webhooks.tasks.github import pull_request_changed
from .helpers import random_text

# These tests should run when we want to test flaky GitHub behavior.
pytestmark = pytest.mark.flaky_github


def test_internal_pr_closed(is_merged, reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="nedbat", state="closed", merged=is_merged)
    pr.add_comment(user="nedbat", body="This is great")
    pr.add_comment(user="feanil", body="Eh, it's ok")

    with reqctx:
        pull_request_changed(pr.as_json())

    # No Jira issue for this PR, so we should have never talked to Jira.
    assert len(fake_jira.requests_made()) == 0


@pytest.fixture
def closed_pull_request(is_merged, reqctx, fake_github, fake_jira):
    """
    Create a closed pull request and an issue key for it.

    Returns (pr, issue_key)
    """
    pr = fake_github.make_pull_request(
        user="tusbar",
        title=random_text(),
        )
    with reqctx:
        issue_key, _ = pull_request_changed(pr.as_json())

    pr.add_comment(user="nedbat", body="Please make some changes")
    pr.add_comment(user="tusbar", body="OK, I made the changes")
    pr.close(merge=is_merged)

    fake_jira.reset_mock()

    return pr, issue_key


def test_external_pr_closed(is_merged, reqctx, fake_jira, closed_pull_request):
    pr, issue_key = closed_pull_request

    with reqctx:
        pull_request_changed(pr.as_json())

    # We moved the Jira issue to Merged or Rejected.
    expected_status = "Merged" if is_merged else "Rejected"
    assert fake_jira.issues[issue_key].status == expected_status


def test_external_pr_closed_but_issue_deleted(is_merged, reqctx, fake_jira, closed_pull_request):
    # A closing pull request, but its Jira issue has been deleted.
    pr, old_issue_key = closed_pull_request
    del fake_jira.issues[old_issue_key]

    with reqctx:
        issue_id, anything_happened = pull_request_changed(pr.as_json())

    assert issue_id is None
    assert anything_happened

    pr_comments = pr.list_comments()
    assert len(pr_comments) == 3    # closed_pull_request makes two
    # We leave the old issue id in the comment.
    body = pr_comments[0].body
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=old_issue_key)
    assert jira_link in body


def test_external_pr_closed_but_issue_in_status(is_merged, reqctx, fake_jira, closed_pull_request):
    # The Jira issue associated with a closing pull request is already in the
    # status we want to move it to.
    pr, issue_key = closed_pull_request
    fake_jira.issues[issue_key].status = ("Merged" if is_merged else "Rejected")

    with reqctx:
        pull_request_changed(pr.as_json())

    # Issue is already correct, so nothing was transitioned.
    assert fake_jira.requests_made(method="POST") == []


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
            pull_request_changed(pr.as_json())

    # No valid transition, so nothing was transitioned.
    assert fake_jira.requests_made(method="POST") == []


def test_cc_pr_closed(reqctx, fake_github, fake_jira, is_merged):
    # When a core committer merges a pull request, ping the champions.
    # But when it's closed without merging, no ping.
    # Use body=None here to test missing bodies also.
    pr = fake_github.make_pull_request(user="felipemontoya", owner="edx", repo="edx-platform", body=None)

    with reqctx:
        pull_request_changed(pr.as_json())

    pr.close(merge=is_merged)

    with reqctx:
        pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    if is_merged:
        assert len(pr_comments) == 2
        assert "@nedbat, @feanil: thought you might like to know" in pr_comments[1].body
    else:
        assert len(pr_comments) == 1

    # Processing it again won't change anything.
    with reqctx:
        pull_request_changed(pr.as_json())

    pr_comments = pr.list_comments()
    if is_merged:
        assert len(pr_comments) == 2
    else:
        assert len(pr_comments) == 1


def test_track_additions_deletions(reqctx, fake_github, fake_jira, is_merged):
    pr = fake_github.make_pull_request(user="tusbar", additions=17, deletions=42)
    with reqctx:
        issue_id, _ = pull_request_changed(pr.as_json())

    issue = fake_jira.issues[issue_id]
    assert issue.lines_added == 17
    assert issue.lines_deleted == 42

    pr.additions = 34
    pr.deletions = 1001
    pr.close(merge=is_merged)

    with reqctx:
        pull_request_changed(pr.as_json())

    issue = fake_jira.issues[issue_id]
    assert issue.lines_added == 34
    assert issue.lines_deleted == 1001


def test_rescan_closed_with_wrong_cla(reqctx, fake_github, fake_jira):
    # No CLA, because this person had no agreement when the pr was made.
    pr = fake_github.make_pull_request(
        user="raisingarizona", created_at=datetime(2015, 6, 15), state="closed", merged=True,
    )
    assert not pull_request_has_cla(pr.as_json())
    # But the bot comment doesn't indicate "no cla", because people.yaml is wrong.
    body = "A ticket: OSPR-1234!\n<!-- comment:external_pr -->"
    pr.add_comment(user=get_bot_username(), body=body)

    with reqctx:
        pull_request_changed(pr.as_json())

    # The fixer will think, the bot comment needs to have no_cla added to it,
    # and will want to edit the bot comment.  But we shouldn't change existing
    # bot comments on closed pull requests.
    pr_comments = pr.list_comments()
    assert len(pr_comments) == 1
    assert pr_comments[0].body == body
