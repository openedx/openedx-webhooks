"""
A fake implementation of the GitHub REST and GraphQL API.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime
import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from openedx_webhooks.cla_check import CLA_CONTEXT
from openedx_webhooks.types import GhProject

from . import faker
from .helpers import check_good_graphql, check_good_markdown


class FakeGitHubException(faker.FakerException):
    def as_json(self) -> Dict:
        j = {"message": str(self)}
        return j

class DoesNotExist(FakeGitHubException):
    """A requested object does not exist."""
    status_code = 404

def fake_sha():
    """A realistic stand-in for a commit sha."""
    return "".join(random.choice("0123456789abcdef") for c in range(32))

def fake_node_id():
    """A plausible stand-in for a node id."""
    return "NODE_" + "".join(random.choice("0123456789abcdef") for c in range(16))

@dataclass
class User:
    login: str = "some-user"
    name: str = "Some User"
    type: str = "User"

    def as_json(self):
        return {
            "login": self.login,
            "name": self.name,
            "type": self.type,
            "url": f"https://api.github.com/users/{self.login}",
            "html_url": f"https://github.com/{self.login}",
        }


@dataclass
class Label:
    name: str
    color: Optional[str] = "ededed"
    description: Optional[str] = None

    def as_json(self):
        return dataclasses.asdict(self)

DEFAULT_LABELS = [
    {"name": "bug", "color": "d73a4a", "description": "Something isn't working"},
    {"name": "documentation", "color": "0075ca", "description": "Improvements or additions to documentation"},
    {"name": "duplicate", "color": "cfd3d7", "description": "This issue or pull request already exists"},
    {"name": "enhancement", "color": "a2eeef", "description": "New feature or request"},
    {"name": "good first issue", "color": "7057ff", "description": "Good for newcomers"},
    {"name": "help wanted", "color": "008672", "description": "Extra attention is needed"},
    {"name": "invalid", "color": "e4e669", "description": "This doesn't seem right"},
    {"name": "question", "color": "d876e3", "description": "Further information is requested"},
    {"name": "wontfix", "color": "ffffff", "description": "This will not be worked on"},
]

comment_ids = itertools.count(start=1001, step=137)

@dataclass
class Comment:
    """
    A comment on an issue or pull request.
    """
    id: int = field(init=False, default_factory=comment_ids.__next__)
    user: User
    body: str

    def __post_init__(self):
        self.validate()

    def validate(self):
        check_good_markdown(self.body)

    def as_json(self) -> Dict:
        return {
            "id": self.id,
            "body": self.body,
            "user": self.user.as_json(),
        }


def patchable_now():
    """Current time, in a way that freezegun can monkeypatch."""
    return datetime.datetime.now()


@dataclass
class PullRequest:
    repo: Repo
    number: int
    user: User
    title: str = ""
    body: Optional[str] = ""
    node_id: str = field(default_factory=fake_node_id)
    created_at: datetime.datetime = field(default_factory=patchable_now)
    closed_at: Optional[datetime.datetime] = None
    comments: List[int] = field(default_factory=list)
    labels: Set[str] = field(default_factory=set)
    state: str = "open"
    merged: bool = False
    draft: bool = False
    commits: List[str] = field(default_factory=list)
    ref: str = ""

    def as_json(self, brief=False) -> Dict:
        j = {
            "number": self.number,
            "node_id": self.node_id,
            "state": self.state,
            "draft": self.draft,
            "title": self.title,
            "user": self.user.as_json(),
            "body": self.body,
            "labels": [self.repo.get_label(lbl).as_json() for lbl in sorted(self.labels)],
            "base": {
                "repo": self.repo.as_json(),
                "ref": self.ref,
            },
            "head": {
                "sha": self.commits[-1],
            },
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "closed_at": self.closed_at.strftime("%Y-%m-%dT%H:%M:%SZ") if self.closed_at else None,
            "url": f"{self.repo.github.host}/repos/{self.repo.full_name}/pulls/{self.number}",
            "html_url": f"https://github.com/{self.repo.full_name}/pull/{self.number}",
        }
        if not brief:
            j["merged"] = self.merged
        return j

    def close(self, merge=False):
        """
        Close a pull request, maybe merging it.
        """
        self.state = "closed"
        self.merged = merge
        self.closed_at = datetime.datetime.now()

    def reopen(self):
        """
        Re-open a pull request.
        """
        self.state = "open"
        self.merged = False
        self.closed_at = None

    def add_comment(self, user="someone", **kwargs) -> Comment:
        comment = self.repo.make_comment(user, **kwargs)
        self.comments.append(comment.id)
        return comment

    def list_comments(self) -> List[Comment]:
        return [com for cid in self.comments if (com := self.repo.comments.get(cid))]

    def delete_comment(self, comment_number) -> None:
        del self.repo.comments[comment_number]

    def set_labels(self, labels: Iterable[str]) -> None:
        """
        Set the labels on this pull request.
        """
        labels = set(labels)
        for label in labels:
            if not self.repo.has_label(label):
                self.repo.add_label(name=label)
        self.labels = labels

    def status(self, context):
        assert context == CLA_CONTEXT
        return self.repo.github.cla_statuses.get(self.commits[-1])

    def is_in_project(self, project: GhProject) -> bool:
        proj_node_id = self.repo.github.projects.get(project)
        if proj_node_id is None:
            return False
        return self.node_id in self.repo.github.project_items[proj_node_id]


@dataclass
class Repo:
    github: FakeGitHub
    owner: str
    repo: str
    private: bool
    labels: Dict[str, Label] = field(default_factory=dict)
    pull_requests: Dict[int, PullRequest] = field(default_factory=dict)
    comments: Dict[int, Comment] = field(default_factory=dict)

    @property
    def full_name(self):
        return f"{self.owner}/{self.repo}"

    def as_json(self) -> Dict:
        return {
            "full_name": self.full_name,
            "name": self.repo,
            "owner": {
                "login": self.owner,
            },
            "private": self.private,
        }

    def make_pull_request(self, user="someone", number=None, **kwargs) -> PullRequest:
        user = self.github.get_user(user, create=True)
        if number is None:
            highest = max(self.pull_requests.keys(), default=10)
            number = highest + random.randint(10, 20)
        commits = [fake_sha() for _ in range(random.randint(1, 4))]
        pr = PullRequest(self, number, user, commits=commits, **kwargs)
        self.pull_requests[number] = pr
        self.github.pr_nodes[pr.node_id] = pr
        return pr

    def list_pull_requests(self, state: str) -> List[PullRequest]:
        return [pr for pr in self.pull_requests.values() if (state == "all") or (pr.state == state)]

    def get_pull_request(self, number: int) -> PullRequest:
        try:
            return self.pull_requests[number]
        except KeyError:
            raise DoesNotExist(f"Pull request {self.full_name} #{number} does not exist")

    def make_comment(self, user, **kwargs) -> Comment:
        user = self.github.get_user(user, create=True)
        comment = Comment(user, **kwargs)
        self.comments[comment.id] = comment
        return comment

    def get_label(self, name: str) -> Label:
        try:
            return self.labels[name]
        except KeyError:
            raise DoesNotExist(f"Label {self.full_name} {name!r} does not exist")

    def has_label(self, name: str) -> bool:
        return name in self.labels

    def _set_labels(self, data: List[Dict]) -> None:
        self.labels = {}
        for kwargs in data:
            self.add_label(**kwargs)

    def add_label(self, **kwargs) -> Label:
        label = Label(**kwargs)
        self.labels[label.name] = label
        return label


class Flaky404:
    """
    A middleware to emulate flaky behavior of GitHub's.
    """
    def __init__(self, fraction_404):
        self.fraction_404 = fraction_404
        self.paths = set()

    def middleware(self, request, context):
        """
        For GET requests, maybe return a 404 the first time it's requested.
        """
        if request.method != "GET":
            return None
        if request.path in self.paths:
            return None
        self.paths.add(request.path)
        if random.random() < self.fraction_404:
            context.status_code = 404
            return {"message": "Not Found"}
        return None


class FakeGitHub(faker.Faker):

    def __init__(self, login, fraction_404=0) -> None:
        super().__init__(host="https://api.github.com")
        if fraction_404:
            self.add_middleware(Flaky404(fraction_404).middleware)

        self.login = login
        self.users: Dict[str, User] = {}
        self.repos: Dict[str, Repo] = {}

        # Map from PR node id to pull request.
        self.pr_nodes: Dict[str, PullRequest] = {}
        # Map from Project node id to (orgname, number) pairs.
        self.project_nodes: Dict[str, GhProject] = {}
        # Map from (orgname, number) project ids to project node id.
        self.projects: Dict[GhProject, str] = {}
        # Map from PR node id to Project node ids, and from Project node id
        # to PR node ids.
        self.project_items: Dict[str, Set[str]] = collections.defaultdict(set)

        self.cla_statuses: Dict[str, Dict[str, str]] = {}

    def make_user(self, login: str, **kwargs) -> User:
        u = self.users[login] = User(login, **kwargs)
        return u

    def get_user(self, login: str, create: bool = False) -> User:
        user = self.users.get(login)
        if user is None:
            if create:
                user = self.make_user(login)
            else:
                raise DoesNotExist(f"User {login!r} does not exist")
        return user

    def make_repo(self, owner: str, repo: str, private: bool=False) -> Repo:
        r = Repo(self, owner, repo, private)
        r._set_labels(DEFAULT_LABELS)
        self.repos[f"{owner}/{repo}"] = r
        return r

    def get_repo(self, owner: str, repo: str) -> Repo:
        try:
            return self.repos[f"{owner}/{repo}"]
        except KeyError:
            raise DoesNotExist(f"Repo {owner}/{repo} does not exist")

    def make_pull_request(self, owner: str = "an-org", repo: str = "a-repo", **kwargs) -> PullRequest:
        """Convenience: make a repo and a pull request."""
        rep = self.make_repo(owner, repo)
        pr = rep.make_pull_request(**kwargs)
        return pr

    # Users

    @faker.route(r"/user")
    def _get_user(self, _match, _request, _context) -> Dict:
        return {"login": self.login}

    @faker.route(r"/users/(?P<login>[^/]+)")
    def _get_users(self, match, _request, _context) -> Dict:
        # https://developer.github.com/v3/users/#get-a-user
        return self.users[match["login"]].as_json()

    # Organization repos

    @faker.route(r"/orgs/(?P<org>[^/]+)/repos")
    def _get_org_repos(self, match, _request, _context) -> List[Dict]:
        org_prefix = match["org"] + "/"
        repos = [repo for name, repo in self.repos.items() if name.startswith(org_prefix)]
        return [repo.as_json() for repo in repos]

    # Pull requests

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls")
    def _get_pulls(self, match, request, _context) -> List[Dict]:
        # https://developer.github.com/v3/pulls/#list-pull-requests
        r = self.get_repo(match["owner"], match["repo"])
        state = request.qs.get("state", ["open"])[0]
        return [pr.as_json(brief=True) for pr in r.list_pull_requests(state)]

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pulls/(?P<number>\d+)")
    def _get_pull(self, match, _request, _context) -> Dict:
        # https://developer.github.com/v3/pulls/#get-a-pull-request
        r = self.get_repo(match["owner"], match["repo"])
        pr = r.get_pull_request(int(match["number"]))
        return pr.as_json()

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)", "PATCH")
    def _patch_issues(self, match, request, _context) -> Dict:
        # https://developer.github.com/v3/issues/#update-an-issue
        r = self.get_repo(match["owner"], match["repo"])
        pr = r.get_pull_request(int(match["number"]))
        patch = request.json()
        if "labels" in patch:
            pr.set_labels(patch["labels"])
        r.pull_requests[pr.number] = pr
        return pr.as_json()

    # Commmits

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/statuses/(?P<sha>[a-fA-F0-9]+)(\?.*)?")
    def _get_pr_status_check(self, match, _request, _context) -> List[Dict[str, Any]]:
        sha: str = match["sha"]
        if sha in self.cla_statuses:
            return [self.cla_statuses[sha]]
        else:
            return []

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/statuses/(?P<sha>[a-fA-F0-9]+)(\?.*)?", 'POST')
    def _post_pr_status_update(self, match, request, _context) -> List[Dict[str, Any]]:
        data = request.json()
        assert data['context'] == CLA_CONTEXT
        self.cla_statuses[match['sha']] = data
        return [data]

    # Comments

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/comments(\?.*)?")
    def _get_issues_comments(self, match, _request, _context) -> List[Dict]:
        # https://developer.github.com/v3/issues/comments/#list-issue-comments
        r = self.get_repo(match["owner"], match["repo"])
        pr = r.get_pull_request(int(match["number"]))
        return [com.as_json() for cid in pr.comments if (com := r.comments.get(cid))]

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/comments", "POST")
    def _post_issues_comments(self, match, request, _context) -> Dict:
        # https://developer.github.com/v3/issues/comments/#create-an-issue-comment
        r = self.get_repo(match["owner"], match["repo"])
        pr = r.get_pull_request(int(match["number"]))
        comment = pr.add_comment(user=self.login, body=request.json()["body"])
        return comment.as_json()

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)", "PATCH")
    def _patch_issues_comments(self, match, request, _context) -> Dict:
        # https://developer.github.com/v3/issues/comments/#update-an-issue-comment
        r = self.get_repo(match["owner"], match["repo"])
        comment = r.comments[int(match["comment_id"])]
        comment.body = request.json()["body"]
        comment.validate()
        return comment.as_json()

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/comments/(?P<comment_id>\d+)", "DELETE")
    def _delete_issues_comments(self, match, _request, context) -> None:
        # https://developer.github.com/v3/issues/comments/#delete-an-issue-comment
        r = self.get_repo(match["owner"], match["repo"])
        del r.comments[int(match["comment_id"])]
        context.status_code = 204

    # GraphQL

    @faker.route(r"/graphql", "POST")
    def _graphql(self, _match, request, _context) -> Dict:
        """Dispatch a GraphQL request."""
        data = request.json()
        query = data["query"]
        check_good_graphql(query)
        slug = query.split()[1]
        kwargs = data["variables"]
        method = getattr(self, f"_graphql_{slug}")
        if method is None:
            raise Exception(f"Unknown GraphQL slug in FakeGitHub: {slug = }")
        return method(**kwargs)

    def _graphql_ProjectsForPr(self, owner: str, name: str, number: int) -> Dict:
        r = self.get_repo(owner, name)
        pr = r.get_pull_request(number)
        project_node_ids = self.project_items[pr.node_id]
        nodes = []
        for node_id in project_node_ids:
            org, num = self.project_nodes[node_id]
            nodes.append(
                {"project": {"owner": {"login": org}, "number": num}}
            )
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "projectItems": {
                            "nodes": nodes,
                        }
                    }
                }
            }
        }

    def _graphql_OrgProjectId(self, owner: str, number: int) -> Dict:
        proj_id = f"PROJECT:{owner}.{number}"
        self.project_nodes[proj_id] = (owner, number)
        self.projects[(owner, number)] = proj_id
        return {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": proj_id
                    }
                }
            }
        }

    def _graphql_AddProjectItem(self, projectId: str, prNodeId: str) -> Dict:
        self.project_items[projectId].add(prNodeId)
        self.project_items[prNodeId].add(projectId)
        return {
            'data': {
                'addProjectV2ItemById': {
                    'item': {'id': 'saul goodman'}
                }
            }
        }

    def _graphql_UpdateProjectItem(self, projectId: str, itemId: str, fieldId: str, value) -> dict:
        self.project_items[projectId].add(itemId)
        self.project_items[fieldId].add(value)
        return {'data': {}}

    def _graphql_OrgProjectMetadata(self, orgname: str, number: int) -> dict:
        proj_id = f"PROJECT:{orgname}.{number}"
        self.project_nodes[proj_id] = (orgname, number)
        self.projects[(orgname, number)] = proj_id
        return {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": proj_id,
                        "fields": {
                            "nodes": [
                                {"name": "Name", "id": "name-id", "dataType": "text"},
                                {"name": "Date opened", "id": "date-opened-id", "dataType": "date"},
                                {"name": "Repo Owner / Owning Team", "id": "repo-owner-id", "dataType": "text"},
                            ]
                        }
                    }
                }
            }
        }
