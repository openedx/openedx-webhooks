"""
Confirm expected behavior of the CLA-related functionality
"""
# Disable these warnings due to how the fixtures are constructed and used.
# pylint: disable=redefined-outer-name,unused-argument
import pytest

from openedx_webhooks.github.dispatcher.actions.utils import update_commit_status_for_cla


COMMIT_SHA = 'deadbeefcafe'
PULL_REQUEST = {
    'base': {
        'repo': {
            'full_name': 'edx/openedx-webhooks-test',
        },
    },
    'number': 1,
}


@pytest.fixture
def patch_get_commit(mocker):
    """
    Force Github API lookup of pull request to return custom data
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '._get_latest_commit_for_pull_request_data'
    ), return_value=[{'sha': COMMIT_SHA,}],)


@pytest.fixture
def patch_get_commit_fail(mocker):
    """
    Force Github API lookup of pull request to fail
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '._get_latest_commit_for_pull_request_data'
    ), return_value=None)


@pytest.fixture(autouse=True)
def patch_get_status_fail(mocker):
    """
    Force Github API lookup of commit status to fail
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '._get_commit_status_for_cla'
    ), return_value=None)


@pytest.fixture
def patch_update_status(mocker):
    """
    Force Github API update of pull request to succeed
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '._update_commit_status_for_cla'
    ), return_value={})


@pytest.fixture
def patch_update_status_fail(mocker):
    """
    Force Github API update of pull request to fail
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '._update_commit_status_for_cla'
    ), return_value=None)


@pytest.fixture
def patch_pull_request_has_cla(mocker):
    """
    Force Github API to think user _has_ signed CLA
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '.pull_request_has_cla'
    ), return_value=True)


@pytest.fixture
def patch_pull_request_has_cla_false(mocker):
    """
    Force Github API to think user has _not_ signed CLA
    """
    mocker.patch((
        'openedx_webhooks.github.dispatcher.actions.utils'
        '.pull_request_has_cla'
    ), return_value=False)


class TestCla:
    """
    Confirm expected behavior of the CLA-related functionality
    """

    def test_cla_exists(
            self,
            patch_get_commit,
            patch_update_status,
            patch_pull_request_has_cla,
    ):
        """
        Check that we can mark the build as pasing with a CLA
        """
        has_changed, has_signed = update_commit_status_for_cla(PULL_REQUEST)
        assert has_changed
        assert has_signed

    def test_cla_missing(
            self,
            patch_get_commit,
            patch_update_status,
            patch_pull_request_has_cla_false,
    ):
        """
        Check that we can mark the build as failing without a CLA
        """
        has_changed, has_signed = update_commit_status_for_cla(PULL_REQUEST)
        assert has_changed
        assert not has_signed

    def test_get_commit_failure(
            self,
            patch_get_commit_fail,
            patch_pull_request_has_cla,
            patch_update_status,
    ):
        """
        Check that we can handle a failed commit lookup
        """
        has_changed, has_signed = update_commit_status_for_cla(PULL_REQUEST)
        assert not has_changed
        assert not has_signed

    def test_update_status_failure(
            self,
            patch_get_commit,
            patch_pull_request_has_cla,
            patch_update_status_fail,
    ):
        """
        Check that we can handle a failed status update
        """
        has_changed, has_signed = update_commit_status_for_cla(PULL_REQUEST)
        assert not has_changed
        assert not has_signed
