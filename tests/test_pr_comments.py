"""Tests of the comment creation functions in tasks/github.py."""

import pytest

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    has_contractor_comment,
    get_blended_project_id,
)

from . import template_snips


def test_community_pr_comment(reqctx, fake_github, fake_jira):
    # A pull request from a member in good standing.
    pr = fake_github.make_pull_request(user="tusbar")
    jira = fake_jira.make_issue(key="TNL-12345")
    with reqctx:
        comment = github_community_pr_comment(pr.as_json(), jira.as_json())
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert template_snips.NO_CLA_TEXT not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_community_pr_comment_no_author(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="FakeUser")
    jira = fake_jira.make_issue(key="FOO-1")
    with reqctx:
        comment = github_community_pr_comment(pr.as_json(), jira.as_json())
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert template_snips.NO_CLA_TEXT in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="FakeUser")
    prj = pr.as_json()
    with reqctx:
        comment = github_contractor_pr_comment(prj)
    assert "you're a member of a company that does contract work for edX" in comment
    href = (
        'href="https://openedx-webhooks.herokuapp.com/github/process_pr' +
        '?repo={}'.format(prj["base"]["repo"]["full_name"].replace("/", "%2F")) +
        '&number={}"'.format(prj["number"])
    )
    assert href in comment
    assert 'Create an OSPR issue for this pull request' in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_has_contractor_comment(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")
    with reqctx:
        comment = github_contractor_pr_comment(pr.as_json())
    pr.add_comment(user=fake_github.login, body=comment)

    with reqctx:
        result = has_contractor_comment(pr.as_json())
    assert result is True


def test_has_contractor_comment_unrelated_comments(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")
    pr.add_comment(user=fake_github.login, body="this comment is unrelated")
    pr.add_comment(user="different_user", body=template_snips.CONTRACTOR_TEXT)

    with reqctx:
        result = has_contractor_comment(pr.as_json())
    assert result is False


def test_has_contractor_comment_no_comments(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")

    with reqctx:
        result = has_contractor_comment(pr.as_json())
    assert result is False


@pytest.mark.parametrize("title, number", [
    ("Please take my change", None),
    ("[BD-17] Fix typo", 17),
    ("This is for [  BD-007]", 7),
    ("Blended BD-18 doesn't count", None)
])
def test_get_blended_project_id(fake_github, title, number):
    pr = fake_github.make_pull_request(title=title)
    num = get_blended_project_id(pr.as_json())
    assert number == num
