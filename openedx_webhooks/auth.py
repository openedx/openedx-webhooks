"""
Create authenticated sessions for access to GitHub and Jira.
"""

import requests
from urlobject import URLObject

from openedx_webhooks.settings import settings


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


def get_jira_session():
    """
    Get the Jira session to use, in an easily test-patchable way.
    """
    session = BaseUrlSession(base_url=settings.JIRA_SERVER)
    session.auth = (settings.JIRA_USER_EMAIL, settings.JIRA_USER_TOKEN)
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
