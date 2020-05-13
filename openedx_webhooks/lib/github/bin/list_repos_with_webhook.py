#!/usr/bin/env python
"""
List all repos with specified webhook payload URL.
"""

import click

from openedx_webhooks.lib.github.utils import get_repos_with_webhook, repo_name

click.disable_unicode_literals_warning = True


@click.command()
@click.argument('payload-url')
@click.option(
    '--exclude-inactive',
    is_flag=True,
    help="Include webhooks which aren't active"
)
def cli(payload_url, exclude_inactive):
    """
    List all repos with specified webhook payload URL.

    Note that you must set the environment variable $GITHUB_PERSONAL_TOKEN
    to a valid token that you create in GitHub.
    """
    repos = get_repos_with_webhook(
        payload_url, exclude_inactive=exclude_inactive
    )

    for repo in repos:
        click.echo(repo_name(repo))


if __name__ == '__main__':
    cli()
