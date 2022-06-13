"""Tests of task/github.py:synchronize_labels."""

import pytest

from openedx_webhooks.tasks.github_work import synchronize_labels

from .fake_github import Label


# These tests should run when we want to test flaky GitHub behavior.
pytestmark = pytest.mark.flaky_github


DESIRED_LABELS = [
    Label(name='basic label', color='bfe5bf', description=None),
    Label(name='important-label', color='00ff00', description='This stuff is important.'),
    Label(name='something', color='123456', description='Huh?'),
]

def test_no_labels_yet(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert len(fake_github.requests_made(method="POST")) == 2

def test_no_sync_needed(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert fake_github.requests_made(method="POST") == []
    assert fake_github.requests_made(method="PATCH") == []
    assert fake_github.requests_made(method="DELETE") == []


def test_one_is_missing(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "basic label", "color": "bfe5bf"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert len(fake_github.requests_made(method="POST")) == 1


def test_color_is_wrong(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "ff0000", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert len(fake_github.requests_made(method="POST")) == 0
    assert len(fake_github.requests_made(method="PATCH")) == 1


def test_description_is_wrong(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert len(fake_github.requests_made(method="POST")) == 0
    assert len(fake_github.requests_made(method="PATCH")) == 1


def test_delete_unneeded(fake_github):
    repo = fake_github.make_repo("edx", "some-repo")
    repo.set_labels([
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
        {"name": "not needed label", "color": "ff0000"},
    ])

    synchronize_labels("edx/some-repo")

    assert repo.get_labels() == DESIRED_LABELS
    assert len(fake_github.requests_made(method="POST")) == 0
    assert len(fake_github.requests_made(method="PATCH")) == 1
    assert len(fake_github.requests_made(method="DELETE")) == 1
