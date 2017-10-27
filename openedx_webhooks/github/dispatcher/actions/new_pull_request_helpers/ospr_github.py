# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from .....lib.github.decorators import inject_gh
from ..utils import create_pull_request_comment
from .urls import CLA_URL, CONTRIBUTING_URL, PROCESS_URL

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
    "If you like, you can add yourself to the [AUTHORS]({authors_url}) file "
    "for this repo, though that isn't required."
)

CONTRIBUTING_MSG = (
    "Please see the [CONTRIBUTING]({}) file for more information."
).format(CONTRIBUTING_URL)


@inject_gh
def create_ospr_comment(gh, event, ospr_info):
    # TODO:
    #   * [ ] CLA clause
    #   * [ ] AUTHORS file clause
    #   * [ ] Contributing clause
    comment = _create_comment(event, ospr_info)
    create_pull_request_comment(gh, event, comment)


def _create_comment(event, ospr_info):
    context = dict(
        contributor=event.event_resource['user']['login'],
        ospr_label=ospr_info['label'],
        ospr_url=ospr_info['url'],
    )
    return OSPR_MSG.format(context)
