"""A mock implementation of the Jira API."""

import random
import re


class MockJira:
    """A mock implementation of the Jira API, specialized to the OSPR project."""

    HOST = "openedx.atlassian.net"

    # Custom fields for OSPR.
    CONTRIBUTOR_NAME = "custom_101"
    CUSTOMER = "custom_102"
    PR_NUMBER = "custom_103"
    REPO = "custom_104"
    URL = "customfield_10904"   # This one is hard-coded

    # Issue states and transitions for OSPR.
    INITIAL_STATE = "Needs Triage"

    # The OSPR project is configured that any state can transition to any other
    # state. Other projects could be much more complex.
    TRANSITIONS = {
        name: str(i + 901)
        for i, name in enumerate([
            "Needs Triage",
            "Waiting on Author",
            "Blocked by Other Work",
            "Rejected",
            "Merged",
            "Community Manager Review",
            "Open edX Community Review",
            "Awaiting Prioritization",
            "Product Review",
            "Engineering Review",
            "Architecture Review",
            "Changes Requested",
        ])
    }

    def __init__(self, requests_mocker):
        self.requests_mocker = requests_mocker

        # Custom fields particular to the OSPR project.
        self.requests_mocker.get(
            f"https://{self.HOST}/rest/api/2/field",
            json=[
                {"id": self.CONTRIBUTOR_NAME, "name": "Contributor Name", "custom": True},
                {"id": self.CUSTOMER, "name": "Customer", "custom": True},
                {"id": self.PR_NUMBER, "name": "PR Number", "custom": True},
                {"id": self.REPO, "name": "Repo", "custom": True},
                {"id": self.URL, "name": "URL", "custom": True},
            ]
        )

        # Make a new issue.
        self.new_issue_post = self.requests_mocker.post(
            f"https://{self.HOST}/rest/api/2/issue",
            json=self._new_issue_callback,
        )
        self.issues = {}

        # Get an issue's transitions.
        self.requests_mocker.get(
            re.compile(
                fr"https://{self.HOST}/rest/api/2/issue/OSPR-\d+/transitions" +
                r"\?expand=transitions.fields"
            ),
            json=self._issue_transitions_callback,
        )

    def request_history(self):
        """Return the list of requests made to this host."""
        return [r for r in self.requests_mocker.request_history if r.netloc == self.HOST]

    def make_issue(self, key=None):
        """Make fake issue data."""
        if key is None:
            key = "OSPR-{}".format(random.randint(1001, 9009))
        issue = {
            "key": key,
            "fields": {
                "status": {
                    "name": self.INITIAL_STATE,
                },
            },
        }
        self.issues[key] = issue
        return issue

    def delete_issue(self, issue):
        """Delete a fake issue."""
        del self.issues[issue["key"]]

    def _new_issue_callback(self, request, _):
        """Responds to the API endpoint for creating new issues."""
        project = request.json()["fields"]["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        return self.make_issue(key)

    def _issue_transitions_callback(self, request, context):
        """Responds to the API endpoint for listing transitions between issue states."""
        # Get the issue key from the request.
        match_key = re.search(r"/rest/api/2/issue/(OSPR-\d+)/transitions", request.path)
        assert match_key is not None
        key = match_key.group(1)

        if key in self.issues:
            # The transitions don't include the transitions to the current state.
            issue = self.issues[key]

            return {
                "transitions": [
                    {"id": id, "to": {"name": name}}
                    for name, id in self.TRANSITIONS.items()
                    if name != issue["fields"]["status"]["name"]
                ],
            }
        else:
            # No such issue.
            context.status_code = 404
            return {}

    def transitions_post(self, issue):
        """Return a mocker for the POST to transition an issue."""
        return self.requests_mocker.post(
            f"https://{self.HOST}/rest/api/2/issue/{issue['key']}/transitions"
        )
