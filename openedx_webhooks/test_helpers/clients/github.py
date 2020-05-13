import pytest
from github3 import GitHub


@pytest.fixture
def github_client(mocker):
    return mocker.Mock(spec_set=GitHub)
