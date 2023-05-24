"""
Operations on GitHub data.
"""

from typing import Any, Dict

from openedx_webhooks.auth import get_github_session
from openedx_webhooks.info import get_labels_file
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import (
    log_check_response,
    memoize_timed,
    paginated_get,
)


def get_repo_labels(repo: str) -> Dict[str, Dict[str, Any]]:
    """Get a dict mapping label names to full label info."""
    url = f"/repos/{repo}/labels"
    repo_labels = {lbl["name"]: lbl for lbl in paginated_get(url, session=get_github_session())}
    return repo_labels


@memoize_timed(minutes=15)
def synchronize_labels(repo: str) -> None:
    """Ensure the labels in `repo` match the specs in openedx-webhooks-data/labels.yaml"""

    url = f"/repos/{repo}/labels"
    repo_labels = get_repo_labels(repo)
    desired_labels = get_labels_file()
    for name, label_data in desired_labels.items():
        if label_data.get("delete", False):
            # A label that should not exist in the repo.
            if name in repo_labels:
                logger.info(f"Deleting label {name} from {repo}")
                resp = get_github_session().delete(f"{url}/{name}")
                log_check_response(resp)
        else:
            # A label that should exist in the repo.
            label_data["name"] = name
            if name in repo_labels:
                repo_label = repo_labels[name]
                color_differs = repo_label["color"] != label_data["color"]
                repo_desc = repo_label.get("description", "") or ""
                desired_desc = label_data.get("description", "") or ""
                desc_differs = repo_desc != desired_desc
                if color_differs or desc_differs:
                    logger.info(f"Updating label {name} in {repo}")
                    resp = get_github_session().patch(f"{url}/{name}", json=label_data)
                    log_check_response(resp)
            else:
                logger.info(f"Adding label {name} to {repo}")
                resp = get_github_session().post(url, json=label_data)
                log_check_response(resp)
