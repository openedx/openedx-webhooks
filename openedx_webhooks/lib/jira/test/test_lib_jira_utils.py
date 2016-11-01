# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime

from jira import JIRA
from pytz import timezone
import pytest

from openedx_webhooks.lib.exceptions import NotFoundError
from openedx_webhooks.lib.jira.utils import (
    convert_to_jira_datetime_string, make_fields_lookup
)


@pytest.fixture
def jira(fields_data, mocker):
    jira = mocker.Mock(spec_set=JIRA)
    jira.fields = lambda: fields_data
    return jira


class TestCnvertToJiraDatetimeString():
    def test_with_tzinfo(self):
        expected = '2016-10-23T08:22:54.000-0700'
        pacific = timezone('US/Pacific')
        dt = pacific.localize(datetime(2016, 10, 23, 8, 22, 54))
        result = convert_to_jira_datetime_string(dt)
        assert result == expected

    def test_without_tzinfo(self):
        expected = '2016-10-23T08:22:54.000-0000'
        dt = datetime(2016, 10, 23, 8, 22, 54)
        result = convert_to_jira_datetime_string(dt)
        assert result == expected


class TestMakeFieldsLookup:
    def test_make_lookup(self, jira):
        expected = {
            'test01': 'id_test01',
            'test02': 'id_test02',
        }
        result = make_fields_lookup(jira, ['test01', 'test02'])
        assert result == expected

    def test_no_lookup(self, jira):
        with pytest.raises(NotFoundError):
            make_fields_lookup(jira, ['foo', 'bar'])
