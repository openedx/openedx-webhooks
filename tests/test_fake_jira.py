"""Tests of FakeJira."""

import requests


class TestIssues:
    def test_get_issue(self, fake_jira):
        fake_jira.make_issue(key="HELLO-123", summary="This is a bad bug!")
        resp = requests.get("https://openedx.atlassian.net/rest/api/2/issue/HELLO-123")
        assert resp.status_code == 200
        issue = resp.json()
        assert "HELLO-123" == issue["key"]
        assert "This is a bad bug!" == issue["fields"]["summary"]

    def test_update_summary(self, fake_jira):
        issue = fake_jira.make_issue(
            project="HELLO",
            summary="This is a bad bug!",
            description="Here are the details so you can see how serious it is.",
        )
        resp = requests.put(
            f"https://openedx.atlassian.net/rest/api/2/issue/{issue.key}",
            json={"fields": {"summary": "This is OK."}},
        )
        assert 204 == resp.status_code
        resp = requests.get(f"https://openedx.atlassian.net/rest/api/2/issue/{issue.key}")
        assert resp.status_code == 200
        issue2 = resp.json()
        # The title is changed.
        assert "This is OK." == issue2["fields"]["summary"]
        # The body is unchanged.
        assert "Here are the details so you can see how serious it is." == issue2["fields"]["description"]
