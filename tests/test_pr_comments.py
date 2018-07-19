from datetime import datetime

import pytest

from openedx_webhooks.tasks.github import (
    COVERLETTER_MARKER, github_community_pr_comment,
    github_contractor_pr_comment, github_internal_cover_letter,
    has_contractor_comment, has_internal_cover_letter
)

pytestmark = pytest.mark.usefixtures('mock_github')


def make_pull_request(
        user, title="generic title", body="generic body", number=1,
        base_repo_name="edx/edx-platform", head_repo_name=None,
        base_ref="master", head_ref="patch-1",
        created_at=None
):
    # This should really use a framework like factory_boy.
    created_at = created_at or datetime.now().replace(microsecond=0)
    if head_repo_name is None:
        head_repo_name = "{}/edx-platform".format(user)
    return {
        "user": {
            "login": user,
        },
        "number": number,
        "title": title,
        "body": body,
        "created_at": created_at.isoformat(),
        "head": {
            "repo": {
                "full_name": head_repo_name,
            },
            "ref": head_ref,
        },
        "base": {
            "repo": {
                "full_name": base_repo_name,
            },
            "ref": base_ref,
        }
    }


def make_jira_issue(key="ABC-123"):
    return {
        "key": key,
    }


@pytest.mark.skip(reason=(
    'failing due to '
    '`BetamaxError: A request was made that could not be handled.`'
))
def test_community_pr_comment(app, requests_mocker):
    # A pull request from a member in good standing.
    pr = make_pull_request(user="tusbar", head_ref="tusbar/cool-feature")
    jira = make_jira_issue(key="TNL-12345")
    # An AUTHORS file that contains the author.
    requests_mocker.get(
        "https://raw.githubusercontent.com/tusbar/edx-platform/tusbar/cool-feature/AUTHORS",
        text="Bertrand Marron <tusbar@tusbar.com>\n",
    )
    with app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert "can't start reviewing your pull request" not in comment
    assert "you can add yourself to the [AUTHORS]" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


@pytest.mark.skip(reason=(
    'failing due to '
    '`BetamaxError: A request was made that could not be handled.`'
))
def test_community_pr_comment_not_in_authors_file(app, requests_mocker):
    pr = make_pull_request(user="tusbar", head_ref="tusbar/fix-bug-1234")
    jira = make_jira_issue(key="TNL-12345")
    # An AUTHORS file that doesn't contain the author.
    requests_mocker.get(
        "https://raw.githubusercontent.com/tusbar/edx-platform/tusbar/fix-bug-1234/AUTHORS",
        text="Ned Batchelder <ned@edx.org>\n",
    )
    with app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert "can't start reviewing your pull request" not in comment
    assert "you can add yourself to the [AUTHORS]" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


@pytest.mark.skip(reason=(
    'failing due to '
    '`BetamaxError: A request was made that could not be handled.`'
))
def test_community_pr_comment_no_authors_file_at_all(app, requests_mocker):
    pr = make_pull_request(user="tusbar", head_ref="tusbar/fix-bug-1234")
    jira = make_jira_issue(key="TNL-12345")
    # There is no AUTHORS file?!
    requests_mocker.get(
        "https://raw.githubusercontent.com/tusbar/edx-platform/tusbar/fix-bug-1234/AUTHORS",
        status_code=404,
    )
    with app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert "can't start reviewing your pull request" not in comment
    assert "you can add yourself to the [AUTHORS]" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_community_pr_comment_no_author(app):
    pr = make_pull_request(user="FakeUser")
    jira = make_jira_issue(key="FOO-1")
    with app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert "can't start reviewing your pull request" in comment
    assert "you can add yourself to the [AUTHORS]" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(app, reqctx):
    pr = make_pull_request(user="FakeUser")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    assert "you're a member of a company that does contract work for edX" in comment
    href = (
        'href="https://openedx-webhooks.herokuapp.com/github/process_pr'
        '?repo=edx%2Fedx-platform&number=1"'
    )
    assert href in comment
    assert 'Create an OSPR issue for this pull request' in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_has_contractor_comment(app, reqctx, requests_mocker):
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    pr = make_pull_request(user="testuser", number=1)
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_json = {
        "user": {
            "login": "testuser",
        },
        "body": comment
    }
    requests_mocker.get(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        json=[comment_json],
        headers={"Content-Type": "application/json"},
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is True


def test_has_contractor_comment_unrelated_comments(app, reqctx, requests_mocker):
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    pr = make_pull_request(user="testuser", number=1)
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comments_json = [
        {
            "user": {
                "login": "testuser",
            },
            "body": "this comment is unrelated",
        },
        {
            # this comment will be ignored
            # because it's not made by our bot user
            "user": {
                "login": "different_user",
            },
            "body": "It looks like you're a member of a company that does contract work for edX.",
        }
    ]
    requests_mocker.get(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        json=comments_json,
        headers={"Content-Type": "application/json"},
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_has_contractor_comment_no_comments(app, reqctx, requests_mocker):
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    pr = make_pull_request(user="testuser", number=1)
    requests_mocker.get(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        json=[],
        headers={"Content-Type": "application/json"},
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_internal_pr_cover_letter(reqctx):
    pr = make_pull_request(
        user="FakeUser", body="this is my first pull request",
        head_repo_name="testuser/edx-platform",
    )
    with reqctx:
        comment = github_internal_cover_letter(pr)
    assert comment is None


def test_has_internal_pr_cover_letter(reqctx, requests_mocker):
    pr = make_pull_request(
        user="different_user", body="omg this code is teh awesomezors",
        head_ref="patch-1",
    )
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    requests_mocker.get(
        "https://raw.githubusercontent.com/different_user/edx-platform/patch-1/.pr_cover_letter.md.j2",
        text="Fancy cover letter!",
    )

    with reqctx:
        comment_body = github_internal_cover_letter(pr)
    comments_json = [
        {
            "user": {
                "login": "testuser",
            },
            "body": comment_body,
        },
    ]
    requests_mocker.get(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        json=comments_json,
        headers={"Content-Type": "application/json"},
    )

    with reqctx:
        result = has_internal_cover_letter(pr)
    assert result is True


def test_has_internal_pr_cover_letter_false(reqctx, requests_mocker):
    pr = make_pull_request(
        user="testuser", body="omg this code is teh awesomezors",
    )
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    with reqctx:
        result = has_internal_cover_letter(pr)
    assert result is False


def test_custom_internal_pr_cover(reqctx, requests_mocker):
    pr = make_pull_request(
        user="different_user", body="omg this code is teh awesomezors",
        head_ref="patch-1",
    )
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
        headers={"Content-Type": "application/json"},
    )
    requests_mocker.get(
        "https://raw.githubusercontent.com/different_user/edx-platform/patch-1/.pr_cover_letter.md.j2",
        text='custom cover letter for PR from @{{ user }}',
    )

    with reqctx:
        comment_body = github_internal_cover_letter(pr)
    assert comment_body.startswith('custom cover letter for PR from @different_user')
    assert comment_body.endswith(COVERLETTER_MARKER)
