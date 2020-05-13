from openedx_webhooks.lib.github.utils import repo_contains_webhook


def test_include_inactive(repo):
    result = repo_contains_webhook(repo, 'http://test.inactive')
    assert result is True


def test_no_inactive(repo):
    result = repo_contains_webhook(
        repo, 'http://test.inactive', exclude_inactive=True
    )
    assert result is False


def test_multiple_include_inactive(repo):
    result = repo_contains_webhook(repo, 'http://test.me')
    assert result is True


def test_multiple_no_inactive(repo):
    result = repo_contains_webhook(
        repo, 'http://test.me', exclude_inactive=True
    )
    assert result is True


def test_no_hook(repo):
    result = repo_contains_webhook(repo, 'http://random')
    assert result is False
