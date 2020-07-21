"""Tests of the comment creation functions in tasks/github.py."""

from openedx_webhooks.bot_comments import (
    BotComment,
    is_comment_kind,
    github_community_pr_comment,
    github_contractor_pr_comment,
)

from .helpers import is_good_markdown


def test_community_pr_comment(reqctx, fake_github, fake_jira):
    # A pull request from a member in good standing.
    pr = fake_github.make_pull_request(user="tusbar")
    jira = fake_jira.make_issue(key="TNL-12345")
    with reqctx:
        comment = github_community_pr_comment(pr.as_json(), jira.key)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert not is_comment_kind(BotComment.NEED_CLA, comment)
    assert is_good_markdown(comment)


def test_community_pr_comment_no_author(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="FakeUser")
    jira = fake_jira.make_issue(key="FOO-1")
    with reqctx:
        comment = github_community_pr_comment(pr.as_json(), jira.key)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert is_comment_kind(BotComment.NEED_CLA, comment)
    assert (
        "[signed contributor agreement]" +
        "(https://open.edx.org/wp-content/uploads/2019/01/individual-contributor-agreement.pdf)"
    ) in comment
    assert is_good_markdown(comment)


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
    assert is_good_markdown(comment)
