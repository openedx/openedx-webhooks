"""
Create authenticated sessions for access to GitHub and Jira.
"""

import requests
from urlobject import URLObject

from openedx_webhooks import settings


class BaseUrlSession(requests.Session):
    """
    A requests Session class that applies a base URL to the requested URL.
    """
    def __init__(self, base_url):
        super().__init__()
        self.base_url = URLObject(base_url)

    def request(self, method, url, data=None, headers=None, **kwargs):
        return super().request(
            method=method,
            url=self.base_url.relative(url),
            data=data,
            headers=headers,
            **kwargs
        )


def get_jira_session(jira_nick):
    """
    Get the Jira session to use, in an easily test-patchable way.

    `jira_nick` is a nickname for one of our configured Jira servers.
    """
    # Avoid a circular import.
    from openedx_webhooks.info import get_jira_server_info

    jira_server = get_jira_server_info(jira_nick)
    session = BaseUrlSession(base_url=jira_server.server)
    session.auth = (jira_server.email, jira_server.token)
    session.trust_env = False   # prevent reading the local .netrc
    return session


def get_github_session():
    """
    Get the GitHub session to use.
    """
    session = BaseUrlSession(base_url="https://api.github.com")
    session.headers["Authorization"] = f"token {settings.GITHUB_PERSONAL_TOKEN}"
    session.trust_env = False   # prevent reading the local .netrc
    return session
