"""
Management of the CLA check (actually a commit status).
"""

from typing import Dict, Optional

from openedx_webhooks.auth import get_github_session
from openedx_webhooks.tasks import logger
from openedx_webhooks.types import PrDict
from openedx_webhooks.utils import log_check_response


def _get_latest_commit_for_pull_request(repo_name_full: str, number: int) -> Optional[str]:
    """
    Get the HEAD commit for a pull request.
    """
    url = f"https://api.github.com/repos/{repo_name_full}/pulls/{number}"
    response = get_github_session().get(url)
    log_check_response(response)
    data = response.json()
    sha = data['head']['sha']
    logger.debug("CLA: SHA %s", sha)
    return sha


def _get_commit_status_for_cla(url) -> Optional[Dict[str, str]]:
    """
    Send a GET request to the GitHub API to lookup the build status.

    Returns:
        a dict with context, state, description, and target_url.
    """
    logger.debug("CLA: GET %s", url)
    response = get_github_session().get(url)
    log_check_response(response)
    data = response.json()
    logger.debug("CLA: GOT %s %s", url, data)
    cla_statuses = [
        status
        for status in data
        if status['context'] == CLA_CONTEXT
    ]
    status = None
    if cla_statuses:
        cla_status = cla_statuses[-1]
        status = {
            k: v for k, v in cla_status.items()
            if k in ["context", "state", "description", "target_url"]
        }
    return status


def _update_commit_status_for_cla(url, payload):
    """
    Send a POST request to the GitHub API to update the build status
    """
    logger.debug("CLA: POST %s %s", url, payload)
    response = get_github_session().post(url, json=payload)
    log_check_response(response)
    data = response.json()
    logger.debug("CLA: POSTED %s %s", url, data)
    return data


def cla_status_on_pr(pull_request: PrDict) -> Optional[Dict[str, str]]:
    """
    Get the CLA status for a pull request.

    Returns:
        a dict with context, state, description, and target_url.
    """
    repo_name_full = pull_request['base']['repo']['full_name']
    number = pull_request['number']
    sha = _get_latest_commit_for_pull_request(repo_name_full, number)
    if not sha:
        return None
    url = f"https://api.github.com/repos/{repo_name_full}/statuses/{sha}"
    status = _get_commit_status_for_cla(url)
    return status

# A status is a dict of values. We only have a few that we use, so build them
# all here.
CLA_CONTEXT = "openedx/cla"
CLA_DETAIL_URL = (
    "https://openedx.atlassian.net/wiki/spaces/COMM/pages/941457737/" +
        "How+to+start+contributing+to+the+Open+edX+code+base"
)

CLA_STATUS_GOOD = {
    "context": CLA_CONTEXT,
    "state": "success",
    "description": "The author is authorized to contribute",
    "target_url": CLA_DETAIL_URL,
}

CLA_STATUS_BAD = {
    "context": CLA_CONTEXT,
    "state": "failure",
    "description": "We need a signed Contributor Agreement",
    "target_url": CLA_DETAIL_URL,
}

CLA_STATUS_BOT = {
    "context": CLA_CONTEXT,
    "state": "success",
    "description": "Bots don't need contributor agreements",
}

CLA_STATUS_PRIVATE = {
    "context": CLA_CONTEXT,
    "state": "success",
    "description": "No contributor agreement is needed in a private repo",
    "target_url": CLA_DETAIL_URL,
}

CLA_STATUS_NO_CONTRIBUTIONS = {
    "context": CLA_CONTEXT,
    "state": "failure",
    "description": "This repo does not accept outside contributions except under contract",
}


def set_cla_status_on_pr(repo_name_full: str, number: int, status: Dict[str, str]) -> bool:
    """
    Set the CLA check status on a pull request.

    Arguments:
        repo_name_full: a string like "openedx/edx-platform"
        number: the pull request number
        status:
            a dict with context, state, description, and target_url as expected
            by the GitHub API:
            https://docs.github.com/en/rest/commits/statuses#create-a-commit-status

    """
    sha = _get_latest_commit_for_pull_request(repo_name_full, number)
    logger.debug("CLA: Update status to %r for commit %r", status, sha)
    payload = {
        'context': CLA_CONTEXT,
        **status,
    }
    url = f"https://api.github.com/repos/{repo_name_full}/statuses/{sha}"
    data = _update_commit_status_for_cla(url, payload)
    return data is not None
