import pytest

from openedx_webhooks.lib.jira.models import JiraField, JiraFields


@pytest.fixture
def field_datum():
    return {'name': 'test01', 'first': True, 'id': 'id_test01'}


@pytest.fixture
def fields_data(field_datum):
    data = [
        field_datum,
        {'name': 'test02', 'id': 'id_test02'},
        {'name': 'test01', 'first': False},
    ]
    return data


@pytest.fixture
def field(field_datum):
    return JiraField(field_datum)


@pytest.fixture
def fields(fields_data):
    return JiraFields(fields_data)
