"""A fake implementation of the Jira API."""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from . import faker


@dataclass
class Issue:
    """A Jira issue."""
    key: str
    status: str
    issuetype: Optional[str] = None
    contributor_name: Optional[str] = None
    customer: Optional[str] = None
    pr_number: Optional[int] = None
    repo: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    labels: Set[str] = field(default_factory=set)

    def as_json(self) -> Dict:
        return {
            "key": self.key,
            "fields": {
                "project": {"key": self.key.partition("-")[0]},
                "status": {"name": self.status},
                "issuetype": {"name": self.issuetype},
                "summary": self.summary,
                "description": self.description,
                "labels": sorted(self.labels),
                FakeJira.CONTRIBUTOR_NAME: self.contributor_name,
                FakeJira.CUSTOMER: self.customer,
                FakeJira.PR_NUMBER: self.pr_number,
                FakeJira.REPO: self.repo,
                FakeJira.URL: self.url,
            },
        }


class FakeJira(faker.Faker):
    """A fake implementation of the Jira API, specialized to the OSPR project."""

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

    def __init__(self):
        super().__init__(host="https://openedx.atlassian.net")
        self.issues = {}

    @faker.route(r"/rest/api/2/field")
    def _get_field(self, _match, _request, _context) -> List[Dict]:
        # Custom fields particular to the OSPR project.
        return [
            {"id": self.CONTRIBUTOR_NAME, "name": "Contributor Name", "custom": True},
            {"id": self.CUSTOMER, "name": "Customer", "custom": True},
            {"id": self.PR_NUMBER, "name": "PR Number", "custom": True},
            {"id": self.REPO, "name": "Repo", "custom": True},
            {"id": self.URL, "name": "URL", "custom": True},
        ]

    def make_issue(self, key=None, **kwargs):
        """Make fake issue data."""
        if key is None:
            key = "OSPR-{}".format(random.randint(1001, 9009))
        issue = Issue(key=key, status=self.INITIAL_STATE, **kwargs)
        self.issues[key] = issue
        return issue

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)")
    def _get_issue(self, match, _request, _context) -> Dict:
        """Implement the GET issue endpoint."""
        key = match["key"]
        assert key in self.issues
        return self.issues[key].as_json()

    @faker.route(r"/rest/api/2/issue", "POST")
    def _post_issue(self, _match, request, _context):
        """Responds to the API endpoint for creating new issues."""
        issue_data = request.json()
        fields = issue_data["fields"]
        project = fields["project"]["key"]
        key = "{}-{}".format(project, random.randint(111, 999))
        kwargs = dict(
            issuetype="Pull Request Review",
            summary=fields.get("summary"),
            description=fields.get("description"),
            labels=fields.get("labels"),
            contributor_name=fields.get(FakeJira.CONTRIBUTOR_NAME),
            customer=fields.get(FakeJira.CUSTOMER),
            pr_number=fields.get(FakeJira.PR_NUMBER),
            repo=fields.get(FakeJira.REPO),
            url=fields.get(FakeJira.URL),
        )
        issue = self.make_issue(key, **kwargs)
        return issue.as_json()

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)/transitions")
    def _get_issue_transitions(self, match, _request, context) -> Dict:
        """Responds to the API endpoint for listing transitions between issue states."""
        key = match["key"]
        if key in self.issues:
            # The transitions don't include the transitions to the current state.
            issue = self.issues[key]

            return {
                "transitions": [
                    {"id": id, "to": {"name": name}}
                    for name, id in self.TRANSITIONS.items()
                    if name != issue.status
                ],
            }
        else:
            # No such issue.
            context.status_code = 404
            return {}

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)/transitions", "POST")
    def _post_issue_transitions(self, match, request, _context):
        """
        Implement the POST to transition an issue to a new status.
        """
        key = match["key"]
        assert key in self.issues
        transition_id = request.json()["transition"]["id"]
        self.issues[key].status = self.TRANSITION_IDS[transition_id]
