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

    TRANSITION_IDS = {id: name for name, id in TRANSITIONS.items()}

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

        # Get an issue.
        self.requests_mocker.get(
            re.compile(fr"https://{self.HOST}/rest/api/2/issue/OSPR-\d+"),
            json=self._get_issue_callback,
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

        # Transition an issue.
        self.transition_issue_post = self.requests_mocker.post(
            re.compile(fr"https://{self.HOST}/rest/api/2/issue/OSPR-\d+/transitions"),
            json=self._transition_issue_callback,
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

    def get_issue_status(self, issue):
        """Return the status of an issue."""
        return self.issues[issue["key"]]["fields"]["status"]["name"]

    def set_issue_status(self, issue, status):
        """Set the status of a fake issue."""
        self.issues[issue["key"]]["fields"]["status"]["name"] = status

    def _new_issue_callback(self, request, _):
        """Responds to the API endpoint for creating new issues."""
        project = request.json()["fields"]["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        return self.make_issue(key)

    def _get_issue_callback(self, request, _):
        """Implement the GET issue endpoint."""
        # Get the issue key from the request.
        key = get_regex_value(r"/rest/api/2/issue/(OSPR-\d+)", request.path)
        assert key in self.issues
        return self.issues[key]

    def _issue_transitions_callback(self, request, context):
        """Responds to the API endpoint for listing transitions between issue states."""
        # Get the issue key from the request.
        key = get_regex_value(r"/rest/api/2/issue/(OSPR-\d+)/transitions", request.path)
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

    def _transition_issue_callback(self, request, _):
        """
        Implement the POST to transition an issue to a new status.
        """
        key = get_regex_value(r"/rest/api/2/issue/(OSPR-\d+)/transitions", request.path)
        assert key in self.issues
        transition_id = request.json()["transition"]["id"]
        self.set_issue_status(self.issues[key], self.TRANSITION_IDS[transition_id])


def get_regex_value(pattern, string):
    """
    Search a string with a pattern (which must match), and return the group(1) value.
    """
    match = re.search(pattern, string)
    assert match is not None
    return match[1]
