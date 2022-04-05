import pytest

from openedx_webhooks.lib.exceptions import NotFoundError
from openedx_webhooks.lib.webhooks_data.models import People

class TestGet:
    def test_get(self, people_data):
        expected = 'active-person'
        people = People(people_data)
        assert people.get(expected).login == expected

    def test_miss(self, people_data):
        people = People(people_data)
        with pytest.raises(NotFoundError):
            people.get('foo')
