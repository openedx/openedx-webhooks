"""
Tests of the functions in info.py
"""

import unittest

import mock

from openedx_webhooks.info import get_orgs
import openedx_webhooks.info


# This is the data the tests use, instead of the real yaml files in repo-tools.
TEST_YAML = {
    "orgs.yaml":
        """
        # Org data
        edx:
            committer: true
        HourlyDudes:
            contractor: true
        CommitterSoft:
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
        self.assertEqual(get_orgs("committer"), set(["edx", "CommitterSoft"]))

    def test_contractor_orgs(self):
        self.assertEqual(get_orgs("contractor"), set(["HourlyDudes"]))
