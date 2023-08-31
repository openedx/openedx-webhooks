"""Tests for gh_projects.py"""

from openedx_webhooks.gh_projects import (
    add_pull_request_to_project,
    pull_request_projects,
)
from openedx_webhooks.types import PrId


def test_adding_pr_to_project(fake_github):
    pr = fake_github.make_pull_request(user="FakeUser")
    prj = pr.as_json()
    prid = PrId.from_pr_dict(prj)
    projects = set(pull_request_projects(prj))
    assert projects == set()
    assert not pr.is_in_project(("myorg", 23))

    add_pull_request_to_project(prid, pr.node_id, ("myorg", 23))
    projects = set(pull_request_projects(prj))
    assert projects == {("myorg", 23)}
    assert pr.is_in_project(("myorg", 23))
    assert not pr.is_in_project(("anotherorg", 27))

    add_pull_request_to_project(prid, pr.node_id, ("anotherorg", 27))
    projects = set(pull_request_projects(prj))
    assert projects == {("myorg", 23), ("anotherorg", 27)}
    assert pr.is_in_project(("myorg", 23))
    assert pr.is_in_project(("anotherorg", 27))
