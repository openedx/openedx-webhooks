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
    oauth_info = dict(
        consumer_key=environ_get('JIRA_OAUTH_CONSUMER_KEY'),
        key_cert=environ_get('JIRA_OAUTH_RSA_KEY'),
    )
    jira_client = JIRA(server, oauth=oauth_info)
    return jira_client
