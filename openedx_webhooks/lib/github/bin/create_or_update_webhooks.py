#!/usr/bin/env python
"""
Update or create webhooks according to spec for public repos.
"""

import functools
import json
from collections import defaultdict

import click

from openedx_webhooks.lib.github.decorators import inject_gh
from openedx_webhooks.lib.github.utils import (
    create_or_update_webhooks_for_repo, get_repo
)

click.disable_unicode_literals_warning = True


@click.group()
def cli():
    """
    Create or update a webhook for all public repos within an organization or
    for a specific repo.

    Note that you must set the environment variable $GITHUB_PERSONAL_TOKEN to a
    valid token that you create in GitHub.
    """
    pass


def common_params(func):
    @click.argument('config-json', type=click.File('rb'))
    @click.option('--dry-run', is_flag=True)
    @click.option('-v', '--verbose', is_flag=True)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@cli.command()
@click.argument('organization-name', type=click.STRING)
@common_params
def org(organization_name, config_json, dry_run, verbose):
    """
    Update or create webhooks according to spec for all organizational public
    repos where the user has admin privileges.

    CONFIG_JSON is a JSON file with a list of webhook definitions:

    \b
    [
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

    See <https://developer.github.com/v3/repos/hooks/#create-a-hook> for
    more information about the `config`.
    """
    hook_confs = json.load(config_json)
    repos = _get_repos_for_org(organization_name)

    if dry_run:
        click.echo(
            '**Dry run only** The following actions would have been performed:'
        )

    results = _create_or_update_hooks(repos, hook_confs, dry_run, verbose)
    _print_all_results(results)


@cli.command()
@click.argument('repository-name', type=click.STRING)
@common_params
def repo(repository_name, config_json, dry_run, verbose):
    """
    Update or create webhooks according to spec for a specific repository in
    the form of owner/name.

    CONFIG_JSON is a JSON file with a list of webhook definitions:

    \b
    [
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

    See <https://developer.github.com/v3/repos/hooks/#create-a-hook> for
    more information about the `config`.
    """
    hook_confs = json.load(config_json)
    repo = get_repo(repository_name)

    if dry_run:
        click.echo(
            '**Dry run only** The following actions would have been performed:'
        )

    results = _create_or_update_hooks([repo], hook_confs, dry_run, verbose)
    _print_all_results(results)


@inject_gh
def _get_repos_for_org(gh, org_name):
    org = gh.organization(org_name)
    repos = org.iter_repos(type='public')

    return repos


def _create_or_update_hooks(repos, hook_confs, dry_run, verbose):
    results = Results()

    for repo in repos:
        for conf in hook_confs:
            hook, created, deleted = _install_hook(
                repo, conf, dry_run, verbose
            )
            results.add(repo, conf, hook, created, deleted)

    return results


def _install_hook(repo, conf, dry_run, verbose):
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
        hook, created, deleted = create_or_update_webhooks_for_repo(
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


def _print_all_results(results):
    _print_results(
        results.created, "{} webhook created for the following {} repos:"
    )

    _print_results(
        results.edited, "{} webhook edited for the following {} repos:"
    )

    _print_results(
        results.deleted, "{} webhook deleted for the following {} repos:"
    )

    _print_results(
        results.failed,
        "{} webhook failed to install for the following {} repos:"
    )


def _print_results(results_dict, header):
    for url, repos in results_dict.items():
        click.echo(header.format(url, len(repos)))
        for repo in repos:
            click.echo("* " + repo.full_name)


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


if __name__ == '__main__':
    cli()
