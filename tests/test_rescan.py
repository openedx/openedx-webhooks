"""Tests of tasks/github.py:rescan_repository """

import json
from datetime import datetime

import pytest

from openedx_webhooks.info import get_bot_username
from openedx_webhooks.tasks.github import rescan_repository, pull_request_changed

@pytest.fixture
def pull_request_changed_fn(mocker):
    """A mock for pull_request_changed that wraps the real function."""
    return mocker.patch(
        "openedx_webhooks.tasks.github.pull_request_changed",
        wraps=pull_request_changed,
    )


@pytest.fixture
def rescannable_repo(fake_github, fake_jira):
    """
    Make a fake repo full of pull requests to rescan.
    """
    repo = fake_github.make_repo("an-org", "a-repo")
    # Numbers of internal pull requsts are odd, external are even.
    repo.make_pull_request(user="nedbat", number=101, created_at=datetime(2019, 1, 1))
    repo.make_pull_request(user="tusbar", number=102, created_at=datetime(2019, 2, 1))
    repo.make_pull_request(user="nedbat", number=103, state="closed", created_at=datetime(2019, 3, 1))
    repo.make_pull_request(user="feanil", number=105, created_at=datetime(2019, 4, 1))
    repo.make_pull_request(user="tusbar", number=106, created_at=datetime(2019, 5, 1))
    repo.make_pull_request(user="tusbar", number=108, state="closed", created_at=datetime(2019, 6, 1))
    # One of the PRs already has a bot comment with a Jira issue.
    pr = repo.make_pull_request(user="tusbar", number=110, state="closed", merged=True, created_at=datetime(2019, 7, 1))
    pr.add_comment(user=get_bot_username(), body=f"A ticket: OSPR-1234!\n<!-- comment:external_pr -->")
    fake_jira.make_issue(key="OSPR-1234", summary="An issue")

    # Issues before 2018 should not be rescanned.
    repo.make_pull_request(user="tusbar", number=98, created_at=datetime(2017, 12, 15))
    repo.make_pull_request(user="nedbat", number=97, created_at=datetime(2012, 10, 1))

    return repo

@pytest.mark.parametrize("allpr", [False, True])
def test_rescan_repository(rescannable_repo, reqctx, pull_request_changed_fn, allpr):
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    created = ret["created"]

    # Look at the pull request numbers passed to pull_request_changed. Only the
    # external (even) numbers should be there.
    prnums = [c.args[0]["number"] for c in pull_request_changed_fn.call_args_list]
    if allpr:
        assert prnums == [102, 106, 108, 110]
        assert set(created.keys()) == {102, 106, 108, 110}
        assert created[110] == "OSPR-1234"
    else:
        assert prnums == [102, 106]
        assert set(created.keys()) == {102, 106}

    # If we rescan again, nothing should happen.
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    assert "created" not in ret


def test_rescan_repository_dry_run(rescannable_repo, reqctx, fake_github, fake_jira, pull_request_changed_fn):
    # Rescan as a dry run.
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=True, dry_run=True)

    # We shouldn't have made any writes to GitHub or Jira.
    fake_github.assert_readonly()
    fake_jira.assert_readonly()

    # These are the OSPR tickets for the pull requests.
    assert ret["created"] == {
        102: "OSPR-9000",
        106: "OSPR-9001",
        108: "OSPR-9002",
        110: "OSPR-1234",
    }

    # Get the names of the actions. We won't worry about the details, those
    # are tested in the non-dry-run tests of rescanning pull requests.
    actions = {k: [name for name, kwargs in actions] for k, actions in ret["dry_run_actions"].items()}
    assert actions == {
        102: [
            "synchronize_labels",
            "create_ospr_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
        ],
        106: [
            "synchronize_labels",
            "create_ospr_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
        ],
        108: [
            "synchronize_labels",
            "create_ospr_issue",
            "transition_jira_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
        ],
        110: [
            "synchronize_labels",
            "transition_jira_issue",
            "update_jira_issue",
            "update_labels_on_pull_request",
            "edit_comment_on_pull_request",
        ],
    }

    # The value returned should be json-encodable.
    import pprint; pprint.pprint(ret)
    json.dumps(ret)


@pytest.mark.parametrize("earliest, latest, nums", [
    ("", "", [102, 106, 108, 110]),
    ("2019-06-01", "", [108, 110]),
    ("2019-06-01", "2019-06-30", [108]),
])
def test_rescan_repository_date_limits(rescannable_repo, reqctx, pull_request_changed_fn, earliest, latest, nums):
    with reqctx:
        rescan_repository(rescannable_repo.full_name, allpr=True, earliest=earliest, latest=latest)

    # Look at the pull request numbers passed to pull_request_changed. Only the
    # external (even) numbers should be there.
    prnums = [c.args[0]["number"] for c in pull_request_changed_fn.call_args_list]
    assert prnums == nums
