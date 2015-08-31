import pytest
from datetime import datetime
import openedx_webhooks
from openedx_webhooks.views.github import (
    github_community_pr_comment, github_contractor_pr_comment
)

#pytest.mark.usefixtures('betamax_session')

def make_pull_request(user, number=1, base_repo_name="edx/edx-platform", head_repo_name="edx/edx-platform", created_at=None):
    "this should really use a framework like factory_boy"
    created_at = created_at or datetime.now().replace(microsecond=0)
    return {
        "user": {
            "login": user,
        },
        "number": number,
        "created_at": created_at.isoformat(),
        "head": {
            "repo": {
                "full_name": head_repo_name,
            }
        },
        "base": {
            "repo": {
                "full_name": base_repo_name,
            }
        }
    }

def make_jira_issue(key="ABC-123"):
    return {
        "key": key,
    }


def test_community_pr_comment():
    pr = make_pull_request(user="FakeUser")
    jira = make_jira_issue(key="FOO-1")
    with openedx_webhooks.app.test_request_context('/'):
        comment = github_community_pr_comment(pr, jira)
    assert "[FOO-1](https://openedx.atlassian.net/browse/FOO-1)" in comment
    assert "can't start reviewing your pull request" in comment

def test_contractor_pr_comment():
    pr = make_pull_request(user="FakeUser")
    with openedx_webhooks.app.test_request_context('/', environ_overrides={"wsgi.url_scheme": "https"}):
        comment = github_contractor_pr_comment(pr)
    assert "company that does contract work for edX" in comment
    assert "visit this link:\nhttps://" in comment

