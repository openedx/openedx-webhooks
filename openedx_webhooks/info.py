"""
Get information about people, repos, orgs, pull requests, etc.
"""
import csv
import datetime
import logging
import re
from typing import Dict, Iterable, Optional, Tuple, Union

import yaml
from glom import glom
from iso8601 import parse_date

from openedx_webhooks import settings
from openedx_webhooks.lib.github.models import PrId
from openedx_webhooks.auth import get_github_session
from openedx_webhooks.types import GhProject, PrDict, PrCommentDict
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
    return _read_github_file("openedx/openedx-webhooks-data", filename)


def _read_github_file(repo_fullname: str, file_path: str, not_there: Optional[str] = None) -> str:
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
    github = get_github_session()
    data_file_url = _github_file_url(repo_fullname, file_path)
    logger.debug(f"Grabbing data file from: {data_file_url}")
    resp = github.get(data_file_url)
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
            institution: ""
            committer: {...},
            before: {...}
        },
        ...
    }
    """
    people_data_csv = _read_csv_data_file("salesforce-export.csv")
    people = {}

    for row in people_data_csv:
        first_name = row['First Name']
        last_name = row['Last Name']
        acct_name = row['Account Name']
        github_username = row['GitHub Username']

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

    people_data_yaml = _read_yaml_data_file("people.yaml")
    for p in people:        # pylint: disable=consider-using-dict-items
        # Prioritzes the csv by first updating the yaml's values with csv values
        # And then updates any missing dict fields using yaml's fields
        if p in people_data_yaml:
            people_data_yaml[p].update(people[p])
            people[p].update(people_data_yaml[p])
    return people


def get_orgs_file():
    orgs = _read_yaml_data_file("orgs.yaml")
    for org_data in list(orgs.values()):
        if "name" in org_data:
            orgs[org_data["name"]] = org_data
    return orgs

def get_person_certain_time(person: Dict, certain_time: datetime.datetime) -> Dict:
    """
    Return person data structure for a particular time

    Arguments:
        person: dict of GitHub user info from people.yaml.
        certain_time: datetime.datetime object used to determine the state of the person.

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
    author = pull_request["user"]["login"]
    if author not in people:
        # We don't know this person!
        return None

    person = people[author]
    created_at = parse_date(pull_request["created_at"]).replace(tzinfo=None)
    person = get_person_certain_time(people[author], created_at)
    return person


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


def get_jira_issue_key(pr: Union[PrId, PrDict]) -> Tuple[bool, Optional[str]]:
    """
    Find mention of a Jira issue number in bot-authored comments.

    Returns:
        on_our_jira (bool): is the Jira issue on the JIRA_SERVER?
        issue_key (str): the id of the Jira issue. Can be None if no Jira issue
            is on the pull request.
    """
    if isinstance(pr, PrDict):
        prid = PrId.from_pr_dict(pr)
    else:
        prid = pr
    for comment in get_bot_comments(prid):
        # search for the first occurrence of a JIRA ticket key in the comment body
        match = re.search(r"(https://.*?)/browse/([A-Z]{2,}-\d+)\b", comment["body"])
        if match:
            on_our_jira = (match[1] == settings.JIRA_SERVER)
            jira_key = match[2]
            return on_our_jira, jira_key
    # If there is no jira id yet, return on_our_jira==True so that we will work
    # on Jira to make new ids.
    return True, None


def jira_project_for_ospr(_pr: PrDict) -> Optional[str]:
    """
    What Jira project should be used for this external pull request?

    Returns a string or None if no Jira should be used.
    """
    if settings.JIRA_SERVER is None:
        return None
    return "OSPR"


def jira_project_for_blended(_pr: PrDict) -> Optional[str]:
    """
    What Jira project should be used for this blended pull request?

    Returns a string or None if no Jira should be used.
    """
    if settings.JIRA_SERVER is None:
        return None
    return "BLENDED"


def get_catalog_info(repo_fullname: str) -> Dict:
    """Get the parsed catalog-info.yaml data from a repo, or {} if missing."""
    yml = _read_github_file(repo_fullname, "catalog-info.yaml", not_there="{}")
    return yaml.safe_load(yml)


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
