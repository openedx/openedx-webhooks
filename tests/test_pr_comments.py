"""Tests of the comment creation functions in bot_comments.py."""

import re

from freezegun import freeze_time

from openedx_webhooks.bot_comments import (
    BotComment,
    is_comment_kind,
    github_community_pr_comment,
    github_end_survey_comment,
    extract_data_from_comment,
    format_data_for_comment,
)

from .helpers import check_good_markdown


def test_community_pr_comment(fake_github):
    # A pull request from a member in good standing.
    pr = fake_github.make_pull_request(user="tusbar")
    comment = github_community_pr_comment(pr.as_json())
    assert not is_comment_kind(BotComment.NEED_CLA, comment)
    check_good_markdown(comment)


def test_community_pr_comment_no_cla(fake_github):
    pr = fake_github.make_pull_request(user="FakeUser")
    comment = github_community_pr_comment(pr.as_json())
    assert is_comment_kind(BotComment.NEED_CLA, comment)
    assert "[signed contributor agreement](https://openedx.org/cla)" in comment
    check_good_markdown(comment)


def test_survey_pr_comment(fake_github, is_merged):
    with freeze_time("2021-08-31 15:30:12"):
        pr = fake_github.make_pull_request(user="FakeUser")
    with freeze_time("2021-09-01 01:02:03"):
        pr.close(merge=is_merged)
    prj = pr.as_json()
    comment = github_end_survey_comment(prj)
    assert "@FakeUser" in comment
    assert "/1FAIpQLSceJOyGJ6JOzfy6lyR3T7EW_71OWUnNQXp68Fymsk3MkNoSDg/viewform" in comment
    assert "&entry.1671973413=an-org/a-repo" in comment
    assert "&entry.752974735=2021-08-31+15:30" in comment
    assert "&entry.1917517419=2021-09-01+01:02" in comment
    if is_merged:
        assert "Your pull request was merged!" in comment
        assert "&entry.2133058324=Yes" in comment
    else:
        assert "Even though your pull request wasn’t merged" in comment
        assert "&entry.2133058324=No" in comment
    check_good_markdown(comment)


COMMENT_DATA = {
    "hello": 1,
    "what": "-- that's what --\nbye.",
    "non-ascii": "ИФИ-ДSCII ΓΞЖΓ",
    "lists": [1, 2, 3, [4, 5, 6]],
}

def test_data_in_comments():
    comment = "blah blah" + format_data_for_comment(COMMENT_DATA)
    check_good_markdown(comment)
    data = extract_data_from_comment(comment)
    assert data == COMMENT_DATA


def test_no_data_in_comments():
    comment = "I have no data at all."
    assert extract_data_from_comment(comment) == {}


def test_corrupted_data_in_comments():
    # If the data island is tampered with, don't let that break the bot.
    comment = "blah blah" + format_data_for_comment(COMMENT_DATA)
    comment = re.sub(r"\d", "xyz", comment)
    data = extract_data_from_comment(comment)
    assert data == {}
