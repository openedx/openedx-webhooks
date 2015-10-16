import json
import pytest
import requests
from datetime import datetime
import openedx_webhooks
from openedx_webhooks.tasks.github import (
    github_community_pr_comment, github_contractor_pr_comment,
    github_internal_cover_letter,
    has_contractor_comment, has_internal_cover_letter
)


def make_pull_request(
        user, title="generic title", body="generic body", number=1,
        base_repo_name="edx/edx-platform", head_repo_name="edx/edx-platform",
        created_at=None
    ):
    "this should really use a framework like factory_boy"
    created_at = created_at or datetime.now().replace(microsecond=0)
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
            }
        },
        "base": {
            "repo": {
                "full_name": base_repo_name,
            }
        }
    }

def make_jira_issue(key="ABC-123"):
    return {
        "key": key,
    }


def test_community_pr_comment(app, mock_github):
    pr = make_pull_request(user="FakeUser")
    jira = make_jira_issue(key="FOO-1")
    with app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert "can't start reviewing your pull request" in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(app, reqctx):
    pr = make_pull_request(user="FakeUser")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    assert "you're a member of a company that does contract work for edX" in comment
    assert "visit this link: https://" in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_has_contractor_comment(app, reqctx, responses):
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        body='{"login": "testuser"}',
        content_type="application/json",
    )
    pr = make_pull_request(
        user="testuser", number=1, base_repo_name="edx/edx-platform",
    )
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_json = {
        "user": {
            "login": "testuser",
        },
        "body": comment
    }
    responses.add(
        responses.GET,
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        body=json.dumps([comment_json]),
        content_type="application/json",
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is True


def test_has_contractor_comment_unrelated_comments(app, reqctx, responses):
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        body='{"login": "testuser"}',
        content_type="application/json",
    )
    pr = make_pull_request(
        user="testuser", number=1, base_repo_name="edx/edx-platform",
    )
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
    responses.add(
        responses.GET,
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        body=json.dumps(comments_json),
        content_type="application/json",
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_has_contractor_comment_no_comments(app, reqctx, responses):
    responses.add(
        responses.GET,
        "https://api.github.com/user",
        body='{"login": "testuser"}',
        content_type="application/json",
    )
    pr = make_pull_request(
        user="testuser", number=1, base_repo_name="edx/edx-platform",
    )
    responses.add(
        responses.GET,
        "https://api.github.com/repos/edx/edx-platform/issues/1/comments",
        body='[]',
        content_type="application/json",
    )

    with reqctx:
        app.preprocess_request()
        result = has_contractor_comment(pr)
    assert result is False


def test_internal_pr_cover_letter(reqctx):
    pr = make_pull_request(user="FakeUser", body="this is my first pull request")
    with reqctx:
        body = github_internal_cover_letter(pr)
    assert "this is my first pull request" in body
    assert "### Sandbox" in body
    assert "### Testing" in body
    assert "### Reviewers" in body
    assert "### DevOps assistance" in body


def test_has_internal_pr_cover_letter(reqctx):
    pr = make_pull_request(
        user="testuser", body="omg this code is teh awesomezors",
    )
    with reqctx:
        body = github_internal_cover_letter(pr)
    pr["body"] = body
    result = has_internal_cover_letter(pr)
    assert result is True


def test_has_internal_pr_cover_letter_false():
    pr = make_pull_request(
        user="testuser", body="omg this code is teh awesomezors",
    )
    result = has_internal_cover_letter(pr)
    assert result is False
