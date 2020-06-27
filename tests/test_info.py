"""
Tests of the functions in info.py
"""
from datetime import datetime

import pytest

from openedx_webhooks.info import (
    get_orgs, get_people_file, get_person_certain_time,
    is_committer_pull_request, is_internal_pull_request,
)


pytestmark = pytest.mark.usefixtures("fake_repo_data", "mock_github_bp")


def make_pull_request(user, created_at=None, repo="edx/edx-platform"):
    # This should really use a framework like factory_boy.
    created_at = created_at or datetime.now().replace(microsecond=0)
    return {
        "user": {
            "login": user,
        },
        "created_at": created_at.isoformat(),
        "base": {
            "repo": {
                "full_name": repo,
            },
        },
    }


def test_internal_orgs():
    orgs = get_orgs("internal")
    assert isinstance(orgs, set)
    assert "edX" in orgs

def test_contractor_orgs():
    orgs = get_orgs("contractor")
    assert isinstance(orgs, set)
    assert "edX" not in orgs

def test_edx_employee():
    pr = make_pull_request("nedbat")
    assert is_internal_pull_request(pr)

def test_ex_edx_employee():
    pr = make_pull_request("mmprandom")
    assert not is_internal_pull_request(pr)

def test_ex_edx_employee_old_pr():
    created_at = datetime(2014, 1, 1)
    pr = make_pull_request("jarv", created_at=created_at)
    assert is_internal_pull_request(pr)

def test_never_heard_of_you():
    pr = make_pull_request("some_random_guy")
    assert not is_internal_pull_request(pr)

def test_hourly_worker():
    pr = make_pull_request("theJohnnyBrown")
    assert not is_internal_pull_request(pr)

def test_left_but_still_a_fan():
    pr = make_pull_request("jarv")
    assert not is_internal_pull_request(pr)

def test_org_committers():
    pr = make_pull_request("felipemontoya", repo="edx/something")
    assert not is_internal_pull_request(pr)
    assert is_committer_pull_request(pr)
    pr = make_pull_request("felipemontoya", repo="openedx/something")
    assert not is_internal_pull_request(pr)
    assert not is_committer_pull_request(pr)

def test_repo_committers():
    pr = make_pull_request("pdpinch", repo="edx/ccx-keys")
    assert not is_internal_pull_request(pr)
    assert is_committer_pull_request(pr)
    pr = make_pull_request("pdpinch", repo="edx/edx-platform")
    assert not is_internal_pull_request(pr)
    assert not is_committer_pull_request(pr)

def test_current_person_no_institution():
    people = get_people_file()
    created_at = datetime.today()
    current_person = get_person_certain_time(people["jarv"], created_at)
    assert "institution" not in current_person
    assert current_person["agreement"] == "individual"

def test_current_person():
    people = get_people_file()
    created_at = datetime.today()
    current_person = get_person_certain_time(people["raisingarizona"], created_at)
    assert current_person["agreement"] == "none"

def test_updated_person_has_institution():
    people = get_people_file()
    created_at = datetime(2014, 1, 1)
    updated_person = get_person_certain_time(people["jarv"], created_at)
    assert updated_person["institution"] == "edX"

def test_updated_person():
    people = get_people_file()
    created_at = datetime(2014, 1, 1)
    updated_person = get_person_certain_time(people["raisingarizona"], created_at)
    assert updated_person["agreement"] == "individual"

def test_old_committer():
    pr = make_pull_request("raisingarizona")
    assert not is_committer_pull_request(pr)
    pr = make_pull_request("raisingarizona", created_at=datetime(2014, 12, 31))
    assert is_committer_pull_request(pr)
    pr = make_pull_request("raisingarizona", created_at=datetime(2015, 12, 31))
    assert not is_committer_pull_request(pr)
