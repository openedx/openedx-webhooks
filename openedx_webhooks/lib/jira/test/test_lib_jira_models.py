import pytest

from openedx_webhooks.lib.exceptions import NotFoundError


class TestJiraFields:
    def test_get_by_name(self, fields):
        field = fields.get_by_name('test01')
        assert field.name == 'test01'
        assert field.first is True

    def test_get_by_name_no_result(self, fields):
        with pytest.raises(NotFoundError):
            fields.get_by_name('random')


class TestJiraField:
    def test_getattr(self, field):
        assert field.name == 'test01'
        assert field.first is True

    def test_getattr_error(self, field):
        with pytest.raises(AttributeError):
            field.nope
