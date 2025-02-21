"""
Get information about people, repos, orgs, pull requests, etc.
"""
from collections import namedtuple
import csv
import fnmatch
import logging
import re
from typing import Dict, Iterable, Literal, Optional

import yaml
from glom import glom

from openedx_webhooks import settings
from openedx_webhooks.auth import get_github_session
from openedx_webhooks.types import GhProject, JiraServer, PrDict, PrCommentDict, PrId
from openedx_webhooks.utils import (
    memoize,
    memoize_timed,
    paginated_get,
    retry_get,
)

logger = logging.getLogger(__name__)


def _github_file_url(repo_fullname: str, file_path: str) -> str:
    """Get the GitHub url to retrieve the text of a file."""
    # HEAD is used here to get the tip of the repo, regardless of whether it
    # uses master or main.
    return f"https://raw.githubusercontent.com/{repo_fullname}/HEAD/{file_path}"

def _read_yaml_data_file(filename):
    """Read a YAML file from openedx-webhooks-data."""
    return yaml.safe_load(_read_data_file(filename))

def _read_csv_data_file(filename):
    """
    Reads a CSV file from openedx-webhooks-data. Returns a csv DictReader
    object of dicts. The first row of the csv is assumed to be a header, and is
    used to assign dictionary keys.
    """
    return csv.DictReader(_read_data_file(filename).splitlines())

# Cache the webhooks data files, because every PR change reads them.
@memoize_timed(minutes=15)
def _read_data_file(filename):
    """
    Read the text of an openedx-webhooks-data file.
    """
    return read_github_file("openedx/openedx-webhooks-data", filename)


def read_github_file(repo_fullname: str, file_path: str, not_there: Optional[str] = None) -> str:
    """
    Read a GitHub file from the main or master branch of a repo.

    `not_there` is for handling missing files.  All other errors trying to
    access the file are raised as exceptions.

    Arguments:
        `repo_fullname`: the owner and repo to access: ``"openedx/edx-platform"``.
        `file_path`: the path to the file within the repo.
        `not_there`: if provided, text to return if the file (or repo) doesn't exist.

    Returns:
        The text of the file, or `not_there` if provided.
    """
    return _read_github_url(_github_file_url(repo_fullname, file_path), not_there)


def _read_github_url(url: str, not_there: Optional[str] = None) -> str:
    """
    Read the content of a GitHub URL.

    `not_there` is for handling missing files.  All other errors trying to
    access the file are raised as exceptions.

    Arguments:
        `url`: the complete GitHub URL to read.
        `not_there`: if provided, text to return if the file (or repo) doesn't exist.

    Returns:
        The text of the file, or `not_there` if provided.
    """
    github = get_github_session()
    logger.debug(f"Grabbing data file from: {url}")
    resp = github.get(url)
    if resp.status_code == 404 and not_there is not None:
        return not_there
    resp.raise_for_status()
    return resp.text


@memoize_timed(minutes=15)
def get_people_file():
    """
    Returns data formatted as a dictionary of people containing this information:
    {
        github_username: {
            name: "",
            agreement: "",
            institution: "",
        },
        ...
    }
    """
    people_data_csv = _read_csv_data_file("salesforce-export.csv")
    # Simple assurance that the data is what we expect.
    assert people_data_csv.fieldnames == [
        "First Name", "Last Name", "Number of Active Ind. CLA Contracts",
        "Title", "Account Name", "Number of Active Entity CLA Contracts", "GitHub Username","Is Core Contributor"
    ]

    people = {}

    for row in people_data_csv:
        first_name = row['First Name']
        last_name = row['Last Name']
        acct_name = row['Account Name']
        github_username = row['GitHub Username'].lower()

        people[github_username] = {
            "name": f"{first_name} {last_name}"
        }

        if acct_name == "Individual Contributors":
            people[github_username]["agreement"] = 'individual'
        elif not acct_name:
            people[github_username]["agreement"] = "none"
        else:
            people[github_username]["agreement"] = 'institution'
            people[github_username]["institution"] = acct_name

    return people


def get_orgs_file():
    orgs = _read_yaml_data_file("orgs.yaml")
    for org_data in list(orgs.values()):
        if "name" in org_data:
            orgs[org_data["name"]] = org_data
    return orgs


@memoize_timed(minutes=30)
def get_jira_info() -> dict[str, JiraServer]:
    """
    Get the dict mapping Jira nicknames to JiraServer objects.
    """
    jira_info = {}
    for key, info in _read_yaml_data_file(settings.JIRA_INFO_FILE).items():
        jira_info[key.lower()] = JiraServer(**info)
    return jira_info


class NoJiraServer(Exception):
    """Raised when there is no Jira with a given nickname."""

class NoJiraMapping(Exception):
    """Raised when the repo isn't mapped to a Jira project."""


def get_jira_server_info(jira_nick: str) -> JiraServer:
    """
    Given a Jira nickname, get the JiraServer info about it.
    """
    jira_info = get_jira_info()
    try:
        jira_server = jira_info[jira_nick.lower()]
    except KeyError as exc:
        raise NoJiraServer(f"No Jira server configured with nick {jira_nick!r}") from exc
    return jira_server


def is_internal_pull_request(pull_request: PrDict) -> bool:
    """
    Is this pull request's author internal to the PR's GitHub org?
    """
    person = _pr_author_data(pull_request)
    if person is None:
        return False

    org_name = person.get("institution")
    if org_name is None:
        return False

    org_data = get_orgs_file().get(org_name)
    if org_data is None:
        return False
    if org_data.get("internal", False):
        # This is an temporary stop-gap: the old data will work with the new
        # code so we can deploy new code and then update the data files.
        # Once the data files are updated to remove "internal", we can get rid
        # of this code.
        return True

    gh_org = pull_request["base"]["repo"]["owner"]["login"]
    if gh_org in org_data.get("internal-ghorgs", []):
        return True

    return False


# During the decoupling, it became clear that we needed to ignore pull
# requests in edX private repos, since contractors there may not have
# signed a CLA, which they don't need to do.  It's not clear how this
# logic should be generalized, but this is good for now.
PRIVATABLE_ORGS = {"edx"}

def is_private_repo_no_cla_pull_request(pull_request: PrDict) -> bool:
    """
    Is this a private edX pull request?
    """
    return (
        pull_request["base"]["repo"]["owner"]["login"] in PRIVATABLE_ORGS and
        pull_request["base"]["repo"].get("private", False)
    )


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
    author = pull_request["user"]["login"].lower()
    return people.get(author)


NO_CONTRIBUTION_ORGS = {"edx"}

def repo_refuses_contributions(pull_request: PrDict) -> bool:
    """
    Does this PR's repo accept contributions at all?

    Returns True for no contributions.

    """
    return pull_request["base"]["repo"]["owner"]["login"] in NO_CONTRIBUTION_ORGS


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


@memoize_timed(minutes=15)
def get_catalog_info(repo_fullname: str) -> Dict:
    """Get the parsed catalog-info.yaml data from a repo, or {} if missing."""
    yml = read_github_file(repo_fullname, "catalog-info.yaml", not_there="{}")
    return yaml.safe_load(yml)


@memoize_timed(minutes=60)
def get_github_user_info(username: str) -> Dict | None:
    """Get github user information"""
    resp = get_github_session().get(f"/users/{username}")
    if resp.ok:
        return resp.json()
    logger.error(f"Could not find user information for user: {username} on github")
    return None


Lifecycle = Literal["experimental", "production", "deprecated"]
RepoSpec: (str | None, Lifecycle | None, bool) = namedtuple('RepoSpec', ['owner', 'lifecycle', 'is_owner_individual'])


def get_repo_spec(repo_full_name: str) -> RepoSpec:
    """
    Get the owner of the repo from its catalog-info.yaml file.
    """
    catalog_info = get_catalog_info(repo_full_name)
    if not catalog_info:
        return RepoSpec(None, None, False)
    owner = catalog_info["spec"].get("owner", "")
    owner_type = None
    is_owner_individual = False
    if ":" in owner:
        owner_type, owner = owner.split(":")
    if owner_type == "group":
        owner = f"openedx/{owner}"
    elif owner_type == "user":
        is_owner_individual = True
    return RepoSpec(owner, catalog_info["spec"]["lifecycle"], is_owner_individual)


def projects_for_pr(pull_request: PrDict) -> Iterable[GhProject]:
    """
    Get the projects a pull request should be added to.

    Draft pull requests don't get added.

    The projects are specified in an annotation in catalog-info.yaml::

        metadata:
          annotations:
            openedx.org/add-to-projects: "openedx:23, openedx:456"

    Each entry is an org:num spec for an organization project.

    """
    if is_draft_pull_request(pull_request):
        return set()

    catalog_info = get_catalog_info(pull_request["base"]["repo"]["full_name"])
    annotations = glom(catalog_info, "metadata.annotations", default={})
    projects = annotations.get("openedx.org/add-to-projects", "")
    gh_projects = []
    if projects:
        for spec in projects.split(","):
            org, number = spec.strip().split(":")
            gh_projects.append((org, int(number)))
    return gh_projects


def jira_details_for_pr(jira_nick: str, pr: PrDict) -> tuple[str, str]:
    """
    Determine what Jira project and issuetype should be used.

    The jira mapping file looks like this::

        # Mapping from repo to Jira.
        defaults:
          type: Task
        repos:
          - name: openedx/edx-platform
            project: ARCHBOM
            type: Task
          - name: nedbat/*
            project: ARCHBOM
          - name: "*"
            project: CATCHALL
            type: OtherType

    """

    jira_info = get_jira_server_info(jira_nick)
    mapping = yaml.safe_load(_read_github_url(jira_info.mapping))
    repo_name = pr["base"]["repo"]["full_name"]
    details = mapping.get("defaults", {})
    for repo_info in mapping.get("repos", []):
        if fnmatch.fnmatch(repo_name, repo_info["name"]):
            details.update(repo_info)
            break

    try:
        return details["project"], details["type"]
    except KeyError as exc:
        raise NoJiraMapping(f"No Jira project mapping for {repo_name!r}: {details=}") from exc
