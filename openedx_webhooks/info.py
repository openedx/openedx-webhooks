"""
Get information about people, repos, orgs, pull requests, etc.
"""

from __future__ import unicode_literals, print_function

from datetime import date
from iso8601 import parse_date
import requests
import yaml

from openedx_webhooks.utils import memoize


def read_repotools_yaml_file(filename):
    """Read a YAML file from the repo-tools repo."""
    resp = requests.get("https://raw.githubusercontent.com/edx/repo-tools/master/" + filename)
    if not resp.ok:
        raise requests.exceptions.RequestException(resp.text)
    return yaml.safe_load(resp.text)

@memoize
def get_people_file():
    return read_repotools_yaml_file("people.yaml")

@memoize
def get_repos_file():
    return read_repotools_yaml_file("repos.yaml")

@memoize
def get_orgs_file():
    return read_repotools_yaml_file("orgs.yaml")

def get_orgs(key):
    """Return the set of orgs with a true `key`."""
    orgs = get_orgs_file()
    return set(o for o, info in orgs.items() if info.get(key, False))


def is_internal_pull_request(pull_request):
    """
    Was this pull request created by someone who works for edX?
    """
    people = get_people_file()
    author = pull_request["user"]["login"].decode('utf-8')
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    committer_institutions = get_orgs("committer")
    return (
        author in people and
        people[author].get("institution") in committer_institutions and
        people[author].get("expires_on", date.max) > created_at.date()
    )


def is_contractor_pull_request(pull_request):
    """
    Was this pull request created by someone in an organization that does
    paid contracting work for edX? If so, we don't know if this pull request
    falls under edX's contract, or if it should be treated as a pull request
    from the community.
    """
    people = get_people_file()
    author = pull_request["user"]["login"].decode('utf-8')
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    contractor_orgs = get_orgs("contractor")
    return (
        author in people and
        people[author].get("institution") in contractor_orgs and
        people[author].get("expires_on", date.max) > created_at.date()
    )
