"""
A fake implementation of the GitHub REST API.
"""

from __future__ import annotations

import dataclasses
import datetime
import itertools
import random
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import unquote

from . import faker
from .helpers import check_good_markdown


class FakeGitHubException(faker.FakerException):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors

    def as_json(self) -> Dict:
        j = {"message": str(self)}
        if self.errors:
            j["errors"] = self.errors
        return j

class DoesNotExist(FakeGitHubException):
    """A requested object does not exist."""
    status_code = 404

class ValidationError(FakeGitHubException):
    status_code = 422

    def __init__(self, message="Validation Failed", **kwargs):
        super().__init__(message=message, errors=[kwargs])


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
        }


@dataclass
class Label:
    name: str
    color: Optional[str] = "ededed"
    description: Optional[str] = None

    def __post_init__(self):
        if self.color is not None and not re.fullmatch(r"[0-9a-fA-F]{6}", self.color):
            raise ValidationError(resource="Label", code="invalid", field="color")

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


@dataclass
class PullRequest:
    repo: Repo
    number: int
    user: User
    title: str = ""
    body: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    comments: List[int] = field(default_factory=list)
    labels: Set[str] = field(default_factory=set)
    state: str = "open"
    merged: bool = False
    draft: bool = False
    additions: Optional[int] = None
    deletions: Optional[int] = None

    def as_json(self, brief=False) -> Dict:
        j = {
            "number": self.number,
            "state": self.state,
            "draft": self.draft,
            "title": self.title,
            "user": self.user.as_json(),
            "body": self.body,
            "labels": [self.repo.get_label(l).as_json() for l in sorted(self.labels)],
            "base": self.repo.as_json(),
            "created_at": self.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "url": f"{self.repo.github.host}/repos/{self.repo.full_name}/pulls/{self.number}",
            "html_url": f"https://github.com/{self.repo.full_name}/pull/{self.number}",
        }
        if not brief:
            j["merged"] = self.merged
            if self.additions is not None:
                j["additions"] = self.additions
            if self.deletions is not None:
                j["deletions"] = self.deletions
        return j

    def close(self, merge=False):
        """
        Close a pull request, maybe merging it.
        """
        self.state = "closed"
        self.merged = merge

    def add_comment(self, user="someone", **kwargs) -> Comment:
        comment = self.repo.make_comment(user, **kwargs)
        self.comments.append(comment.id)
        return comment

    def list_comments(self) -> List[Comment]:
        return [self.repo.comments[cid] for cid in self.comments]

    def set_labels(self, labels: Iterable[str]) -> None:
        """
        Set the labels on this pull request.
        """
        labels = set(labels)
        for label in labels:
            if not self.repo.has_label(label):
                self.repo.add_label(name=label)
        self.labels = labels


@dataclass
class Repo:
    github: FakeGitHub
    owner: str
    repo: str
    labels: Dict[str, Label] = field(default_factory=dict)
    pull_requests: Dict[int, PullRequest] = field(default_factory=dict)
    comments: Dict[int, Comment] = field(default_factory=dict)

    @property
    def full_name(self):
        return f"{self.owner}/{self.repo}"

    def as_json(self) -> Dict:
        return {
            "repo": {
                "full_name": self.full_name,
            },
        }

    def make_pull_request(self, user="someone", number=None, **kwargs) -> PullRequest:
        user = self.github.get_user(user, create=True)
        if number is None:
            highest = max(self.pull_requests.keys(), default=10)
            number = highest + random.randint(10, 20)
        pr = PullRequest(self, number, user, **kwargs)
        self.pull_requests[number] = pr
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

    def set_labels(self, data: List[Dict]) -> None:
        self.labels = {}
        for kwargs in data:
            self.add_label(**kwargs)

    def get_labels(self) -> List[Label]:
        return sorted(self.labels.values(), key=lambda l: l.name)

    def add_label(self, **kwargs) -> Label:
        label = Label(**kwargs)
        if label.name in self.labels:
            raise ValidationError(resource="Label", code="already_exists", field="name")
        self.labels[label.name] = label
        return label

    def update_label(self, name: str, **kwargs) -> Label:
        label = self.get_label(name)
        new_label = dataclasses.replace(label, **kwargs)
        self.labels[name] = new_label
        return new_label

    def delete_label(self, name: str) -> None:
        try:
            del self.labels[name]
        except KeyError:
            raise DoesNotExist(f"Label {self.full_name} {name!r} does not exist")


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

    def __init__(self, login: str = "some-user", fraction_404=0):
        super().__init__(host="https://api.github.com")
        if fraction_404:
            self.add_middleware(Flaky404(fraction_404).middleware)

        self.login = login
        self.users: Dict[str, User] = {}
        self.repos: Dict[str, Repo] = {}

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

    def make_repo(self, owner: str, repo: str) -> Repo:
        r = Repo(self, owner, repo)
        r.set_labels(DEFAULT_LABELS)
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
        return pr.as_json()

    # Repo labels

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/labels")
    def _get_labels(self, match, _request, _context) -> List[Dict]:
        # https://developer.github.com/v3/issues/labels/#list-labels-for-a-repository
        r = self.get_repo(match["owner"], match["repo"])
        return [label.as_json() for label in r.labels.values()]

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/labels", "POST")
    def _post_labels(self, match, request, context):
        # https://developer.github.com/v3/issues/labels/#create-a-label
        r = self.get_repo(match["owner"], match["repo"])
        label = r.add_label(**request.json())
        context.status_code = 201
        return label.as_json()

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/labels/(?P<name>.*)", "PATCH")
    def _patch_labels(self, match, request, _context):
        # https://developer.github.com/v3/issues/labels/#update-a-label
        r = self.get_repo(match["owner"], match["repo"])
        data = request.json()
        if "name" in data:
            data.pop("name")
        label = r.update_label(unquote(match["name"]), **data)
        return label.as_json()

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/labels/(?P<name>.*)", "DELETE")
    def _delete_labels(self, match, _request, context):
        # https://developer.github.com/v3/issues/labels/#delete-a-label
        r = self.get_repo(match["owner"], match["repo"])
        r.delete_label(unquote(match["name"]))
        context.status_code = 204

    # Comments

    @faker.route(r"/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)/comments(\?.*)?")
    def _get_issues_comments(self, match, _request, _context) -> List[Dict]:
        # https://developer.github.com/v3/issues/comments/#list-issue-comments
        r = self.get_repo(match["owner"], match["repo"])
        pr = r.get_pull_request(int(match["number"]))
        return [r.comments[cid].as_json() for cid in pr.comments]

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
