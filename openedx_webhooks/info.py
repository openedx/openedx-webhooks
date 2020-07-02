"""
Get information about people, repos, orgs, pull requests, etc.
"""

import datetime
from typing import Dict, Optional

import yaml
from iso8601 import parse_date

from openedx_webhooks.oauth import github_bp
from openedx_webhooks.types import PrDict
from openedx_webhooks.utils import memoize_timed


def _read_repotools_yaml_file(filename):
    """Read a YAML file from the repo-tools-data repo."""
    return yaml.safe_load(_read_repotools_file(filename))

@memoize_timed(minutes=15)
def _read_repotools_file(filename):
    """
    Read the text of a repo-tools-data file.
    """
    github = github_bp.session
    resp = github.get(f"https://raw.githubusercontent.com/edx/repo-tools-data/master/{filename}")
    resp.raise_for_status()
    return resp.text

def get_people_file():
    return _read_repotools_yaml_file("people.yaml")

def get_repos_file():
    return _read_repotools_yaml_file("repos.yaml")

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
    for before_date in sorted(person.get("before", {})):
        if certain_time.date() <= before_date:
            before_person = person["before"][before_date]
            update_person = person.copy()
            update_person.update(before_person)
            return update_person
    return person


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
    if person.get("expires_on", datetime.date.max) <= created_at.date():
        # This person's agreement has expired.
        return None

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
    Was this pull request created by a core committer for this repo?
    """
    person = _pr_author_data(pull_request)
    if person is None:
        return False
    if "committer" not in person:
        return False

    repo = pull_request["base"]["repo"]["full_name"]
    org = repo.partition("/")[0]
    commit_rights = person["committer"]
    if "orgs" in commit_rights:
        if org in commit_rights["orgs"]:
            return True
    if "repos" in commit_rights:
        if repo in commit_rights["repos"]:
            return True
    return False


def pull_request_has_cla(pull_request: PrDict) -> bool:
    """Does this pull request have a valid CLA?"""
    person = _pr_author_data(pull_request)
    if person is None:
        return False
    agreement = person.get("agreement", "none")
    return agreement != "none"
