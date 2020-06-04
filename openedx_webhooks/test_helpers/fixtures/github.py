from collections import namedtuple

import pytest

Hook = namedtuple('Hook', ['name', 'config', 'active'])
Repo = namedtuple('Repo', ['hooks'])


@pytest.fixture
def hooks():
    return [
        Hook(name='web', config={'url': 'http://test.me'}, active=True),
        Hook(name='travis', config={'url': 'http://travis'}, active=True),
        Hook(name='web', config={'url': 'http://test.me'}, active=False),
        Hook(name='trello', config={'url': 'http://test.me'}, active=True),
        Hook(name='web', config={'url': 'http://test.inactive'}, active=False),
    ]


@pytest.fixture
def repo(hooks):
    return Repo(hooks=lambda: hooks)


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
