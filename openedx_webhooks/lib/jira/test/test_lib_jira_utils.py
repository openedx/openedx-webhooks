from datetime import datetime

import pytest
from pytz import timezone

from openedx_webhooks.lib.exceptions import NotFoundError
from openedx_webhooks.lib.jira.utils import (
    convert_to_jira_datetime_string, make_fields_lookup
)


@pytest.fixture
def jira_client(jira_client, fields_data):
    jira_client.fields = lambda: fields_data
    return jira_client


class TestCnvertToJiraDatetimeString():
    def test_with_tzinfo(self):
        expected = '2016-10-23T08:22:54.000-0700'
        pacific = timezone('US/Pacific')
        dt = pacific.localize(datetime(2016, 10, 23, 8, 22, 54))
        result = convert_to_jira_datetime_string(dt)
        assert result == expected

    def test_without_tzinfo(self):
        expected = '2016-10-23T08:22:54.000+0000'
        dt = datetime(2016, 10, 23, 8, 22, 54)
        result = convert_to_jira_datetime_string(dt)
        assert result == expected


class TestMakeFieldsLookup:
    def test_make_lookup(self, jira_client):
        expected = {
            'test01': 'id_test01',
            'test02': 'id_test02',
        }
        result = make_fields_lookup(jira_client, ['test01', 'test02'])
        assert result == expected

    def test_no_lookup(self, jira_client):
        with pytest.raises(NotFoundError):
            make_fields_lookup(jira_client, ['foo', 'bar'])
