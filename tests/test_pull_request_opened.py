"""Tests of task/github.py:pull_request_opened."""

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    pull_request_opened,
)

from . import template_snips


def test_internal_pr_opened(reqctx, mock_github):
    pr = mock_github.make_pull_request(user='nedbat')
    comments_post = mock_github.comments_post(pr)
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert anything_happened is False
    assert len(comments_post.request_history) == 0


def test_pr_opened_by_bot(reqctx, mock_github):
    pr = mock_github.make_pull_request(user="some_bot", user_type="Bot")
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert anything_happened is False


def test_external_pr_opened(reqctx, mock_github, mock_jira):
    mock_github.mock_user({"login": "new_contributor", "name": "Newb Contributor"})
    pr = mock_github.make_pull_request(user='new_contributor')
    mock_github.mock_comments(pr, [])
    comments_post = mock_github.comments_post(pr)
    adjust_labels_patch = mock_github.pr_patch(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert issue_id == mock_jira.created_issues[0]
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(mock_jira.new_issue_post.request_history) == 1
    assert mock_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            mock_jira.CONTRIBUTOR_NAME: "Newb Contributor",
            mock_jira.PR_NUMBER: pr["number"],
            mock_jira.REPO: pr["base"]["repo"]["full_name"],
            mock_jira.URL: pr["html_url"],
            "description": pr["body"],
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": pr["title"],
        }
    }

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @new_contributor!" in body
    assert template_snips.NO_CLA_TEXT in body
    assert template_snips.NO_CLA_LINK in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert adjust_labels_patch.request_history[0].json() == {
        "labels": ["needs triage", "open-source-contribution"],
    }


def test_external_pr_opened_with_cla(reqctx, mock_github, mock_jira):
    pr = mock_github.make_pull_request(user='tusbar')
    mock_github.mock_comments(pr, [])
    comments_post = mock_github.comments_post(pr)
    adjust_labels_patch = mock_github.pr_patch(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert issue_id == mock_jira.created_issues[0]
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(mock_jira.new_issue_post.request_history) == 1
    assert mock_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            mock_jira.CONTRIBUTOR_NAME: "Bertrand Marron",
            mock_jira.CUSTOMER: ["IONISx"],
            mock_jira.PR_NUMBER: pr["number"],
            mock_jira.REPO: pr["base"]["repo"]["full_name"],
            mock_jira.URL: pr["html_url"],
            "description": pr["body"],
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": pr["title"],
        }
    }

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @tusbar!" in body
    assert template_snips.NO_CLA_TEXT not in body
    assert template_snips.NO_CLA_LINK not in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert adjust_labels_patch.request_history[0].json() == {
        "labels": ["needs triage", "open-source-contribution"],
    }


def test_external_pr_rescanned(reqctx, mock_github, mock_jira):
    mock_github.mock_user({"login": "new_contributor", "name": "Newb Contributor"})
    pr = mock_github.make_pull_request(user='new_contributor')
    with reqctx:
        comment = github_community_pr_comment(pr, jira_issue=mock_jira.make_issue(key="OSPR-12345"))
    comment_data = {
        "user": {"login": mock_github.WEBHOOK_BOT_NAME},
        "body": comment,
    }
    mock_github.mock_comments(pr, [comment_data])
    comments_post = mock_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id == "OSPR-12345"
    assert anything_happened is False

    # No Jira issue was created.
    assert len(mock_jira.new_issue_post.request_history) == 0

    # No new GitHub comment was created.
    assert len(comments_post.request_history) == 0


def test_contractor_pr_opened(reqctx, mock_github, mock_jira):
    pr = mock_github.make_pull_request(user="joecontractor")
    mock_github.mock_comments(pr, [])
    comments_post = mock_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is None
    assert anything_happened is True

    # No Jira issue was created.
    assert len(mock_jira.new_issue_post.request_history) == 0

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    assert template_snips.CONTRACTOR_TEXT in body
    href = (
        'href="https://openedx-webhooks.herokuapp.com/github/process_pr' +
        '?repo={}'.format(pr["base"]["repo"]["full_name"].replace("/", "%2F")) +
        '&number={}"'.format(pr["number"])
    )
    assert href in body
    assert 'Create an OSPR issue for this pull request' in body


def test_contractor_pr_rescanned(reqctx, mock_github, mock_jira):
    pr = mock_github.make_pull_request(user="joecontractor")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_data = {
        "user": {"login": mock_github.WEBHOOK_BOT_NAME},
        "body": comment,
    }
    mock_github.mock_comments(pr, [comment_data])
    comments_post = mock_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is None
    assert anything_happened is False

    # No Jira issue was created.
    assert len(mock_jira.new_issue_post.request_history) == 0

    # No new GitHub comment was created.
    assert len(comments_post.request_history) == 0
