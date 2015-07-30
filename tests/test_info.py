"""
Tests of the functions in info.py
"""
import pytest
from datetime import datetime

from openedx_webhooks.info import get_orgs, is_internal_pull_request
import openedx_webhooks.info

pytest.mark.usefixtures('betamax_session')


class TestGetOrg(object):

    def test_committer_orgs(self, betamax_session):
        orgs = get_orgs("committer", betamax_session)
        assert isinstance(orgs, set)
        assert "edX" in orgs

    def test_contractor_orgs(self, betamax_session):
        orgs = get_orgs("contractor", betamax_session)
        assert isinstance(orgs, set)
        assert "edX" not in orgs


def make_pull_request(user, created_at=None):
    "this should really use a framework like factory_boy"
    created_at = created_at or datetime.now().replace(microsecond=0)
    return {
        "user": {
            "login": user,
        },
        "created_at": created_at.isoformat(),
    }


class TestPullRequestCategories(object):

    def test_edx_employee(self, betamax_session):
        pr = make_pull_request("nedbat")
        assert is_internal_pull_request(pr, session=betamax_session)

    def test_ex_edx_employee(self, betamax_session):
        pr = make_pull_request("mmprandom")
        assert not is_internal_pull_request(pr, session=betamax_session)

    def test_ex_edx_employee_old_pr(self, betamax_session):
        created_at = datetime(2014, 1, 1)
        pr = make_pull_request("mmprandom", created_at=created_at)
        assert is_internal_pull_request(pr, session=betamax_session)

    def test_never_heard_of_you(self, betamax_session):
        pr = make_pull_request("some_random_guy")
        assert not is_internal_pull_request(pr, session=betamax_session)

    def test_hourly_worker(self, betamax_session):
        pr = make_pull_request("theJohnnyBrown")
        assert not is_internal_pull_request(pr, session=betamax_session)

    def test_left_but_still_a_fan(self, betamax_session):
        pr = make_pull_request("jarv")
        assert not is_internal_pull_request(pr, session=betamax_session)
        # Note: openedx_webhooks doesn't understand the "before" keys.

    def test_committers(self, betamax_session):
        pr = make_pull_request("antoviaque")
        assert is_internal_pull_request(pr, session=betamax_session)
