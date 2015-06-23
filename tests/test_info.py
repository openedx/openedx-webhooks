"""
Tests of the functions in info.py
"""

import unittest

import mock

from openedx_webhooks.info import get_orgs, is_internal_pull_request
import openedx_webhooks.info


# This is the data the tests use, instead of the real yaml files in repo-tools.
TEST_YAML = {
    "orgs.yaml":
        """
        # Org data
        edX:
            committer: true
        HourlyDudes:
            contractor: true
        CommitterSoft:
            committer: true
        """,

    "people.yaml":
        """
        # People data
        edx_gal:
            # A person who works for edX now.
            agreement: institution
            institution: edX

        ex_edx_dude:
            # A person who used to work for edX.
            agreement: institution
            institution: edX
            expires_on: 2015-01-01

        hourly_worker:
            agreement: institution
            institution: HourlyDudes

        left_but_still_a_fan:
            agreement: individual
            before:
                2015-01-01:
                    agreement: institution
                    institution: edX

        external_committer:
            agreement: individual
            committer: true

        external_committer_at_org:
            agreement: institution
            institution: HourlyDudes
            committer: true
        """,
}



class BaseTestCase(unittest.TestCase):
    def fake_read_repotools_file(self, filename):
        return TEST_YAML[filename]

    def setUp(self):
        super(BaseTestCase, self).setUp()
        fake_read = mock.patch(
            "openedx_webhooks.info._read_repotools_file",
            self.fake_read_repotools_file
        )
        fake_read.start()
        self.addCleanup(fake_read.stop)


class TestGetOrg(BaseTestCase):

    def test_committer_orgs(self):
        self.assertEqual(get_orgs("committer"), set(["edX", "CommitterSoft"]))

    def test_contractor_orgs(self):
        self.assertEqual(get_orgs("contractor"), set(["HourlyDudes"]))


class TestPullRequestCategories(BaseTestCase):

    def assert_is_internal(self, user, created_at="20150623T110400", is_internal=True):
        pull_request = {
            "user": {
                "login": user,
            },
            "created_at": created_at,
        }
        actual_internal = is_internal_pull_request(pull_request)
        self.assertEqual(actual_internal, is_internal)

    def test_edx_employee(self):
        self.assert_is_internal(user="edx_gal")

    def test_fired_edx_employee(self):
        self.assert_is_internal(user="ex_edx_dude", is_internal=False)
        self.assert_is_internal(user="ex_edx_dude", created_at="20140616T123400", is_internal=True)

    def test_never_heard_of_you(self):
        self.assert_is_internal(user="some_random_guy", is_internal=False)

    def test_hourly_worker(self):
        self.assert_is_internal(user="hourly_worker", is_internal=False)

    def test_left_but_still_a_fan(self):
        self.assert_is_internal(user="left_but_still_a_fan", is_internal=False)
        # Note: openedx_webhooks doesn't understand the "before" keys.

    def test_committers(self):
        self.assert_is_internal(user="external_committer")
        self.assert_is_internal(user="external_committer_at_org")
