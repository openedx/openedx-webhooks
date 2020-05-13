from collections import namedtuple

import pytest

from openedx_webhooks.lib.github.utils import repo_name

Owner = namedtuple('Owner', ['login'])
Repo = namedtuple('Repo', ['owner', 'name'])


@pytest.fixture
def repo():
    owner = Owner(login='owner')
    repo = Repo(owner=owner, name='repo')
    return repo


def test_repo_name(repo):
    expected = 'owner/repo'
    assert repo_name(repo) == expected
