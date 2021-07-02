"""
Get information about people, repos, orgs, pull requests, etc.
"""

import datetime
import re
from typing import Dict, Iterable, Optional, Union

import yaml
from iso8601 import parse_date

from openedx_webhooks.lib.github.models import PrId
from openedx_webhooks.oauth import get_github_session
from openedx_webhooks.types import PrDict, PrCommentDict
from openedx_webhooks.utils import (
    memoize,
    memoize_timed,
    paginated_get,
    retry_get,
)


@memoize_timed(minutes=15)
def _read_repotools_yaml_file(filename):
    """Read a YAML file from the repo-tools-data repo."""
    return yaml.safe_load(_read_repotools_file(filename))

def _read_repotools_file(filename):
    """
    Read the text of a repo-tools-data file.
    """
    github = get_github_session()
    resp = github.get(f"https://raw.githubusercontent.com/edx/repo-tools-data/master/{filename}")
    resp.raise_for_status()
    return resp.text

def get_people_file():
    return _read_repotools_yaml_file("people.yaml")

def get_orgs_file():
    return _read_repotools_yaml_file("orgs.yaml")

def get_labels_file():
    return _read_repotools_yaml_file("labels.yaml")

def get_orgs(key):
    """Return the set of orgs with a true `key`."""
    orgs = get_orgs_file()
    return {o for o, info in orgs.items() if info.get(key, False)}

def get_person_certain_time(person: Dict, certain_time: datetime.datetime) -> Dict:
    """
    Return person data structure for a particular time

    Arguments:
        person: dict of a Github user info from people.yaml in repo-tools-data
        certain_time: datetime.datetime object used to determine the state of the person

    """
    # Layer together all of the applicable "before" clauses.
    update_person = person.copy()
    for before_date in sorted(person.get("before", {}), reverse=True):
        if certain_time.date() > before_date:
            break
        update_person.update(person["before"][before_date])
    return update_person

def is_internal_pull_request(pull_request: PrDict) -> bool:
    """
    Was this pull request created by someone who works for edX?
    """
    return _is_pull_request(pull_request, "internal")

def is_contractor_pull_request(pull_request: PrDict) -> bool:
    """
    Was this pull request created by someone in an organization that does
    paid contracting work for edX? If so, we don't know if this pull request
    falls under edX's contract, or if it should be treated as a pull request
    from the community.
    """
    return _is_pull_request(pull_request, "contractor")

def is_bot_pull_request(pull_request: PrDict) -> bool:
    """
    Was this pull request created by a bot?
    """
    return pull_request["user"]["type"] == "Bot"


def is_draft_pull_request(pull_request: PrDict) -> bool:
    """
    Is this a draft (or WIP) pull request?
    """
    return pull_request.get("draft", False) or bool(re.search(r"\b(WIP|wip)\b", pull_request["title"]))


def _pr_author_data(pull_request: PrDict) -> Optional[Dict]:
    """
    Get data about the author of the pull request, as of the
    creation of the pull request.

    Returns None if the author had no CLA.
    """
    people = get_people_file()
    author = pull_request["user"]["login"]
    if author not in people:
        # We don't know this person!
        return None

    person = people[author]
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    person = get_person_certain_time(people[author], created_at)
    return person

def _is_pull_request(pull_request: PrDict, kind: str) -> bool:
    """
    Is this pull request of a certain kind?

    Arguments:
        pull_request: the dict data read from GitHub.
        kind (str): either "internal" or "contractor".

    Returns:
        bool

    """
    person = _pr_author_data(pull_request)
    if person is None:
        return False

    if person.get(kind, False):
        # This person has the flag personally.
        return True

    the_orgs = get_orgs(kind)
    if person.get("institution") in the_orgs:
        # This person's institution has the flag.
        return True

    return False


def is_committer_pull_request(pull_request: PrDict) -> bool:
    """
    Was this pull request created by a core committer for this repo
    or branch?
    """
    person = _pr_author_data(pull_request)
    if person is None:
        return False
    if "committer" not in person:
        return False

    repo = pull_request["base"]["repo"]["full_name"]
    org = repo.partition("/")[0]
    branch = pull_request["base"]["ref"]
    commit_rights = person["committer"]
    if not commit_rights:
        return False
    if "orgs" in commit_rights:
        if org in commit_rights["orgs"]:
            return True
    if "repos" in commit_rights:
        if repo in commit_rights["repos"]:
            return True
    if "branches" in commit_rights:
        for access_branch in commit_rights["branches"]:
            if access_branch.endswith("*") and branch.startswith(access_branch[:-1]):
                return True
            elif branch == access_branch:
                return True
    return False


def pull_request_has_cla(pull_request: PrDict) -> bool:
    """Does this pull request have a valid CLA?"""
    person = _pr_author_data(pull_request)
    if person is None:
        return False
    agreement = person.get("agreement", "none")
    return agreement != "none"


def get_blended_project_id(pull_request: PrDict) -> Optional[int]:
    """
    Find the blended project id in the pull request, if any.

    Returns:
        An int ("[BD-5]" returns 5, for example) found in the pull request, or None.
    """
    m = re.search(r"\[\s*BD\s*-\s*(\d+)\s*\]", pull_request["title"])
    if m:
        return int(m[1])
    else:
        return None


@memoize
def github_whoami():
    self_resp = retry_get(get_github_session(), "/user")
    self_resp.raise_for_status()
    return self_resp.json()


def get_bot_username() -> str:
    """What is the username of the bot?"""
    me = github_whoami()
    return me["login"]


def get_bot_comments(prid: PrId) -> Iterable[PrCommentDict]:
    """Find all the comments the bot has made on a pull request."""
    my_username = get_bot_username()
    comment_url = f"/repos/{prid.full_name}/issues/{prid.number}/comments"
    for comment in paginated_get(comment_url, session=get_github_session()):
        # I only care about comments I made
        if comment["user"]["login"] == my_username:
            yield comment


def get_jira_issue_key(pr: Union[PrId, PrDict]) -> Optional[str]:
    """Find mention of a Jira issue number in bot-authored comments."""
    if isinstance(pr, PrDict):
        prid = PrId.from_pr_dict(pr)
    else:
        prid = pr
    for comment in get_bot_comments(prid):
        # search for the first occurrence of a JIRA ticket key in the comment body
        match = re.search(r"\b([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            return match.group(0)
    return None
