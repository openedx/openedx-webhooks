import base64

from openedx_webhooks.auth import get_github_session, get_jira_session
from openedx_webhooks.settings import TestSettings


def test_get_github_session(fake_github):
    session = get_github_session()
    response = session.get("/user")
    headers = response.request.headers
    assert headers["Authorization"] == f"token {TestSettings.GITHUB_PERSONAL_TOKEN}"
    assert response.url == "https://api.github.com/user"


def test_get_jira_session(fake_jira):
    session = get_jira_session()
    response = session.get("/rest/api/2/field")
    headers = response.request.headers
    user_token = f"{TestSettings.JIRA_USER_EMAIL}:{TestSettings.JIRA_USER_TOKEN}"
    basic_auth = base64.b64encode(user_token.encode()).decode()
    assert headers["Authorization"] == f"Basic {basic_auth}"
    assert response.url == f"{TestSettings.JIRA_SERVER}/rest/api/2/field"
