# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from .....lib.exceptions import NotFoundError
from .....lib.github.decorators import inject_gh
from .....lib.github.utils import get_repo_contents
from ..utils import create_pull_request_comment
from .urls import CLA_URL, CONTRIBUTING_URL, PROCESS_URL

AUTHORS = 'AUTHORS'

OSPR_MSG = """\
Thanks for the pull request, @{{contributor}}! I've created [{{ospr_label}}]({{ospr_url}}) to keep track of it in JIRA. JIRA is a place for product owners to prioritize feature reviews by the engineering development teams.

Feel free to add as much of the following information to the ticket:

* supporting documentation
* edx-code email threads
* timeline information ("this must be merged by XX date", and why that is)
* partner information ("this is a course on edx.org")
* any other information that can help Product understand the context for the PR

All technical communication about the code itself will still be done via the GitHub pull request interface. As a reminder, [our process documentation is here]({}).

""".format(PROCESS_URL)

CLA_MSG = (
    "We can't start reviewing your pull request until you've submitted a "
    "[signed contributor agreement]({}) or indicated your institutional "
    "affiliation."
).format(CLA_URL)

AUTHORS_MSG = (
    "If you like, you can add yourself to the [{}]({{authors_url}}) file "
    "for this repo, though that isn't required."
).format(AUTHORS)

CONTRIBUTING_MSG = (
    "Please see the [CONTRIBUTING]({}) file for more information."
).format(CONTRIBUTING_URL)


@inject_gh
def create_ospr_comment(gh, event, ospr_info):
    comment = _create_comment(event, ospr_info)
    create_pull_request_comment(gh, event, comment)


def _create_comment(gh, event, ospr_info):
    context = dict(
        contributor=event.event_resource['user']['login'],
        ospr_label=ospr_info['label'],
        ospr_url=ospr_info['url'],
    )
    comment = OSPR_MSG.format(context)
    additions = _apply_additional_messages(gh, event)
    comment += ' '.join(additions)

    return comment


def _apply_additional_messages(gh, event):
    additions = []

    if not event.is_by_current_user:
        additions.append(CLA_MSG)

    is_in_authors = True
    no_authors_file = False
    try:
        is_in_authors = _is_in_authors(gh, event)
    except NotFoundError:
        no_authors_file = True

    if not is_in_authors:
        author_msg = _create_author_message(event)
        additions.append(author_msg)

    condition = (
        not (event.is_by_current_user or is_in_authors)
        or no_authors_file
    )
    if condition:
        additions.append(CONTRIBUTING_MSG)

    return additions


def _create_author_message(event):
    repo_url = event.event_resource['head']['repo']['html_url']
    ref = event.event_resource['head']['ref']
    context = dict(
        authors_url="{}/blob/{}/{}".format(repo_url, ref, AUTHORS)
    )
    return AUTHORS_MSG.format(context)


def _is_in_authors(gh, event):
    repo_name = event.event_resource['head']['repo']['full_name']
    authors = get_repo_contents(gh, repo_name, 'AUTHORS')

    if not authors:
        raise NotFoundError

    login = event.event_resource['user']['login']
    all_ids = _get_all_ids(gh, login, event)
    all_ids = [id for id in all_ids if id in authors]
    return bool(all_ids)


def _get_all_ids(gh, login, event):
    ids = [login]
    gh_user = gh.user(login)
    ids.extend([gh_user.name, gh_user.email])
    if event.is_by_known_user:
        user = event.openedx_user
        ids.extend([user.name] + user.all_emails)
    return filter(None, ids)
