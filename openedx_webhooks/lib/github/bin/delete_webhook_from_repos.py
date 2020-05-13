#!/usr/bin/env python
"""
Delete specified webhook from all repos.
"""

import click

from openedx_webhooks.lib.github.utils import (
    delete_hooks, get_repos_with_webhook, get_webhooks, repo_name
)

click.disable_unicode_literals_warning = True


@click.command()
@click.argument('payload-url')
def cli(payload_url):
    """
    Delete specified webhook from all repos.

    Note that you must set the environment variable $GITHUB_PERSONAL_TOKEN
    to a valid token that you create in GitHub.
    """
    repos = get_repos_with_webhook(payload_url)

    for repo in repos:
        hooks = list(get_webhooks(repo, payload_url))
        click.echo("Deleteing {} hook(s) from {}...".format(
            len(hooks), repo_name(repo)
        ))
        delete_hooks(repo, hooks)


if __name__ == '__main__':
    cli()
