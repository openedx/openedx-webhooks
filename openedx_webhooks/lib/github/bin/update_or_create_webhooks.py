#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Update or create webhooks according to spec.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import json

import click
from openedx_webhooks.lib.github.utils import update_or_create_webhook

click.disable_unicode_literals_warning = True


@click.command()
@click.argument('config-json', type=click.File('rb'))
@click.option('--dry-run', is_flag=True)
def cli(config_json, dry_run):
    """
    Update or create webhooks according to spec.

    Using a configuration file, create or update webhooks in specified repos.

    \b
    {
      "repos": [
        "owner1/repo1",
        ...
      ],
      "hooks": [
        {
          "config": {
            "url": "payload_url",
            "insecure_ssl": false, # Optional
            "secret": "secret", # Optional
            "content_type": "json" # Optional
          },
          "events": [
            "pull_request",
            ...
          ]
        },
        ...
      ]
    }

    See <https://developer.github.com/v3/repos/hooks/#create-a-hook> for
    more information about the `config`.

    Note that you must set the environment variable $GITHUB_PERSONAL_TOKEN
    to a valid token that you create in GitHub.
    """
    raw = json.load(config_json)
    repos = raw['repos']
    hook_confs = raw['hooks']

    if dry_run:
        click.echo(
            '**Dry run only** The following actions would have been performed:'
        )

    for repo in repos:
        for conf in hook_confs:
            active = conf.get('active', True)
            config = conf['config']
            events = conf['events']
            url = config['url']

            hook, created, deleted = update_or_create_webhook(
                repo, config, events, active, dry_run
            )
            if created:
                msg = "{} webhook created: {}".format(repo, url)
            else:
                msg = "{} webhook({}) updated: {}".format(repo, hook.id, url)
            click.echo(msg)

            for d in deleted:
                msg = "{} webhook({}) deleted: {}".format(repo, d.id, url)
                click.echo(msg)


if __name__ == '__main__':
    cli()
