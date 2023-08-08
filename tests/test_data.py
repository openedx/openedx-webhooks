"""
Check that our test data is correctly structured.
"""

import pathlib

from repo_tools_data_schema import validate_orgs

TEST_DATA_DIR = pathlib.Path(__file__).parent / "repo_data" / "openedx" / "openedx-webhooks-data"


def test_orgs_yaml():
    validate_orgs(TEST_DATA_DIR / "orgs.yaml")
