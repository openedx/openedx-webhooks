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
    session = get_jira_session("test1")
    response = session.get("/rest/api/2/issue/FOO-99")
    headers = response.request.headers
    user_token = "jira-user@test1.com:asdasdasdasdasd"
    basic_auth = base64.b64encode(user_token.encode()).decode()
    assert headers["Authorization"] == f"Basic {basic_auth}"
    assert response.url == "https://test.atlassian.net/rest/api/2/issue/FOO-99"
