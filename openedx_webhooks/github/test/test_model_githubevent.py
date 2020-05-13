from openedx_webhooks.github.models import GithubEvent


def test_sender(github_client):
    expected = 'active-person'
    payload = {
        'sender': {
            'login': expected,
        },
    }
    event = GithubEvent(github_client, 'type', payload)
    assert event.openedx_user.login == expected


def test_unknown_sender(github_client):
    payload = {
        'sender': {
            'login': 'unknown',
        },
    }
    event = GithubEvent(github_client, 'type', payload)
    assert event.openedx_user is None
