#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Update or create webhooks according to spec.
"""
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

import json
from collections import defaultdict

import click

from openedx_webhooks.lib.github.utils import update_or_create_webhook

click.disable_unicode_literals_warning = True


class Results(object):
    def __init__(self):
        self.created = defaultdict(list)
        self.edited = defaultdict(list)
        self.deleted = defaultdict(list)
        self.failed = defaultdict(list)

    def add(self, repo, conf, hook, created, deleted):
        url = conf['config']['url']
        if hook:
            if created:
                self.created[url].append(repo)
            else:
                self.edited[url].append(repo)
        else:
            self.failed[url].append(repo)
        if deleted:
            self.deleted[url].append(repo)


def install_hook(repo, conf, dry_run, verbose):
    """
    Install a webhook into specified repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        conf (dict): See description of "hooks" in cli docstring
        dry_run (bool): Don't really edit the hook

    Returns:
        hook Optional[github3.repos.hook.Hook]: `None` if the install fails
    """
    active = conf.get('active', True)
    config = conf['config']
    events = conf['events']
    url = config['url']

    try:
        hook, created, deleted = update_or_create_webhook(
            repo, config, events, active, dry_run
        )
        if verbose or dry_run:
            if created:
                msg = "{} webhook created: {}".format(repo, url)
            else:
                msg = "{} webhook({}) updated: {}".format(repo, hook.id, url)
            click.echo(msg)

            for d in deleted:
                msg = "{} webhook({}) deleted: {}".format(repo, d.id, url)
                click.echo(msg)
        return hook, created, deleted
    except:
        if verbose:
            msg = "**FAILED** {} ({})".format(repo, url)
            click.echo(msg)
        return None, False, []


def print_results(results_dict, header):
    for url, repos in results_dict.items():
        click.echo(header.format(url, len(repos)))
        for repo in repos:
            click.echo("* " + repo)


@click.command()
@click.argument('config-json', type=click.File('rb'))
@click.option('--dry-run', is_flag=True)
@click.option('-v', '--verbose', is_flag=True)
def cli(config_json, dry_run, verbose):
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

    results = Results()

    if dry_run:
        click.echo(
            '**Dry run only** The following actions would have been performed:'
        )

    for repo in repos:
        for conf in hook_confs:
            hook, created, deleted = install_hook(repo, conf, dry_run, verbose)
            results.add(repo, conf, hook, created, deleted)

    print_results(
        results.created, "{} webhook created for the following {} repos:"
    )

    print_results(
        results.edited, "{} webhook edited for the following {} repos:"
    )

    print_results(
        results.deleted, "{} webhook deleted for the following {} repos:"
    )

    print_results(
        results.failed,
        "{} webhook failed to install for the following {} repos:"
    )


if __name__ == '__main__':
    cli()
