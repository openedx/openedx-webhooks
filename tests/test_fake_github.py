"""Tests of FakeGithub."""

import pytest
import requests

from freezegun import freeze_time
from glom import glom

from .fake_github import FakeGitHub


# pylint: disable=missing-timeout

class TestUsers:
    def test_get_me(self, fake_github):
        resp = requests.get("https://api.github.com/user")
        assert resp.status_code == 200
        assert resp.json() == {"login": "webhook-bot"}

    def test_get_user(self, fake_github):
        fake_github.make_user(login="nedbat", name="Ned Batchelder")
        resp = requests.get("https://api.github.com/users/nedbat")
        assert resp.status_code == 200
        uj = resp.json()
        assert uj["login"] == "nedbat"
        assert uj["name"] == "Ned Batchelder"
        assert uj["type"] == "User"
        assert uj["url"] == "https://api.github.com/users/nedbat"


class TestRepos:
    def test_make_repo(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        assert repo.owner == "an-org"
        assert repo.repo == "a-repo"
        repo2 = fake_github.get_repo("an-org", "a-repo")
        assert repo == repo2


class TestPullRequests:
    def test_make_pull_request(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        with freeze_time("2021-08-31 15:30:12"):
            pr = repo.make_pull_request(
                user="some-user",
                title="Here is a pull request",
                body="It's a good pull request, you should merge it.",
            )
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/pulls/{pr.number}")
        assert resp.status_code == 200
        prj = resp.json()
        assert prj["number"] == pr.number
        assert prj["user"]["login"] == "some-user"
        assert prj["user"]["name"] == "Some User"
        assert prj["user"]["url"] == "https://api.github.com/users/some-user"
        assert prj["user"]["html_url"] == "https://github.com/some-user"
        assert prj["title"] == "Here is a pull request"
        assert prj["body"] == "It's a good pull request, you should merge it."
        assert prj["state"] == "open"
        assert prj["labels"] == []
        assert prj["base"]["repo"]["full_name"] == "an-org/a-repo"
        assert prj["html_url"] == f"https://github.com/an-org/a-repo/pull/{pr.number}"
        assert prj["created_at"] == "2021-08-31T15:30:12Z"
        assert prj["closed_at"] is None

    def test_no_such_pull_request(self, fake_github):
        fake_github.make_repo("an-org", "a-repo")
        resp = requests.get("https://api.github.com/repos/an-org/a-repo/pulls/99")
        assert resp.status_code == 404
        assert resp.json()["message"] == "Pull request an-org/a-repo #99 does not exist"

    def test_no_such_repo_for_pull_request(self, fake_github):
        fake_github.make_repo("an-org", "a-repo")
        resp = requests.get("https://api.github.com/repos/some-user/another-repo/pulls/1")
        assert resp.status_code == 404
        assert resp.json()["message"] == "Repo some-user/another-repo does not exist"

    def test_close_pull_request(self, fake_github, is_merged):
        repo = fake_github.make_repo("an-org", "a-repo")
        with freeze_time("2021-08-31 15:30:12"):
            pr = repo.make_pull_request(
                user="some-user",
                title="Here is a pull request",
                body="It's a good pull request, you should merge it.",
            )
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/pulls/{pr.number}")
        assert resp.status_code == 200
        prj = resp.json()
        assert prj["created_at"] == "2021-08-31T15:30:12Z"
        assert prj["closed_at"] is None

        with freeze_time("2021-09-01 01:02:03"):
            pr.close(merge=is_merged)
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/pulls/{pr.number}")
        prj = resp.json()
        assert prj["created_at"] == "2021-08-31T15:30:12Z"
        assert prj["closed_at"] == "2021-09-01T01:02:03Z"
        assert prj["merged"] == is_merged


@pytest.fixture
def pull_requests_to_list(fake_github):
    repo = fake_github.make_repo("an-org", "a-repo")
    repo.make_pull_request(user="user1", title="Title 1", body="Boo")
    repo.make_pull_request(user="user2", title="Title 2", body="Boo", state="closed")
    repo.make_pull_request(user="user1", title="Title 3", body="Boo hoo")
    repo.make_pull_request(user="user2", title="Title 4", body="Boo hoo", draft=True)
    repo.make_pull_request(user="user3", title="Title 5", body="Boo hoo", state="closed")


class TestPullRequestList:
    def test_list_pull_requests(self, pull_requests_to_list):
        resp = requests.get("https://api.github.com/repos/an-org/a-repo/pulls")
        prjs = resp.json()
        # By default, only open pull requests are listed.
        assert len(prjs) == 3
        # When listing pull requests, not all fields are returned.
        assert not any(k in prj for prj in prjs for k in ["merged"])

    @pytest.mark.parametrize("state, number, specific", [
        ("open", 3, True),
        ("closed", 2, True),
        ("all", 5, False),
    ])
    def test_list_pull_requests_count(self, pull_requests_to_list, state, number, specific):
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/pulls?state={state}")
        prjs = resp.json()
        assert len(prjs) == number
        if specific:
            assert all(prj["state"] == state for prj in prjs)


class TestPullRequestLabels:
    def test_updating_labels_with_api(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request(
            title="Here is a pull request",
            body="It's a good pull request, you should merge it.",
        )
        assert pr.labels == set()

        resp = requests.patch(
            f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}",
            json={"labels": ["new label", "bug", "another label"]},
        )
        assert resp.status_code == 200
        assert pr.labels == {"new label", "bug", "another label"}
        assert repo.get_label("new label").color == "ededed"
        assert repo.get_label("bug").color == "d73a4a"
        assert repo.get_label("another label").color == "ededed"

        resp = requests.get(
            f"https://api.github.com/repos/an-org/a-repo/pulls/{pr.number}"
        )
        assert resp.status_code == 200
        prj = resp.json()
        assert prj["title"] == "Here is a pull request"
        label_summary = [(lbl["name"], lbl["color"]) for lbl in prj["labels"]]
        assert label_summary == [
            ("another label", "ededed"),
            ("bug", "d73a4a"),
            ("new label", "ededed"),
        ]

    def test_updating_labels_elsewhere(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request(
            title="Here is a pull request",
            body="It's a good pull request, you should merge it.",
        )
        assert pr.labels == set()

        pr.set_labels(["new label", "bug", "another label"])

        assert pr.labels == {"new label", "bug", "another label"}
        assert repo.get_label("new label").color == "ededed"
        assert repo.get_label("bug").color == "d73a4a"
        assert repo.get_label("another label").color == "ededed"

        resp = requests.get(
            f"https://api.github.com/repos/an-org/a-repo/pulls/{pr.number}"
        )
        assert resp.status_code == 200
        prj = resp.json()
        assert prj["title"] == "Here is a pull request"
        label_summary = [(lbl["name"], lbl["color"]) for lbl in prj["labels"]]
        assert label_summary == [
            ("another label", "ededed"),
            ("bug", "d73a4a"),
            ("new label", "ededed"),
        ]


class TestComments:
    def test_listing_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()
        assert pr.comments == []
        resp = requests.get(
            f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments"
        )
        assert resp.status_code == 200
        assert resp.json() == []

        pr.add_comment(user="tusbar", body="This is my comment")
        pr.add_comment(user="feanil", body="I love this change!")
        resp = requests.get(
            f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments"
        )
        assert resp.status_code == 200
        summary = glom(resp.json(), [{"u": "user.login", "b": "body"}])
        assert summary == [
            {"u": "tusbar", "b": "This is my comment"},
            {"u": "feanil", "b": "I love this change!"},
        ]

    def test_posting_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()

        resp = requests.post(
            f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments",
            json={"body": "I'm making a comment"},
        )
        assert resp.status_code == 200

        the_comment = pr.list_comments()[0]
        assert the_comment.user.login == "webhook-bot"
        assert the_comment.body == "I'm making a comment"

    def test_editing_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()

        pr.add_comment(user="tusbar", body="This is my comment")
        pr.add_comment(user="feanil", body="I love this change!")

        # List the comments, and get the id of the first one.
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments")
        comment_id = resp.json()[0]["id"]

        # Update the first comment.
        resp = requests.patch(
            f"https://api.github.com/repos/an-org/a-repo/issues/comments/{comment_id}",
            json={"body": "I've changed my mind about my comment."},
        )
        assert resp.status_code == 200

        # List the comments, and see the body of the first comment has changed.
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments")
        assert resp.json()[0]["body"] == "I've changed my mind about my comment."

    def test_posting_bad_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()

        with pytest.raises(ValueError, match="Markdown has a link to None"):
            requests.post(
                f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments",
                json={"body": "Look: [None](https://foo.com)"},
            )

    def test_editing_bad_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()

        pr.add_comment(user="tusbar", body="This is my comment")
        pr.add_comment(user="feanil", body="I love this change!")

        # List the comments, and get the id of the first one.
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments")
        comment_id = resp.json()[0]["id"]

        # Update the first comment.
        with pytest.raises(ValueError, match="Markdown has a link to None"):
            requests.patch(
                f"https://api.github.com/repos/an-org/a-repo/issues/comments/{comment_id}",
                json={"body": "Look: [None](https://foo.com)"},
            )

    def test_deleting_comments(self, fake_github):
        repo = fake_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()

        pr.add_comment(user="tusbar", body="This is my comment")
        pr.add_comment(user="feanil", body="I love this change!")

        # List the comments, and get the id of the first one.
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments")
        comment_id = resp.json()[0]["id"]

        # Update the first comment.
        resp = requests.delete(
            f"https://api.github.com/repos/an-org/a-repo/issues/comments/{comment_id}",
        )
        assert resp.status_code == 204

        # List the comments, and see only the second comment.
        resp = requests.get(f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments")
        comments = resp.json()
        assert len(comments) == 1
        assert comments[0]["body"] == "I love this change!"


@pytest.fixture
def flaky_github(requests_mocker, fake_repo_data):
    the_fake_github = FakeGitHub(login="webhook-bot", fraction_404=1)
    the_fake_github.install_mocks(requests_mocker)
    return the_fake_github

class TestFlakyGitHub:
    def test_get(self, flaky_github):
        # The first time we request something, it's 404, and then it's OK after that.
        resp = requests.get("https://api.github.com/user")
        assert resp.status_code == 404
        resp = requests.get("https://api.github.com/user")
        assert resp.status_code == 200
        resp = requests.get("https://api.github.com/user")
        assert resp.status_code == 200

    def test_post(self, flaky_github):
        repo = flaky_github.make_repo("an-org", "a-repo")
        pr = repo.make_pull_request()
        resp = requests.post(
            f"https://api.github.com/repos/an-org/a-repo/issues/{pr.number}/comments",
            json={"body": "I'm making a comment"},
        )
        # POSTs aren't affected by the flaky fraction.
        assert resp.status_code == 200
