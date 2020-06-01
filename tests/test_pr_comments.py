from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    has_contractor_comment,
    pull_request_opened,
)

def make_jira_issue(key="ABC-123"):
    return {
        "key": key,
    }


def test_community_pr_comment(reqctx, mock_github):
    # A pull request from a member in good standing.
    pr = mock_github.make_pull_request(user="tusbar", head_ref="tusbar/cool-feature")
    jira = make_jira_issue(key="TNL-12345")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[TNL-12345](https://openedx.atlassian.net/browse/TNL-12345)" in comment
    assert "can't start reviewing your pull request" not in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_community_pr_comment_no_author(reqctx, mock_github):
    pr = mock_github.make_pull_request(user="FakeUser")
    jira = make_jira_issue(key="FOO-1")
    with reqctx:
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert "can't start reviewing your pull request" in comment
    assert not comment.startswith((" ", "\n", "\t"))


def test_contractor_pr_comment(reqctx, mock_github):
    pr = mock_github.make_pull_request(user="FakeUser")
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


def test_has_contractor_comment(app, reqctx, mock_github):
    pr = mock_github.make_pull_request(user="testuser")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_json = {
        "user": {
            "login": mock_github.WEBHOOK_BOT_NAME,
        },
        "body": comment
    }
    mock_github.mock_comments(pr, [comment_json])

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is True


def test_has_contractor_comment_unrelated_comments(app, reqctx, mock_github):
    pr = mock_github.make_pull_request(user="testuser")
    comments = [
        {
            # A bot comment, but not about contracting.
            "user": {
                "login": mock_github.WEBHOOK_BOT_NAME,
            },
            "body": "this comment is unrelated",
        },
        {
            # This comment will be ignored because it's not made by our bot user
            "user": {
                "login": "different_user",
            },
            "body": "It looks like you're a member of a company that does contract work for edX.",
        }
    ]
    mock_github.mock_comments(pr, comments)

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is False


def test_has_contractor_comment_no_comments(app, reqctx, mock_github):
    pr = mock_github.make_pull_request(user="testuser")
    mock_github.mock_comments(pr, [])

    with reqctx:
        result = has_contractor_comment(pr)
    assert result is False


def test_internal_pr_opened(requests_mocker, mock_github):
    pr = mock_github.make_pull_request(user='nedbat')
    result = pull_request_opened(pr)
    assert result[1] is False
    history = requests_mocker.request_history
    for request_mock in history:
        assert request_mock.url != "https://api.github.com/repos/edx/edx-platform/issues/1/comments"


def test_pr_opened_by_bot(reqctx, mock_github):
    pr = mock_github.make_pull_request(user="some_bot", user_type="Bot")
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert anything_happened is False


def test_external_pr_opened(reqctx, requests_mocker, mock_github, mock_jira):
    pr = mock_github.make_pull_request(user='new_contributor')
    mock_github.mock_comments(pr, [])
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
    assert anything_happened is True

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
