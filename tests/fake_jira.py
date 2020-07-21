"""A fake implementation of the Jira API."""

import dataclasses
import itertools
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

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
    contributor_name: Optional[str] = None
    customer: Optional[str] = None
    pr_number: Optional[int] = None
    repo: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    labels: Set[str] = field(default_factory=set)
    epic_link: Optional[str] = None
    platform_map_1_2: Optional[str] = None
    platform_map_3_4: Optional[str] = None
    blended_project_status_page: Optional[str] = None
    blended_project_id: Optional[str] = None

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
                FakeJira.EPIC_LINK: self.epic_link,
                FakeJira.CONTRIBUTOR_NAME: self.contributor_name,
                FakeJira.CUSTOMER: self.customer,
                FakeJira.PR_NUMBER: self.pr_number,
                FakeJira.REPO: self.repo,
                FakeJira.URL: self.url,
                FakeJira.PLATFORM_MAP_1_2: self.platform_map_1_2,
                FakeJira.PLATFORM_MAP_3_4: self.platform_map_3_4,
                FakeJira.BLENDED_PROJECT_STATUS_PAGE: self.blended_project_status_page,
                FakeJira.BLENDED_PROJECT_ID: self.blended_project_id,
            },
        }


class FakeJira(faker.Faker):
    """A fake implementation of the Jira API, specialized to the OSPR project."""

    HOST = "openedx.atlassian.net"

    # Custom fields for OSPR. The values are arbitrary.
    CONTRIBUTOR_NAME = "custom_101"
    CUSTOMER = "custom_102"
    PR_NUMBER = "custom_103"
    REPO = "custom_104"
    URL = "customfield_10904"   # This one is hard-coded
    EPIC_LINK = "custom_900"
    PLATFORM_MAP_1_2 = "custom_105"
    PLATFORM_MAP_3_4 = "custom_106"
    BLENDED_PROJECT_STATUS_PAGE = "custom_107"
    BLENDED_PROJECT_ID = "custom_108"

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
        # Map from issue keys to Issue objects.
        self.issues: Dict[str, Issue] = {}
        # Map from old keys to new keys for moved issues.
        self.moves: Dict[str, str] = {}

    @faker.route(r"/rest/api/2/field")
    def _get_field(self, _match, _request, _context) -> List[Dict]:
        # Custom fields particular to the OSPR project.
        return [{"id": i, "name": n, "custom": True} for i, n in [
            (self.EPIC_LINK, "Epic Link"),
            (self.CONTRIBUTOR_NAME, "Contributor Name"),
            (self.CUSTOMER, "Customer"),
            (self.PR_NUMBER, "PR Number"),
            (self.REPO, "Repo"),
            (self.URL, "URL"),
            (self.PLATFORM_MAP_1_2, "Platform Map Area (Levels 1 & 2)"),
            (self.PLATFORM_MAP_3_4, "Platform Map Area (Levels 3 & 4)"),
            (self.BLENDED_PROJECT_STATUS_PAGE, "Blended Project Status Page"),
            (self.BLENDED_PROJECT_ID, "Blended Project ID"),
        ]]

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
        kwargs = dict(
            issuetype=fields["issuetype"]["name"],
            summary=fields.get("summary"),
            description=fields.get("description"),
            labels=set(fields.get("labels")),
            epic_link=fields.get(FakeJira.EPIC_LINK),
            contributor_name=fields.get(FakeJira.CONTRIBUTOR_NAME),
            customer=fields.get(FakeJira.CUSTOMER),
            pr_number=fields.get(FakeJira.PR_NUMBER),
            repo=fields.get(FakeJira.REPO),
            url=fields.get(FakeJira.URL),
            platform_map_1_2=fields.get(FakeJira.PLATFORM_MAP_1_2),
            platform_map_3_4=fields.get(FakeJira.PLATFORM_MAP_3_4),
        )
        self.make_issue(key, **kwargs)
        # Response is only some information:
        # {"id":"184975","key":"OSPR-4836","self":"https://openedx.atlassian.net/rest/api/2/issue/184975"}
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
            if FakeJira.EPIC_LINK in fields:
                kwargs["epic_link"] = fields.pop(FakeJira.EPIC_LINK)
            if FakeJira.PLATFORM_MAP_1_2 in fields:
                kwargs["platform_map_1_2"] = fields.pop(FakeJira.PLATFORM_MAP_1_2)
            assert fields == {}, f"Didn't handle requested changes: {fields=}"
            issue = dataclasses.replace(issue, **kwargs)
            self.issues[issue.key] = issue
            context.status_code = 204
        else:
            context.status_code = 404

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)", "DELETE")
    def _delete_issue(self, match, _request, context) -> None:
        """
        Implement the endpoint for deleting issues.
        """
        if (issue := self.find_issue(match["key"])) is not None:
            del self.issues[issue.key]
            context.status_code = 204
        else:
            context.status_code = 404

    @faker.route(r"/rest/api/2/issue/(?P<key>\w+-\d+)/transitions")
    def _get_issue_transitions(self, match, _request, context) -> Dict:
        """Responds to the API endpoint for listing transitions between issue states."""
        if (issue := self.find_issue(match["key"])) is not None:
            # The transitions don't include the transitions to the current state.
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
        issue = self.find_issue(match["key"])
        assert issue is not None
        transition_id = request.json()["transition"]["id"]
        issue.status = self.TRANSITION_IDS[transition_id]

    @faker.route(r"/rest/api/2/search", "GET")
    def _get_search(self, _match, request, _context):
        """
        Implement the search endpoint.
        """
        jql = request.qs["jql"][0]
        # We only handle certain specific queries.
        if bd_ids := re.findall(r'"Blended Project ID" ~ "(.*?)"', jql):
            issues = [iss for iss in self.issues.values() if iss.blended_project_id in bd_ids]
        else:
            # We don't understand this query.
            _context.status_code = 500
            return None
        return {
            "issues": [iss.as_json() for iss in issues],
            "total": len(issues),
        }
