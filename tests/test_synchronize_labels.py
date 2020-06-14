"""Tests of task/github.py:synchronize_labels."""

import urllib.parse

from openedx_webhooks.tasks.github import (
    synchronize_labels,
)


def test_no_labels_yet(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 2
    assert labels_post.request_history[0].json() == {"color": "bfe5bf", "name": "basic label"}
    assert labels_post.request_history[1].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_patch.request_history) == 0
    assert len(labels_delete.request_history) == 0

def test_no_sync_needed(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 0
    assert len(labels_patch.request_history) == 0
    assert len(labels_delete.request_history) == 0

def test_one_is_missing(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 1
    assert labels_post.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_patch.request_history) == 0
    assert len(labels_delete.request_history) == 0

def test_color_is_wrong(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "ff0000", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 0
    assert len(labels_patch.request_history) == 1
    assert end_of_path(labels_patch.request_history[0]) == "important-label"
    assert labels_patch.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_description_is_wrong(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 0
    assert len(labels_patch.request_history) == 1
    assert end_of_path(labels_patch.request_history[0]) == "important-label"
    assert labels_patch.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_delete_unneeded(reqctx, fake_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
        {"name": "not needed label", "color": "ff0000"},
    ]
    fake_github.fake_labels(repo, labels)
    labels_post = fake_github.labels_post(repo)
    labels_patch = fake_github.labels_patch(repo)
    labels_delete = fake_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 0
    assert len(labels_patch.request_history) == 1
    assert end_of_path(labels_patch.request_history[0]) == "important-label"
    assert labels_patch.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 1
    assert end_of_path(labels_delete.request_history[0]) == "not needed label"


def end_of_path(request):
    """Return the decoded last component of the path of a request."""
    return urllib.parse.unquote(request.path.rpartition("/")[-1])
