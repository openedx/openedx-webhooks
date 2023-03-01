"""
Tests of the functions in info.py
"""
from datetime import datetime

import pytest

from openedx_webhooks.info import (
    get_people_file, get_person_certain_time,
    is_committer_pull_request, is_internal_pull_request, is_draft_pull_request,
    pull_request_has_cla,
    get_blended_project_id,
)


# These tests should run when we want to test flaky GitHub behavior.
pytestmark = [
    pytest.mark.flaky_github,
    pytest.mark.usefixtures("fake_repo_data"),
]


@pytest.fixture
def make_pull_request(fake_github):
    """
    Provide a function for making a JSON pull request object.
    """
    def _fn(user, repo="openedx/edx-platform", **kwargs):
        fake_github.make_user(user)
        owner, repo = repo.split("/")
        pr = fake_github.make_pull_request(user=user, owner=owner, repo=repo, **kwargs)
        return pr.as_json()
    return _fn


def test_edx_employee(make_pull_request):
    pr = make_pull_request("nedbat")
    assert is_internal_pull_request(pr)
    pr = make_pull_request("nedbat", repo="edx/something")
    assert is_internal_pull_request(pr)

def test_tcril_employee(make_pull_request):
    pr = make_pull_request("feanil")
    assert is_internal_pull_request(pr)
    pr = make_pull_request("feanil", repo="edx/something")
    assert not is_internal_pull_request(pr)

def test_intguy(make_pull_request):
    pr = make_pull_request("intguy", repo="anywhere/anything")
    assert is_internal_pull_request(pr)
    pr = make_pull_request("intguy", repo="edx/something")
    assert is_internal_pull_request(pr)

def test_ex_edx_employee(make_pull_request):
    pr = make_pull_request("mmprandom")
    assert not is_internal_pull_request(pr)

def test_ex_edx_employee_old_pr(make_pull_request):
    created_at = datetime(2014, 1, 1)
    pr = make_pull_request("jarv", created_at=created_at)
    assert is_internal_pull_request(pr)

def test_never_heard_of_you(make_pull_request):
    pr = make_pull_request("some_random_guy")
    assert not is_internal_pull_request(pr)

def test_hourly_worker(make_pull_request):
    pr = make_pull_request("theJohnnyBrown")
    assert not is_internal_pull_request(pr)

def test_left_but_still_a_fan(make_pull_request):
    pr = make_pull_request("jarv")
    assert not is_internal_pull_request(pr)

def test_org_committers(make_pull_request):
    pr = make_pull_request("felipemontoya", repo="openedx/something")
    assert not is_internal_pull_request(pr)
    assert is_committer_pull_request(pr)
    pr = make_pull_request("felipemontoya", repo="edx/something")
    assert not is_internal_pull_request(pr)
    assert not is_committer_pull_request(pr)

def test_repo_committers(make_pull_request):
    pr = make_pull_request("pdpinch", repo="openedx/ccx-keys")
    assert not is_internal_pull_request(pr)
    assert is_committer_pull_request(pr)
    pr = make_pull_request("pdpinch", repo="openedx/edx-platform")
    assert not is_internal_pull_request(pr)
    assert not is_committer_pull_request(pr)

def test_base_branch_committers(make_pull_request):
    pr = make_pull_request(
        "hollyhunter",
        repo="openedx/fake-release-repo",
        ref="open-release/birch.1"
    )
    assert not is_internal_pull_request(pr)
    assert is_committer_pull_request(pr)
    pr = make_pull_request(
        "hollyhunter",
        repo="openedx/fake-release-repo",
        ref="master"
    )
    assert not is_internal_pull_request(pr)
    assert not is_committer_pull_request(pr)
    pr = make_pull_request(
        "pdpinch",
        repo="openedx/fake-release-repo",
        ref="open-release/birch.1"
    )
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
    # This only works if "before" clauses are layered together properly.
    people = get_people_file()
    created_at = datetime(2014, 1, 1)
    updated_person = get_person_certain_time(people["raisingarizona"], created_at)
    assert updated_person["agreement"] == "individual"

@pytest.mark.parametrize("who, when, cc", [
    ("raisingarizona", datetime(2020, 12, 31), False),
    ("raisingarizona", datetime(2015, 12, 31), False),
    ("raisingarizona", datetime(2014, 12, 31), True),
    ("raisingarizona", datetime(2013, 12, 31), False),
    ("hollyhunter", datetime(2020, 12, 31), True),
    ("hollyhunter", datetime(2019, 12, 31), False),
])
def test_old_committer(make_pull_request, who, when, cc):
    pr = make_pull_request(who, created_at=when)
    assert is_committer_pull_request(pr) == cc

@pytest.mark.parametrize("user, created_at_args, has_cla", [
    ("nedbat", (2020, 7, 2), True),
    ("raisingarizona", (2020, 7, 2), False),
    ("raisingarizona", (2017, 1, 1), True),
    ("raisingarizona", (2016, 1, 1), False),
    ("raisingarizona", (2015, 1, 1), True),
    ("never-heard-of-her", (2020, 7, 2), False),
])
def test_pull_request_has_cla(make_pull_request, user, created_at_args, has_cla):
    pr = make_pull_request(user, created_at=datetime(*created_at_args))
    assert pull_request_has_cla(pr) is has_cla


@pytest.mark.parametrize("title, number", [
    ("Please take my change", None),
    ("[BD-17] Fix typo", 17),
    ("This is for [  BD-007]", 7),
    ("This is for [  BD  -  0070     ]", 70),
    ("Blended BD-18 doesn't count", None),
    ("[BD-34] [BB-1234] extra tags are OK", 34),
    ("[BB-1234] [BD-34] extra tags are OK", 34),
])
def test_get_blended_project_id(fake_github, title, number):
    pr = fake_github.make_pull_request(title=title)
    num = get_blended_project_id(pr.as_json())
    assert number == num


TITLES_WIP = [
    ("My awesome pull request", False),
    ("WIP: not ready yet", True),
    ("[WIP] hare-brained idea", True),
    ("Still working it out (WIP)", True),
    ("(wip) working on it", True),
    ("Swipe left if you like it", False),
    ("This is wip, not ready yet", True),
]

@pytest.mark.parametrize("title, is_wip", TITLES_WIP)
def test_is_wip_pull_request(fake_github, title, is_wip):
    # A PR is draft if it has a WIP title.
    pr = fake_github.make_pull_request(title=title)
    assert is_draft_pull_request(pr.as_json()) == is_wip

@pytest.mark.parametrize("title", [p[0] for p in TITLES_WIP])
def test_is_draft_pull_request(fake_github, title):
    # No matter what the title, a pr is Draft if it says it is.
    pr = fake_github.make_pull_request(title=title, draft=True)
    assert is_draft_pull_request(pr.as_json())

def test_check_csv_users_only():
    people = get_people_file()
    user = 'Carlos-Muniz'
    # This user exists in the yaml but not in the csv, and should not be in people
    assert people.get(user) is None

def test_check_csv_org_priority():
    people = get_people_file()
    user = 'mmprandom'
    assert people[user]['agreement'] == 'individual'

def test_check_people_missing_yaml_fields():
    people = get_people_file()
    user = 'test-test'
    assert people[user].get('jira') is None
    assert people[user].get('commiter') is None
    assert people[user].get('comments') is None
    assert people[user].get('before') is None
