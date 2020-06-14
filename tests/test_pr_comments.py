"""Tests of the comment creation functions in tasks/github.py."""

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    has_contractor_comment,
)

from . import template_snips


def test_community_pr_comment(reqctx, fake_github, fake_jira):
    # A pull request from a member in good standing.
    pr = fake_github.make_pull_request(user="tusbar", head_ref="tusbar/cool-feature")
    jira = fake_jira.make_issue(key="TNL-12345")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert template_snips.NO_CLA_TEXT not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_community_pr_comment_no_author(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="FakeUser")
    jira = fake_jira.make_issue(key="FOO-1")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert template_snips.NO_CLA_TEXT in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="FakeUser")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    assert "you're a member of a company that does contract work for edX" in comment
    href = (
        'href="https://openedx-webhooks.herokuapp.com/github/process_pr' +
        '?repo={}'.format(pr["base"]["repo"]["full_name"].replace("/", "%2F")) +
        '&number={}"'.format(pr["number"])
    )
    assert href in comment
    assert 'Create an OSPR issue for this pull request' in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_has_contractor_comment(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_json = {
        "user": {
            "login": fake_github.WEBHOOK_BOT_NAME,
        },
        "body": comment
    }
    fake_github.fake_comments(pr, [comment_json])

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is True


def test_has_contractor_comment_unrelated_comments(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")
    comments = [
        {
            # A bot comment, but not about contracting.
            "user": {
                "login": fake_github.WEBHOOK_BOT_NAME,
            },
            "body": "this comment is unrelated",
        },
        {
            # This comment will be ignored because it's not made by our bot user
            "user": {
                "login": "different_user",
            },
            "body": template_snips.CONTRACTOR_TEXT,
        }
    ]
    fake_github.fake_comments(pr, comments)

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is False


def test_has_contractor_comment_no_comments(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="testuser")
    fake_github.fake_comments(pr, [])

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is False
