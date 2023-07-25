"""
Operations on GitHub data.
"""

from typing import Any, Dict

from openedx_webhooks.auth import get_github_session
from openedx_webhooks.utils import paginated_get


def get_repo_labels(repo: str) -> Dict[str, Dict[str, Any]]:
    """Get a dict mapping label names to full label info."""
    url = f"/repos/{repo}/labels"
    repo_labels = {lbl["name"]: lbl for lbl in paginated_get(url, session=get_github_session())}
    return repo_labels
