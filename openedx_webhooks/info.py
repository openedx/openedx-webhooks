"""
Get information about people, repos, orgs, pull requests, etc.
"""

from __future__ import unicode_literals, print_function

from datetime import date
from iso8601 import parse_date
import requests
import yaml

from openedx_webhooks.utils import memoize


def _read_repotools_yaml_file(filename, session=None):
    """Read a YAML file from the repo-tools repo."""
    return yaml.safe_load(_read_repotools_file(filename, session=session))

@memoize
def _read_repotools_file(filename, session=None):
    """Read the text of a repo-tools file."""
    session = session or requests.Session()
    resp = session.get("https://raw.githubusercontent.com/edx/repo-tools/master/" + filename)
    resp.raise_for_status()
    return resp.text

def get_people_file(session=None):
    return _read_repotools_yaml_file("people.yaml", session=session)

def get_repos_file(session=None):
    return _read_repotools_yaml_file("repos.yaml", session=session)

def get_orgs_file(session=None):
    return _read_repotools_yaml_file("orgs.yaml", session=session)

def get_orgs(key, session=None):
    """Return the set of orgs with a true `key`."""
    orgs = get_orgs_file(session=session)
    return set(o for o, info in orgs.items() if info.get(key, False))


def is_internal_pull_request(pull_request, session=None):
    """
    Was this pull request created by someone who works for edX?
    """
    return _is_pull_request(pull_request, "committer", session=session)

def is_contractor_pull_request(pull_request, session=None):
    """
    Was this pull request created by someone in an organization that does
    paid contracting work for edX? If so, we don't know if this pull request
    falls under edX's contract, or if it should be treated as a pull request
    from the community.
    """
    return _is_pull_request(pull_request, "contractor", session=session)


def _is_pull_request(pull_request, kind, session=None):
    """
    Is this pull request of a certain kind?

    Arguments:
        pull_request: the dict data read from GitHub.
        kind (str): either "committer" or "contractor".

    Returns:
        bool

    """
    people = get_people_file(session=session)
    author = pull_request["user"]["login"].decode('utf-8')
    if author not in people:
        # We don't know this person!
        return False

    person = people[author]
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    if person.get("expires_on", date.max) <= created_at.date():
        # This person's agreement has expired.
        return False

    if person.get(kind, False):
        # This person has the flag personally.
        return True

    the_orgs = get_orgs(kind, session=session)
    if person.get("institution") in the_orgs:
        # This person's institution has the flag.
        return True

    return False
