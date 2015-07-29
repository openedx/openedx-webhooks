"""
Get information about people, repos, orgs, pull requests, etc.
"""

from __future__ import unicode_literals, print_function

from datetime import date
from iso8601 import parse_date
import requests
import yaml

from openedx_webhooks.utils import memoize


def _read_repotools_yaml_file(filename):
    """Read a YAML file from the repo-tools repo."""
    return yaml.safe_load(_read_repotools_file(filename))

@memoize
def _read_repotools_file(filename):
    """Read the text of a repo-tools file."""
    resp = requests.get("https://raw.githubusercontent.com/edx/repo-tools/master/" + filename)
    if not resp.ok:
        raise requests.exceptions.RequestException(resp.text)
    return resp.text

def get_people_file():
    return _read_repotools_yaml_file("people.yaml")

def get_repos_file():
    return _read_repotools_yaml_file("repos.yaml")

def get_orgs_file():
    return _read_repotools_yaml_file("orgs.yaml")

def get_orgs(key):
    """Return the set of orgs with a true `key`."""
    orgs = get_orgs_file()
    return set(o for o, info in orgs.items() if info.get(key, False))


def is_internal_pull_request(pull_request):
    """
    Was this pull request created by someone who works for edX?
    """
    return _is_pull_request(pull_request, "committer")

def is_contractor_pull_request(pull_request):
    """
    Was this pull request created by someone in an organization that does
    paid contracting work for edX? If so, we don't know if this pull request
    falls under edX's contract, or if it should be treated as a pull request
    from the community.
    """
    return _is_pull_request(pull_request, "contractor")


def _is_pull_request(pull_request, kind):
    """
    Is this pull request of a certain kind?

    Arguments:
        pull_request: the dict data read from GitHub.
        kind (str): either "committer" or "contractor".

    Returns:
        bool

    """
    people = get_people_file()
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

    the_orgs = get_orgs(kind)
    if person.get("institution") in the_orgs:
        # This person's institution has the flag.
        return True

    return False
