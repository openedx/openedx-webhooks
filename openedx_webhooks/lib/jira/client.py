"""
JIRA client instance.
"""

from base64 import b64decode

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
    _server = environ_get('JIRA_SERVER')
    _oauth_info = dict(
        access_token=environ_get('JIRA_ACCESS_TOKEN'),
        access_token_secret=environ_get('JIRA_ACCESS_TOKEN_SECRET'),
        consumer_key=environ_get('JIRA_OAUTH_CONSUMER_KEY'),
        key_cert=b64decode(environ_get('JIRA_OAUTH_PRIVATE_KEY')),
    )
    jira_client = JIRA(_server, oauth=_oauth_info)
    return jira_client
