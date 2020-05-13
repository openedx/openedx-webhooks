import pytest
from jira import JIRA


@pytest.fixture
def jira_client(mocker):
    jira = mocker.Mock(spec_set=JIRA)
    return jira
