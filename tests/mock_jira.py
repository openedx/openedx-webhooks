"""A mock implementation of the Jira API."""

import random

class MockJira:
    """A mock implementation of the Jira API."""
    CONTRIBUTOR_NAME = "custom_101"
    CUSTOMER = "custom_102"
    PR_NUMBER = "custom_103"
    REPO = "custom_104"
    URL = "customfield_10904"   # This one is hard-coded

    def __init__(self, requests_mocker):
        requests_mocker.get(
            "https://openedx.atlassian.net/rest/api/2/field",
            json=[
                {"id": self.CONTRIBUTOR_NAME, "name": "Contributor Name", "custom": True},
                {"id": self.CUSTOMER, "name": "Customer", "custom": True},
                {"id": self.PR_NUMBER, "name": "PR Number", "custom": True},
                {"id": self.REPO, "name": "Repo", "custom": True},
                {"id": self.URL, "name": "URL", "custom": True},
            ]
        )
        self.new_issue_post = requests_mocker.post(
            "https://openedx.atlassian.net/rest/api/2/issue",
            json=self._new_issue_callback,
        )
        self.created_issues = []

    def make_issue(self, key):
        """Make fake issue data."""
        return {
            "key": key,
        }

    def _new_issue_callback(self, request, _):
        """Responds to the API endpoint for creating new issues."""
        project = request.json()["fields"]["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        self.created_issues.append(key)
        return {"key": key}
