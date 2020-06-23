"""Tests of task/github.py:pull_request_opened."""

from openedx_webhooks.tasks.github import (
    github_community_pr_comment,
    github_contractor_pr_comment,
    pull_request_opened,
)

from . import template_snips


def test_internal_pr_opened(reqctx, fake_github):
    pr = fake_github.make_pull_request(user='nedbat')
    comments_post = fake_github.comments_post(pr)
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert anything_happened is False
    assert len(comments_post.request_history) == 0


def test_pr_opened_by_bot(reqctx, fake_github):
    pr = fake_github.make_pull_request(user="some_bot", user_type="Bot")
    with reqctx:
        key, anything_happened = pull_request_opened(pr)
    assert key is None
    assert anything_happened is False


def test_external_pr_opened_no_cla(reqctx, mocker, fake_github, fake_jira):
    fake_github.fake_user({"login": "new_contributor", "name": "Newb Contributor"})
    pr = fake_github.make_pull_request(user='new_contributor')
    fake_github.fake_comments(pr, [])
    comments_post = fake_github.comments_post(pr)
    sync_labels_fn = mocker.patch("openedx_webhooks.tasks.github.synchronize_labels")
    adjust_labels_patch = fake_github.pr_patch(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(fake_jira.new_issue_post.request_history) == 1
    assert fake_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            fake_jira.CONTRIBUTOR_NAME: "Newb Contributor",
            fake_jira.PR_NUMBER: pr["number"],
            fake_jira.REPO: pr["base"]["repo"]["full_name"],
            fake_jira.URL: pr["html_url"],
            "description": pr["body"],
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": pr["title"],
            "labels": [],
        }
    }
    assert len(fake_jira.issues) == 1
    assert issue_id in fake_jira.issues

    # Check that the Jira issue was moved to Community Manager Review.
    assert fake_jira.issues[issue_id]["fields"]["status"]["name"] == "Community Manager Review"

    # Check that we synchronized labels.
    sync_labels_fn.assert_called_once_with("edx/edx-platform")

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @new_contributor!" in body
    assert template_snips.EXTERNAL_TEXT in body
    assert template_snips.NO_CLA_TEXT in body
    assert template_snips.NO_CLA_LINK in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert set(adjust_labels_patch.request_history[0].json()["labels"]) == {
        "community manager review", "open-source-contribution",
    }


def test_external_pr_opened_with_cla(reqctx, mocker, fake_github, fake_jira):
    pr = fake_github.make_pull_request(
        user="tusbar",
        base_repo_name="edx/some-code",
        number=11235,
    )
    fake_github.fake_comments(pr, [])
    comments_post = fake_github.comments_post(pr)
    sync_labels_fn = mocker.patch("openedx_webhooks.tasks.github.synchronize_labels")
    adjust_labels_patch = fake_github.pr_patch(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(fake_jira.new_issue_post.request_history) == 1
    assert fake_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            fake_jira.CONTRIBUTOR_NAME: "Bertrand Marron",
            fake_jira.CUSTOMER: ["IONISx"],
            fake_jira.PR_NUMBER: 11235,
            fake_jira.REPO: "edx/some-code",
            fake_jira.URL: pr["html_url"],
            "description": pr["body"],
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": pr["title"],
            "labels": [],
        }
    }

    assert len(fake_jira.issues) == 1
    assert issue_id in fake_jira.issues

    # Check that the Jira issue is in Needs Triage.
    assert fake_jira.issues[issue_id]["fields"]["status"]["name"] == "Needs Triage"

    # Check that we synchronized labels.
    sync_labels_fn.assert_called_once_with("edx/some-code")

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @tusbar!" in body
    assert template_snips.EXTERNAL_TEXT in body
    assert template_snips.NO_CLA_TEXT not in body
    assert template_snips.NO_CLA_LINK not in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert set(adjust_labels_patch.request_history[0].json()["labels"]) == {
        "needs triage", "open-source-contribution",
    }


def test_core_committer_pr_opened(reqctx, mocker, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="felipemontoya")
    fake_github.fake_comments(pr, [])
    comments_post = fake_github.comments_post(pr)
    sync_labels_fn = mocker.patch("openedx_webhooks.tasks.github.synchronize_labels")
    adjust_labels_patch = fake_github.pr_patch(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is not None
    assert issue_id.startswith("OSPR-")
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(fake_jira.new_issue_post.request_history) == 1
    assert fake_jira.new_issue_post.request_history[0].json() == {
        "fields": {
            fake_jira.CONTRIBUTOR_NAME: "Felipe Montoya",
            fake_jira.CUSTOMER: ["EduNEXT"],
            fake_jira.PR_NUMBER: pr["number"],
            fake_jira.REPO: pr["base"]["repo"]["full_name"],
            fake_jira.URL: pr["html_url"],
            "description": pr["body"],
            "issuetype": {"name": "Pull Request Review"},
            "project": {"key": "OSPR"},
            "summary": pr["title"],
            "labels": ["core committer"],
        }
    }

    assert len(fake_jira.issues) == 1
    assert issue_id in fake_jira.issues

    # Check that the Jira issue was moved to Engineering Review.
    assert fake_jira.issues[issue_id]["fields"]["status"]["name"] == "Engineering Review"

    # Check that we synchronized labels.
    sync_labels_fn.assert_called_once_with("edx/edx-platform")

    # Check the GitHub comment that was created.
    assert len(comments_post.request_history) == 1
    body = comments_post.request_history[0].json()["body"]
    jira_link = "[{id}](https://openedx.atlassian.net/browse/{id})".format(id=issue_id)
    assert jira_link in body
    assert "Thanks for the pull request, @felipemontoya!" in body
    assert template_snips.CORE_COMMITTER_TEXT in body
    assert template_snips.NO_CLA_TEXT not in body
    assert template_snips.NO_CLA_LINK not in body

    # Check the GitHub labels that got applied.
    assert len(adjust_labels_patch.request_history) == 1
    assert set(adjust_labels_patch.request_history[0].json()["labels"]) == {
        "engineering review", "open-source-contribution", "core committer",
    }


def test_external_pr_rescanned(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="tusbar")
    with reqctx:
        comment = github_community_pr_comment(pr, jira_issue=fake_jira.make_issue(key="OSPR-12345"))
    comment_data = {
        "user": {"login": fake_github.WEBHOOK_BOT_NAME},
        "body": comment,
    }
    fake_github.fake_comments(pr, [comment_data])
    comments_post = fake_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id == "OSPR-12345"
    assert anything_happened is False

    # No Jira issue was created.
    assert len(fake_jira.new_issue_post.request_history) == 0

    # No new GitHub comment was created.
    assert len(comments_post.request_history) == 0


def test_contractor_pr_opened(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="joecontractor")
    fake_github.fake_comments(pr, [])
    comments_post = fake_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is None
    assert anything_happened is True

    # No Jira issue was created.
    assert len(fake_jira.new_issue_post.request_history) == 0

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


def test_contractor_pr_rescanned(reqctx, fake_github, fake_jira):
    pr = fake_github.make_pull_request(user="joecontractor")
    with reqctx:
        comment = github_contractor_pr_comment(pr)
    comment_data = {
        "user": {"login": fake_github.WEBHOOK_BOT_NAME},
        "body": comment,
    }
    fake_github.fake_comments(pr, [comment_data])
    comments_post = fake_github.comments_post(pr)

    with reqctx:
        issue_id, anything_happened = pull_request_opened(pr)

    assert issue_id is None
    assert anything_happened is False

    # No Jira issue was created.
    assert len(fake_jira.new_issue_post.request_history) == 0

    # No new GitHub comment was created.
    assert len(comments_post.request_history) == 0
