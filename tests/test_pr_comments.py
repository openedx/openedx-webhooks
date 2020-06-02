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
        'href="https://openedx-webhooks.herokuapp.com/github/process_pr' +
        '?repo={}'.format(pr["base"]["repo"]["full_name"].replace("/", "%2F")) +
        '&number={}"'.format(pr["number"])
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


CLA_TEXT = "We can't start reviewing your pull request until you've submitted"
CLA_LINK = "[signed contributor agreement](https://open.edx.org/wp-content/uploads/2019/01/individual-contributor-agreement.pdf)"

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
    assert CLA_TEXT in body
    assert CLA_LINK in body

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
    assert CLA_TEXT not in body
    assert CLA_LINK not in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert adjust_labels_patch.request_history[0].json() == {
        "labels": ["needs triage", "open-source-contribution"],
    }


def test_external_pr_rescanned(reqctx, mock_github, mock_jira):
    mock_github.mock_user({"login": "new_contributor", "name": "Newb Contributor"})
    pr = mock_github.make_pull_request(user='new_contributor')
    with reqctx:
        comment = github_community_pr_comment(pr, jira_issue=make_jira_issue(key="OSPR-12345"))
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
    assert "you're a member of a company that does contract work for edX" in body
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
