from datetime import datetime

import pytest

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    has_contractor_comment,
    pull_request_opened,
)

pytestmark = [
    pytest.mark.usefixtures('mock_github'),
    pytest.mark.usefixtures('mock_jira'),
]


def make_pull_request(
        user, title="generic title", body="generic body", number=1,
        base_repo_name="edx/edx-platform", head_repo_name=None,
        base_ref="master", head_ref="patch-1", user_type="User",
        created_at=None
):
    # This should really use a framework like factory_boy.
    created_at = created_at or datetime.now().replace(microsecond=0)
    if head_repo_name is None:
        head_repo_name = "{}/edx-platform".format(user)
    return {
        "user": {
            "login": user,
            "type": user_type,
            "url": "https://api.github.com/users/{}".format(user),
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
        },
        "html_url": "https://github.com/{}/pull/{}".format(base_repo_name, number),
    }


def mock_comments(requests_mocker, pr, comments):
    """Mock the requests to get comments on a PR."""
    comment_data = [{"oops": "wut?"} for c in comments]
    requests_mocker.get(
        "https://api.github.com/repos/{repo}/issues/{num}/comments".format(
            repo=pr["base"]["repo"]["full_name"],
            num=pr["number"],
        ),
        json=comment_data,
    )

def make_jira_issue(key="ABC-123"):
    return {
        "key": key,
    }


def test_community_pr_comment(reqctx):
    # A pull request from a member in good standing.
    pr = make_pull_request(user="tusbar", head_ref="tusbar/cool-feature")
    jira = make_jira_issue(key="TNL-12345")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert "can't start reviewing your pull request" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_community_pr_comment_no_author(reqctx):
    pr = make_pull_request(user="FakeUser")
    jira = make_jira_issue(key="FOO-1")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert "can't start reviewing your pull request" in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(reqctx):
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
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is True


def test_has_contractor_comment_unrelated_comments(app, reqctx, requests_mocker):
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
    )
    pr = make_pull_request(user="testuser", number=1)
    with reqctx:
        github_contractor_pr_comment(pr)
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
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_has_contractor_comment_no_comments(app, reqctx, requests_mocker):
    requests_mocker.get(
        "https://api.github.com/user",
        json={"login": "testuser"},
    )
    pr = make_pull_request(user="testuser", number=1)
    requests_mocker.get(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        json=[],
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_internal_pr_opened(requests_mocker):
    pr = make_pull_request(user='nedbat')
    result = pull_request_opened(pr)
    assert result[1] is False
    history = requests_mocker.request_history
    for request_mock in history:
        assert request_mock.url != "https://api.github.com/repos/edx/edx-platform/issues/1/comments"


def test_pr_opened_by_bot(reqctx):
    pr = make_pull_request(user="some_bot", user_type="Bot")
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert not anything_happened


def test_external_pr_opened(reqctx, requests_mocker, mock_jira):
    pr = make_pull_request(user='new_contributor')
    mock_comments(requests_mocker, pr, [])
    comment_post = requests_mocker.post(
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
    )
    requests_mocker.get(
        "https://api.github.com/users/new_contributor",
        json={
            "login": "new_contributor",
            "name": "Newb Contributor",
            "type": "User",
        }
    )
    adjust_labels_patch = requests_mocker.patch(
        "https://api.github.com/repos/edx/edx-platform/issues/1",
    )

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert issue_id == mock_jira.created_issues[0]
    assert anything_happened

    # Check the Jira issue that was created.
    assert len(mock_jira.new_issue_post.request_history) == 1
    assert mock_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            mock_jira.CONTRIBUTOR_NAME: "Newb Contributor",
            mock_jira.PR_NUMBER: 1,
            mock_jira.REPO: "edx/edx-platform",
            mock_jira.URL: "https://github.com/edx/edx-platform/pull/1",
            "description": "generic body",
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": "generic title",
        }
    }

    # Check the GitHub comment that was created.
    assert len(comment_post.request_history) == 1
    body = comment_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @new_contributor!" in body
    assert "We can't start reviewing your pull request until you've submitted" in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert adjust_labels_patch.request_history[0].json() == {
        "labels": ["needs triage", "open-source-contribution"],
    }
