"""Tests of tasks/github.py:rescan_repository """

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


@pytest.mark.parametrize("allpr", [False, True])
def test_rescan_repository(reqctx, fake_github, fake_jira, pull_request_changed_fn, allpr):
    repo = fake_github.make_repo("an-org", "a-repo")
    # Numbers of internal pull requsts are odd, external are even.
    repo.make_pull_request(user="nedbat", number=101)
    repo.make_pull_request(user="tusbar", number=102)
    repo.make_pull_request(user="nedbat", number=103, state="closed")
    repo.make_pull_request(user="feanil", number=105)
    repo.make_pull_request(user="tusbar", number=106)
    repo.make_pull_request(user="tusbar", number=108, state="closed")
    # One of the PRs already has a bot comment with a Jira issue.
    pr = repo.make_pull_request(user="tusbar", number=110, state="closed", merged=True)
    pr.add_comment(user=get_bot_username(), body=f"A ticket: OSPR-1234!\n<!-- comment:external_pr -->")
    fake_jira.make_issue(key="OSPR-1234", summary="An issue")

    with reqctx:
        ret = rescan_repository(repo.full_name, allpr=allpr)
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
        ret = rescan_repository(repo.full_name, allpr=allpr)
    assert "created" not in ret
