# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from urllib import quote_plus

from .....lib.github.decorators import inject_gh
from ..utils import create_pull_request_comment
from .urls import CREATE_OSPR_URL, JIRA_URL


CONTRACTOR_MSG = """\
Thanks for the pull request, @{{contributor}}! It looks like you're a member of a company that does contract work for edX. If you're doing this work as part of a paid contract with edX, you should talk to edX about who will review this pull request. If this work is not part of a paid contract with edX, then you should ensure that there is an OSPR issue to track this work in [JIRA]({}), so that we don't lose track of your pull request.

[Create an OSPR issue for this pull request]({}?repo={{repo}}&number={{pr_number}}).
""".format(JIRA_URL, CREATE_OSPR_URL)


@inject_gh
def create_contractor_comment(gh, event):
    comment = _create_comment(event)
    create_pull_request_comment(gh, event, comment)


def _create_comment(event):
    context = dict(
        contributor=event.event_resource['user']['login'],
        repo=quote_plus(event.repo_full_name),
        pr_number=event.event_resource['number'],
    )
    return CONTRACTOR_MSG.format(context)
