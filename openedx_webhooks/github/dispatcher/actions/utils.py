"""
Utilities for GitHub webhook handler actions.
"""
from typing import Any, Dict, List, Optional

from openedx_webhooks.oauth import get_github_session
from openedx_webhooks.tasks import logger
from openedx_webhooks.types import PrDict
from openedx_webhooks.utils import log_check_response


CLA_CONTEXT = "openedx/cla"


def find_issues_for_pull_request(jira, pull_request_url):
    """
    Find corresponding JIRA issues for a given GitHub pull request.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        pull_request_url (str)

    Returns:
        jira.client.ResultList[jira.Issue]
    """
    jql = 'project=OSPR AND cf[10904]="{}"'.format(pull_request_url)
    return jira.search_issues(jql)


def _get_latest_commit_for_pull_request(repo_name_full: str, number: int) -> Optional[str]:
    """
    Lookup PR commit details and pull out the SHA of the most recent commit.
    """
    data = _get_latest_commit_for_pull_request_data(repo_name_full, number)
    commit: Dict[str, Any] = {}
    if data:
        commit = data[-1]
        sha = commit.get('sha')
    else:
        sha = None
    logger.info("CLA: SHA %s", sha)
    return sha


def _get_latest_commit_for_pull_request_data(repo_name_full: str, number: int) -> List[Dict[str, Any]]:
    """
    Lookup the commits for a pull request.
    """
    url = f"https://api.github.com/repos/{repo_name_full}/pulls/{number}/commits"
    logger.info("CLA: GET %s", url)
    response = get_github_session().get(url)
    log_check_response(response)
    data = response.json()
    logger.info("CLA: GOT %s", data)
    return data


def _get_commit_status_for_cla(url):
    """
    Send a GET request to the Github API to lookup the build status
    """
    logger.info("CLA: GET %s", url)
    response = get_github_session().get(url)
    log_check_response(response)
    data = response.json()
    logger.info("CLA: GOT %s %s", url, data)
    cla_status = [
        status
        for status in data
        if status.get('context') == CLA_CONTEXT
    ]
    state = None
    if len(cla_status) > 0:
        state = cla_status[-1].get('state')
    return state


def _update_commit_status_for_cla(url, payload):
    """
    Send a POST request to the Github API to update the build status
    """
    logger.info("CLA: POST %s %s", url, payload)
    response = get_github_session().post(url, json=payload)
    log_check_response(response)
    data = response.json()
    logger.info("CLA: PAST %s %s", url, data)
    return data


def cla_status_on_pr(pull_request: PrDict) -> Optional[str]:
    repo_name_full = pull_request['base']['repo']['full_name']
    number = pull_request['number']
    sha = _get_latest_commit_for_pull_request(repo_name_full, number)
    if not sha:
        return None
    url = f"https://api.github.com/repos/{repo_name_full}/statuses/{sha}"
    status = _get_commit_status_for_cla(url)
    return status


def set_cla_status_on_pr(repo_name_full: str, number: int, status: str) -> bool:
    sha = _get_latest_commit_for_pull_request(repo_name_full, number)
    logger.info("CLA: Update state from to '%s' for commit '%s'", status, sha)
    if status == "success":
        description = 'The author is covered by a Contributor Agreement'
    else:
        description = 'We need a signed Contributor Agreeement'
    payload = {
        'context': CLA_CONTEXT,
        'description': description,
        'state': status,
        # pylint: disable=line-too-long
        'target_url': 'https://openedx.atlassian.net/wiki/spaces/COMM/pages/941457737/How+to+start+contributing+to+the+Open+edX+code+base',
        # pylint: enable=line-too-long
    }
    url = f"https://api.github.com/repos/{repo_name_full}/statuses/{sha}"
    data = _update_commit_status_for_cla(url, payload)
    return data is not None
