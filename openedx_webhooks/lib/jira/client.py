"""
JIRA client instance.
"""

from jira import JIRA

from openedx_webhooks.utils import environ_get

try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv())
except ImportError:  # pragma: no cover
    pass


def get_authenticated_jira_client() -> JIRA:
    """
    Create an authenticated JIRA session
    """
    server = environ_get('JIRA_SERVER')
    basic_auth = (
        environ_get("JIRA_USER_EMAIL"),
        environ_get("JIRA_USER_TOKEN"),
    )
    jira_client = JIRA(server=server, basic_auth=basic_auth)
    return jira_client
