import pytest


@pytest.fixture
def issue_comment_payload():
    payload = {
        'action': 'edited',
        'issue': {
            'html_url': 'https://example.com/issue/1',
            'updated_at': '2016-10-24T18:53:10Z',
        },
        'sender': {
            'login': 'issue-sender',
        },
    }
    return payload
