import datetime

import pytest

from openedx_webhooks.lib.edx_repo_tools_data.models import People, Person


# Data
@pytest.fixture
def active_data():
    data = {'active-person': {
        'agreement': 'individual',
    }}
    return data


@pytest.fixture
def active_edx_data():
    data = {'active-edx-person': {
        'agreement': 'institution',
        'institution': 'edX',
    }}
    return data


@pytest.fixture
def expired_data():
    data = {'expired-person': {
        'agreement': 'institution',
        'expires_on': datetime.date(2012, 10, 1),
        'institution': 'edX',
    }}
    return data


@pytest.fixture
def robot_data():
    data = {'robot': {
        'agreement': 'individual',
        'is_robot': True,
    }}
    return data


@pytest.fixture
def before():
    data = {
        datetime.date(2016, 1, 9): {},
        datetime.date(2016, 7, 29): {},
        datetime.date(2016, 8, 8): {},
    }
    return data


# Person
@pytest.fixture
def active_person(active_data):
    k, v = list(active_data.items())[0]
    return Person(k, v)


@pytest.fixture
def active_edx_person(active_edx_data):
    k, v = list(active_edx_data.items())[0]
    return Person(k, v)


@pytest.fixture
def active_non_edx_person():
    person = Person('active-person', {
        'agreement': 'institution',
        'institution': 'Shield',
    })
    return person


@pytest.fixture
def expired_person(expired_data):
    k, v = list(expired_data.items())[0]
    return Person(k, v)


@pytest.fixture
def before_expired_person(before):
    person = Person('expired-before-person', {
        'agreement': 'none',
        'before': before,
    })
    return person


@pytest.fixture
def robot(robot_data):
    k, v = list(robot_data.items())[0]
    return Person(k, v)


# People
@pytest.fixture
def people(active_data, active_edx_data, expired_data, robot_data):
    data = {}
    for d in (active_data, active_edx_data, expired_data, robot_data):
        data.update(d)
    return People(data)
