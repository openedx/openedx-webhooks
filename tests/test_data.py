"""
Check that our test data is correctly structured.
"""

import pathlib

from repo_tools_data_schema import validate_labels, validate_orgs, validate_people

TEST_DATA_DIR = pathlib.Path(__file__).parent / "repo_data"


def test_labels_yaml():
    validate_labels(TEST_DATA_DIR / "labels.yaml")


def test_orgs_yaml():
    validate_orgs(TEST_DATA_DIR / "orgs.yaml")


def test_people_yaml():
    validate_people(TEST_DATA_DIR / "people.yaml")
