import base64

from openedx_webhooks.auth import get_github_session, get_jira_session

from . import settings as test_settings


def test_get_github_session(fake_github):
    session = get_github_session()
    response = session.get("/user")
    headers = response.request.headers
    assert headers["Authorization"] == f"token {test_settings.GITHUB_PERSONAL_TOKEN}"
    assert response.url == "https://api.github.com/user"


def test_get_jira_session(fake_jira):
    session = get_jira_session()
    response = session.get("/rest/api/2/field")
    headers = response.request.headers
    user_token = f"{test_settings.JIRA_USER_EMAIL}:{test_settings.JIRA_USER_TOKEN}"
    basic_auth = base64.b64encode(user_token.encode()).decode()
    assert headers["Authorization"] == f"Basic {basic_auth}"
    assert response.url == f"{test_settings.JIRA_SERVER}/rest/api/2/field"
