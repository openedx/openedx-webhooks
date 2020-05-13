#!/usr/bin/env python

import arrow
import click
from functools import lru_cache
from jira import JIRAError

from openedx_webhooks.jira.tasks import update_latest_github_activity
from openedx_webhooks.lib.edx_repo_tools_data.utils import get_people
from openedx_webhooks.lib.exceptions import NotFoundError
from openedx_webhooks.lib.github.client import github_client as gh
from openedx_webhooks.lib.jira.client import jira_client as jira
from openedx_webhooks.lib.jira.utils import make_fields_lookup

click.disable_unicode_literals_warning = True

EXCLUDED = ['Merged', 'Rejected']


@lru_cache()
def _get_people(gh):
    return get_people(gh)


def _is_edx_user(gh, login):
    try:
        is_edx_user = _get_people(gh).get(login).is_edx_user
    except NotFoundError:
        is_edx_user = False
    return is_edx_user


def _get_github_fields(jira, field_names):
    fields = make_fields_lookup(jira, field_names)
    for f in field_names:
        yield fields[f]


def _get_github_values(jira, issue):
    field_names = ['Repo', 'PR Number']
    for k in _get_github_fields(jira, field_names):
        yield getattr(issue.fields, k)


def _get_last_pr_commit_info(gh, pull_request):
    commit = list(pull_request.iter_commits())[-1]
    login = commit.committer_as_User().login

    info = {
        'description': 'pull_request: synchronize',
        'login': login,
        'updated_at': arrow.get(
            commit.to_json()['commit']['committer']['date']
        ).datetime,
        'is_edx_user': _is_edx_user(gh, login),
    }
    return info


def _get_last_pr_activity_info(gh, pull_request):
    activities = (
        list(pull_request.iter_comments()) +
        list(pull_request.iter_issue_comments())
    )
    last_activity = sorted(activities, key=lambda x: x.updated_at)[-1]
    login = last_activity.user.login

    info = {
        'description': 'issue_comment: created',
        'login': last_activity.user.login,
        'updated_at': last_activity.updated_at,
        'is_edx_user': _is_edx_user(gh, login),
    }

    response = max(
        _get_last_pr_commit_info(gh, pull_request),
        info,
        key=lambda x: x['updated_at']
    )
    return response


def retrieve_issues_by_keys(jira, issue_keys):
    """
    Retrieve issues from JIRA.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session
        issue_keys (List[str]): List of JIRA issue keys

    Returns:
        List[jira.resources.Issue]
    """
    issues = []
    for k in issue_keys:
        try:
            issues.append(jira.issue(k))
        except JIRAError:
            raise Exception('"{}" is not a valid issue.'.format(k))
    return issues


def retrieve_osprs(jira):
    """
    Retrieve active OSPRs.

    Arguments:
        jira (jira.JIRA): An authenticated JIRA API client session

    Returns:
        List[jira.resources.Issue]
    """
    issues = []
    start_at = 0
    statuses = ','.join(['"{}"'.format(s) for s in EXCLUDED])
    jql = "project=OSPR AND status NOT IN ({})".format(statuses)
    results = jira.search_issues(jql)

    while results:
        issues.extend(results)
        start_at += len(issues)
        results = jira.search_issues(jql, startAt=start_at)
    return issues


def get_update_info(gh, jira, issue):
    """
    Update JIRA issue with latest GitHub activity.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        jira (jira.JIRA): An authenticated JIRA API client session
        issue (jira.resources.Issue)
    """
    repo_name, pr_number = _get_github_values(jira, issue)
    pr = gh.repository(*repo_name.split('/')).pull_request(pr_number)
    return _get_last_pr_activity_info(gh, pr)


@click.command()
@click.option(
    '--issue', multiple=True, type=int,
    help='OSPR issue number, leave out `OSPR-` prefix.'
)
@click.option('--dry-run', is_flag=True)
def cli(issue, dry_run):
    """
    Update JIRA OSPRs with latest GitHub activity.

    If you don't specify specific JIRA issues, all OSPRs which are not
    merged or rejected will be processed. You can specify multiple issues
    by using the `--issue` option multiple times.
    """
    if issue:
        issue_keys = ["OSPR-{}".format(i) for i in issue]
        issues = retrieve_issues_by_keys(jira, issue_keys)
    else:
        issues = retrieve_osprs(jira)

    if dry_run:
        click.echo(
            '**Dry run only** The following actions would have been performed:'
        )
    click.echo("Updating {} JIRA issues:".format(len(issues)))
    for issue in issues:
        update_info = get_update_info(gh, jira, issue)
        click.echo("Updating {} with {}.".format(issue.key, update_info))
        if not dry_run:
            update_latest_github_activity(jira, issue.id, **update_info)


if __name__ == '__main__':
    cli()
