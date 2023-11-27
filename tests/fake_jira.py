"""A fake implementation of the Jira API."""

import dataclasses
import itertools
import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from . import faker


issue_ids = itertools.count(start=101, step=13)

def _make_issue_key(project: str) -> str:
    """Generate the next issue key for a project."""
    num = next(issue_ids)
    return f"{project}-{num}"


@dataclass
class Issue:
    """A Jira issue."""
    key: str
    status: str
    issuetype: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    labels: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        # Jira labels can't have spaces in them. Check that they are only
        # letters, numbers, dashes.
        for label in self.labels:
            if re.search(r"[^a-zA-Z0-9-]", label):
                raise ValueError(f"Label {label!r} has invalid characters")
            if len(label) < 3:
                raise ValueError(f"Label {label!r} is too short")

    def as_json(self) -> Dict:
        return {
            "key": self.key,
            "fields": {
                "project": {"key": self.key.partition("-")[0]},
                "status": {"name": self.status},
                "issuetype": {"name": self.issuetype},
                "summary": self.summary or None,
                "description": self.description or None,
                "labels": sorted(self.labels),
            },
        }


class FakeJira(faker.Faker):
    """A fake implementation of the Jira API, specialized to the OSPR project."""

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

    def __init__(self, host) -> None:
        super().__init__(host=host)
        # Map from issue keys to Issue objects.
        self.issues: Dict[str, Issue] = {}
        # Map from old keys to new keys for moved issues.
        self.moves: Dict[str, str] = {}

    def make_issue(self, key: Optional[str] = None, project: str = "OSPR", **kwargs) -> Issue:
        """Make fake issue data."""
        if key is None:
            key = _make_issue_key(project)
        issue = Issue(key=key, status=self.INITIAL_STATE, **kwargs)
        self.issues[key] = issue
        return issue

    def find_issue(self, key: str) -> Optional[Issue]:
        """
        Find an issue, even across moves.

        Returns None if the issue doesn't exist.
        """
        while key in self.moves:
            key = self.moves[key]
        return self.issues.get(key)

    def move_issue(self, issue: Issue, project: str) -> Issue:
        """Move an issue to a new project."""
        the_issue = self.find_issue(issue.key)
        assert self.issues[issue.key] is the_issue
        new_key = _make_issue_key(project)
        self.moves[issue.key] = new_key
        del self.issues[issue.key]
        the_issue.key = new_key
        self.issues[new_key] = the_issue
        return the_issue

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)")
    def _get_issue(self, match, _request, context) -> Dict:
        """Implement the GET issue endpoint."""
        if (issue := self.find_issue(match["key"])) is not None:
            return issue.as_json()
        else:
            context.status_code = 404
            return {"errorMessages": ["Issue does not exist or you do not have permission to see it."], "errors": {}}

    @faker.route(r"/rest/api/2/issue", "POST")
    def _post_issue(self, _match, request, context):
        """Responds to the API endpoint for creating new issues."""
        issue_data = request.json()
        fields = issue_data["fields"]
        project = fields["project"]["key"]
        key = _make_issue_key(project)
        kwargs = dict(  # pylint: disable=use-dict-literal
            issuetype=fields["issuetype"]["name"],
            summary=fields.get("summary"),
            description=fields.get("description"),
            labels=set(fields.get("labels")),
        )
        self.make_issue(key, **kwargs)
        # Response is only some information:
        # {"id":"184975","key":"OSPR-4836","self":"https://test.atlassian.net/rest/api/2/issue/184975"}
        # We don't use id or self, so just return the key.
        context.status_code = 201
        return {"key": key}

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)", "PUT")
    def _put_issue(self, match, request, context) -> None:
        """
        Implement the issue PUT endpoint for updating issues.
        """
        if (issue := self.find_issue(match["key"])) is not None:
            changes = request.json()
            fields = changes["fields"]
            kwargs = {}
            if "summary" in fields:
                kwargs["summary"] = fields.pop("summary")
            if "description" in fields:
                kwargs["description"] = fields.pop("description")
            if "labels" in fields:
                kwargs["labels"] = set(fields.pop("labels"))
            assert fields == {}, f"Didn't handle requested changes: {fields=}"
            issue = dataclasses.replace(issue, **kwargs)
            self.issues[issue.key] = issue
            context.status_code = 204
        else:
            context.status_code = 404
