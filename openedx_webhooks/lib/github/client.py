"""
GitHub client instance.
"""

from github3 import GitHub

from openedx_webhooks.utils import environ_get

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
except ImportError:  # pragma: no cover
    pass

def get_authenticated_gh_client() -> GitHub:
    """
    Create an authenticated GitHub client.
    """
    return GitHub(token=environ_get('GITHUB_PERSONAL_TOKEN'))
