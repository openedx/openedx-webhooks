import pytest


@pytest.fixture(autouse=True)
def patch_get_people(people_data, mocker):
    mocker.patch(
        'openedx_webhooks.github.models.get_people_file', return_value=people_data
    )
