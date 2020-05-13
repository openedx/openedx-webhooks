"""
Update OSPR with link to survey.
"""

import arrow

from ....lib.github.decorators import inject_gh
from ....lib.jira.decorators import inject_jira
from ...models import GithubEvent
from .utils import find_issues_for_pull_request

EVENT_TYPES = (
    'pull_request',
)

SURVEY_URL = (
    'https://docs.google.com/forms/d/e'
    '/1FAIpQLSceJOyGJ6JOzfy6lyR3T7EW_71OWUnNQXp68Fymsk3MkNoSDg/viewform'
    '?usp=pp_url'
    '&entry.1671973413={repo_full_name}'
    '&entry.867055334={pull_request_url}'
    '&entry.1484655318={contributor_url}'
    '&entry.752974735={created_at}'
    '&entry.1917517419={closed_at}'
    '&entry.2133058324={is_merged}'
)

MERGED_MSG = """\
@{{contributor}} 🎉 Your pull request was merged!

Please take a moment to [answer a two question survey]({}) so we can improve your experience in the future.
""".format(SURVEY_URL)  # noqa

NOT_MERGED_MSG = """\
@{{contributor}} Even though your pull request wasn’t merged, please take a moment to [answer a two question survey]({}) so we can improve your experience in the future.
""".format(SURVEY_URL)  # noqa


@inject_jira
@inject_gh
def run(gh, jira, event_type, raw_event):
    """
    Update PR with link to survey.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        jira (jira.JIRA): An authenticated JIRA API client session
        event_type (str): GitHub event type
        raw_event (Dict[str, Any]): The parsed event payload
    """
    event = GithubEvent(gh, event_type, raw_event)
    has_jira_issue = bool(find_issues_for_pull_request(jira, event.html_url))

    if event.action != 'closed' or not has_jira_issue:
        return

    msg = _create_pr_comment(event)
    pr_number = event.event_resource['number']
    issue = gh.issue(event.repo_owner_login, event.repo_name, pr_number)

    issue.create_comment(msg)


def _format_datetime(datetime_string):
    date_string = arrow.get(datetime_string).format('YYYY-MM-DD+HH:mm')
    return date_string


def _create_pr_comment(event):
    is_merged = event.event_resource['merged']
    comment = MERGED_MSG if is_merged else NOT_MERGED_MSG
    context = dict(
        repo_full_name=event.repo_full_name,
        pull_request_url=event.event_resource['html_url'],
        contributor=event.event_resource['user']['login'],
        contributor_url=event.event_resource['user']['html_url'],
        created_at=_format_datetime(event.event_resource['created_at']),
        closed_at=_format_datetime(event.event_resource['closed_at']),
        is_merged='Yes' if is_merged else 'No'
    )

    return comment.format(**context)
