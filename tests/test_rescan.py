"""Tests of tasks/github.py:rescan_repository and rescan_organization"""

import json
from datetime import datetime

import pytest

from openedx_webhooks.info import get_bot_username
from openedx_webhooks.lib.github.models import PrId
from openedx_webhooks.tasks.github import (
    pull_request_changed,
    rescan_organization,
    rescan_repository,
)


@pytest.fixture
def pull_request_changed_fn(mocker):
    """A mock for pull_request_changed that wraps the real function."""
    return mocker.patch(
        "openedx_webhooks.tasks.github.pull_request_changed",
        wraps=pull_request_changed,
    )


@pytest.fixture
def rescannable_repo(fake_github, fake_jira):
    """Get the rescannable repo."""
    return make_rescannable_repo(fake_github, fake_jira, org_name="an-org", repo_name="a-repo")


def make_rescannable_repo(fake_github, fake_jira, org_name="an-org", repo_name="a-repo"):
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
    pr.add_comment(user=get_bot_username(), body="A ticket: OSPR-1234!\n<!-- comment:external_pr -->")
    fake_jira.make_issue(key="OSPR-1234", summary="An issue")

    # Issues before 2018 should not be rescanned.
    repo.make_pull_request(user="tusbar", number=98, created_at=datetime(2017, 12, 15))
    repo.make_pull_request(user="nedbat", number=97, created_at=datetime(2012, 10, 1))

    return repo


@pytest.mark.parametrize("allpr", [False, True])
def test_rescan_repository(rescannable_repo, reqctx, pull_request_changed_fn, allpr):
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    changed = ret["changed"]

    # Look at the pull request numbers passed to pull_request_changed. Only the
    # external (even) numbers should be there.
    prnums = [c.args[0]["number"] for c in pull_request_changed_fn.call_args_list]
    if allpr:
        assert prnums == [102, 106, 108, 110]
        assert set(changed.keys()) == {102, 106, 108, 110}
        assert changed[110] == "OSPR-1234"
    else:
        assert prnums == [102, 106]
        assert set(changed.keys()) == {102, 106}

    # If we rescan again, nothing should happen.
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=allpr)
    assert "changed" not in ret


def test_rescan_repository_dry_run(rescannable_repo, reqctx, fake_github, fake_jira, pull_request_changed_fn):
    # Rescan as a dry run.
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=True, dry_run=True)

    # We shouldn't have made any writes to GitHub or Jira.
    fake_github.assert_readonly()
    fake_jira.assert_readonly()

    # These are the OSPR tickets for the pull requests.
    assert ret["changed"] == {
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
            "initial_state",
            "synchronize_labels",
            "create_ospr_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "set_cla_status",
        ],
        106: [
            "initial_state",
            "synchronize_labels",
            "create_ospr_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "set_cla_status",
        ],
        108: [
            "initial_state",
            "synchronize_labels",
            "create_ospr_issue",
            "transition_jira_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "set_cla_status",
        ],
        110: [
            "initial_state",
            "synchronize_labels",
            "transition_jira_issue",
            "update_jira_issue",
            "update_labels_on_pull_request",
            "add_comment_to_pull_request",
            "set_cla_status",
        ],
    }

    # The value returned should be json-encodable.
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


def test_rescan_blended(reqctx, fake_github, fake_jira):
    # At one point, we weren't treating epic links right when rescanning, and
    # kept updating the jira issue.
    pr = fake_github.make_pull_request(user="tusbar", title="[BD-34] Something good")
    prj = pr.as_json()
    map_1_2 = {
        "child": {
            "id": "14522",
            "self": "https://openedx.atlassian.net/rest/api/2/customFieldOption/14522",
            "value": "Course Level Insights"
        },
        "id": "14209",
        "self": "https://openedx.atlassian.net/rest/api/2/customFieldOption/14209",
        "value": "Researcher & Data Experiences"
    }
    epic = fake_jira.make_issue(
        project="BLENDED",
        blended_project_id="BD-34",
        blended_project_status_page="https://thewiki/bd-34",
        platform_map_1_2=map_1_2,
    )

    with reqctx:
        issue_id, anything_happened = pull_request_changed(prj)

    assert issue_id is not None
    assert issue_id.startswith("BLENDED-")
    assert anything_happened is True

    # Check the Jira issue that was created.
    assert len(fake_jira.issues) == 2
    issue = fake_jira.issues[issue_id]
    assert issue.epic_link == epic.key
    assert issue.platform_map_1_2 == map_1_2

    # Reset our fakers so we can isolate the effect of the rescan.
    fake_github.reset_mock()
    fake_jira.reset_mock()

    # Rescan.
    with reqctx:
        ret = rescan_repository(pr.repo.full_name, allpr=True)

    assert "changed" not in ret

    # We shouldn't have made any writes to GitHub or Jira.
    fake_github.assert_readonly()
    fake_jira.assert_readonly()


@pytest.fixture
def rescannable_org(fake_github, fake_jira):
    """
    Make two orgs with two repos each full of pull requests.
    """
    for org_name in ["org1", "org2"]:
        for repo_name in ["rep1", "rep2"]:
            make_rescannable_repo(fake_github, fake_jira, org_name, repo_name)


@pytest.mark.parametrize("allpr, earliest, latest, nums", [
    (False, "", "", [102, 106]),
    (True, "", "", [102, 106, 108, 110]),
    (True, "2019-06-01", "", [108, 110]),
    (True, "2019-06-01", "2019-06-30", [108]),
])
def test_rescan_organization(rescannable_org, reqctx, pull_request_changed_fn, allpr, earliest, latest, nums):
    with reqctx:
        rescan_organization("org1", allpr=allpr, earliest=earliest, latest=latest)
    prs = [PrId.from_pr_dict(c.args[0]) for c in pull_request_changed_fn.call_args_list]
    assert all(prid.org == "org1" for prid in prs)
    assert prs == [PrId(f"org1/{r}", num) for r in ["rep1", "rep2"] for num in nums]


def test_rescan_failure(mocker, rescannable_repo, reqctx):
    def flaky_pull_request_changed(pr, actions):
        if pr["number"] == 108:
            return 1/0 # BOOM
        else:
            return pull_request_changed(pr, actions)

    mocker.patch("openedx_webhooks.tasks.github.pull_request_changed", flaky_pull_request_changed)
    with reqctx:
        ret = rescan_repository(rescannable_repo.full_name, allpr=True)

    assert list(ret["changed"]) == [102, 106, 108, 110]
    err = ret["changed"][108]
    assert err.startswith("Traceback (most recent call last):\n")
    assert " in flaky_pull_request_changed\n" in err
    assert "1/0 # BOOM" in err
    assert "ZeroDivisionError: division by zero" in err
