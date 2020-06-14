"""Tests of task/github.py:synchronize_labels."""

import urllib.parse

from openedx_webhooks.tasks.github import (
    synchronize_labels,
)


def test_no_labels_yet(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 2
    assert labels_post.request_history[0].json() == {"color": "bfe5bf", "name": "basic label"}
    assert labels_post.request_history[1].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_no_sync_needed(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 0
    assert len(labels_delete.request_history) == 0

def test_one_is_missing(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 1
    assert labels_post.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_color_is_wrong(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "ff0000", "description": "This stuff is important."},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 1
    assert labels_post.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_description_is_wrong(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 1
    assert labels_post.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 0

def test_delete_unneeded(reqctx, mock_github):
    repo = "edx/some-repo"
    labels = [
        {"name": "something", "color": "123456", "description": "Huh?"},
        {"name": "important-label", "color": "00ff00", "description": "not sure"},
        {"name": "basic label", "color": "bfe5bf"},
        {"name": "not needed label", "color": "ff0000"},
    ]
    mock_github.mock_labels(repo, labels)
    labels_post = mock_github.labels_post(repo)
    labels_delete = mock_github.labels_delete(repo)

    with reqctx:
        synchronize_labels(repo)

    assert len(labels_post.request_history) == 1
    assert labels_post.request_history[0].json() == {
        "color": "00ff00",
        "description": "This stuff is important.",
        "name": "important-label",
    }
    assert len(labels_delete.request_history) == 1
    assert urllib.parse.unquote(labels_delete.request_history[0].path.rpartition("/")[-1]) == "not needed label"
