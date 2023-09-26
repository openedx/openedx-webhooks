"""Tests of tasks/github.py:rescan_repository and rescan_organization"""

import json
from datetime import datetime

import pytest

from openedx_webhooks.bot_comments import github_community_pr_comment
from openedx_webhooks.info import get_bot_username
from openedx_webhooks.tasks.github import (
    pull_request_changed,
    rescan_organization,
    rescan_repository,
)
from openedx_webhooks.types import PrId


@pytest.fixture
def pull_request_changed_fn(mocker):
    """A mock for pull_request_changed that wraps the real function."""
    return mocker.patch(
        "openedx_webhooks.tasks.github.pull_request_changed",
        wraps=pull_request_changed,
    )


@pytest.fixture
def rescannable_repo(fake_github):
    """Get the rescannable repo."""
    return make_rescannable_repo(fake_github, org_name="an-org", repo_name="a-repo")


def make_rescannable_repo(fake_github, org_name="an-org", repo_name="a-repo"):
    """
    Make a fake repo full of pull requests to rescan.
    """
    repo = fake_github.make_repo(org_name, repo_name)
    # Numbers of internal pull requsts are odd, external are even.
    repo.make_pull_request(user="nedbat", number=101, created_at=datetime(2019, 1, 1))
    repo.make_pull_request(user="tusbar", number=102, created_at=datetime(2019, 2, 1))
    repo.make_pull_request(user="nedbat", number=103, state="closed", created_at=datetime(2019, 3, 1),
        closed_at=datetime(2020,7,1))
    repo.make_pull_request(user="feanil", number=105, created_at=datetime(2019, 4, 1))
    repo.make_pull_request(user="tusbar", number=106, created_at=datetime(2019, 5, 1))
    repo.make_pull_request(user="tusbar", number=108, state="closed", created_at=datetime(2019, 6, 1),
        closed_at=datetime(2020,7,1))
    # One of the PRs already has a bot comment with a Jira issue.
    pr = repo.make_pull_request(user="tusbar", number=110, state="closed", merged=True, created_at=datetime(2019, 7, 1),
        closed_at=datetime(2020,7,1))
    pr.add_comment(user=get_bot_username(), body=github_community_pr_comment(pr.as_json()))

    # Issues before 2018 should not be rescanned.
    repo.make_pull_request(user="tusbar", number=98, created_at=datetime(2017, 12, 15))
    repo.make_pull_request(user="nedbat", number=97, created_at=datetime(2012, 10, 1))

    return repo


@pytest.mark.parametrize("allpr", [
    pytest.param(False, id="allpr:no"),
    pytest.param(True, id="allpr:yes"),
])
def test_rescan_repository(rescannable_repo, pull_request_changed_fn, allpr):
    ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    changed = ret["changed"]
    errors = ret["errors"]
    for err in errors.values():
        print(err)
    assert not errors

    # Look at the pull request numbers passed to pull_request_changed. Only the
    # external (even) numbers should be there.
    prnums = [c.args[0]["number"] for c in pull_request_changed_fn.call_args_list]
    if allpr:
        assert prnums == [102, 106, 108, 110]
        assert changed == {102: None, 106: None, 108: None, 110: None}
    else:
        assert prnums == [102, 106]
        assert set(changed.keys()) == {102, 106}

    # If we rescan again, nothing should happen.
    ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    assert not ret["changed"]


def test_rescan_repository_dry_run(rescannable_repo, fake_github, fake_jira, pull_request_changed_fn):
    # Rescan as a dry run.
    ret = rescan_repository(rescannable_repo.full_name, allpr=True, dry_run=True)

    # We shouldn't have made any writes to GitHub or Jira.
    fake_github.assert_readonly()
    fake_jira.assert_readonly()

    # These are the OSPR tickets for the pull requests.
    assert ret["changed"] == {
        102: None,
        106: None,
        108: None,
        110: None,
    }

    # Get the names of the actions. We won't worry about the details, those
    # are tested in the non-dry-run tests of rescanning pull requests.
    actions = {k: [name for name, kwargs in actions] for k, actions in ret["dry_run_actions"].items()}
    assert actions == {
        102: [
            "set_cla_status",
            "initial_state",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "add_pull_request_to_project",
        ],
        106: [
            "set_cla_status",
            "initial_state",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "add_pull_request_to_project",
        ],
        108: [
            "set_cla_status",
            "initial_state",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "add_pull_request_to_project",
        ],
        110: [
            "set_cla_status",
            "initial_state",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "add_pull_request_to_project",
        ],
    }

    # The value returned should be json-encodable.
    json.dumps(ret)


@pytest.mark.parametrize("earliest, latest, nums", [
    ("", "", [102, 106, 108, 110]),
    ("2019-06-01", "", [108, 110]),
    ("2019-06-01", "2019-06-30", [108]),
])
def test_rescan_repository_date_limits(rescannable_repo, pull_request_changed_fn, earliest, latest, nums):
    rescan_repository(rescannable_repo.full_name, allpr=True, earliest=earliest, latest=latest)

    # Look at the pull request numbers passed to pull_request_changed. Only the
    # external (even) numbers should be there.
    prnums = [c.args[0]["number"] for c in pull_request_changed_fn.call_args_list]
    assert prnums == nums


@pytest.fixture
def rescannable_org(fake_github):
    """
    Make two orgs with two repos each full of pull requests.
    """
    for org_name in ["org1", "org2"]:
        for repo_name in ["rep1", "rep2"]:
            make_rescannable_repo(fake_github, org_name, repo_name)


@pytest.mark.parametrize("allpr, earliest, latest, nums", [
    (False, "", "", [102, 106]),
    (True, "", "", [102, 106, 108, 110]),
    (True, "2019-06-01", "", [108, 110]),
    (True, "2019-06-01", "2019-06-30", [108]),
])
def test_rescan_organization(rescannable_org, pull_request_changed_fn, allpr, earliest, latest, nums):
    rescan_organization("org1", allpr=allpr, earliest=earliest, latest=latest)
    prs = [PrId.from_pr_dict(c.args[0]) for c in pull_request_changed_fn.call_args_list]
    assert all(prid.org == "org1" for prid in prs)
    assert prs == [PrId(f"org1/{r}", num) for r in ["rep1", "rep2"] for num in nums]


def test_rescan_failure(mocker, rescannable_repo):
    def flaky_pull_request_changed(pr, actions):
        if pr["number"] == 108:
            return 1/0 # BOOM
        else:
            return pull_request_changed(pr, actions)

    mocker.patch("openedx_webhooks.tasks.github.pull_request_changed", flaky_pull_request_changed)
    ret = rescan_repository(rescannable_repo.full_name, allpr=True)

    assert list(ret["changed"]) == [102, 106, 108, 110]
    err = ret["errors"][108]
    assert err.startswith("Traceback (most recent call last):\n")
    assert " in flaky_pull_request_changed\n" in err
    assert "1/0 # BOOM" in err
    assert "ZeroDivisionError: division by zero" in err
