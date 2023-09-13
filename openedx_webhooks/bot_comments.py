"""
The bot makes comments on pull requests. This is stuff needed to do it well.
"""

import binascii
import json
import re

from enum import Enum, auto
from typing import Dict, Optional

import arrow
from flask import render_template

from openedx_webhooks import settings
from openedx_webhooks.info import (
    is_draft_pull_request,
    pull_request_has_cla,
)
from openedx_webhooks.types import JiraDict, PrDict
from openedx_webhooks.utils import get_jira_custom_fields


class BotComment(Enum):
    """
    Comments the bot can leave on pull requests.
    """
    WELCOME = auto()
    WELCOME_CLOSED = auto()
    NEED_CLA = auto()
    BLENDED = auto()
    END_OF_WIP = auto()
    SURVEY = auto()
    NO_CONTRIBUTIONS = auto()


BOT_COMMENT_INDICATORS = {
    BotComment.WELCOME: [
        "<!-- comment:external_pr -->",
        "Feel free to add as much of the following information to the ticket",
    ],
    BotComment.WELCOME_CLOSED: [
        "<!-- comment:welcome_closed -->",
    ],
    BotComment.NEED_CLA: [
        "<!-- comment:no_cla -->",
        "We can't start reviewing your pull request until you've submitted",
    ],
    BotComment.BLENDED: [
        "<!-- comment:welcome-blended -->",
    ],
    BotComment.END_OF_WIP: [
        "<!-- comment:end_of_wip -->",
    ],
    BotComment.SURVEY: [
        "<!-- comment:end_survey -->",
        "/1FAIpQLSceJOyGJ6JOzfy6lyR3T7EW_71OWUnNQXp68Fymsk3MkNoSDg/viewform",
        "<!-- comment:no_survey_needed -->",
    ],
    BotComment.NO_CONTRIBUTIONS: [
        "<!-- comment:no-contributions -->",
    ],
}

# These are bot comments in the very first bot comment.
BOT_COMMENTS_FIRST = {
    BotComment.WELCOME,
    BotComment.WELCOME_CLOSED,
    BotComment.NEED_CLA,
    BotComment.BLENDED,
    BotComment.END_OF_WIP,
    BotComment.NO_CONTRIBUTIONS,
}

def is_comment_kind(kind: BotComment, text: str) -> bool:
    """
    Is this `text` a comment of this `kind`?
    """
    return any(snip in text for snip in BOT_COMMENT_INDICATORS[kind])


def github_community_pr_comment(pull_request: PrDict, issue_key: str, **kwargs) -> str:
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * contain a link to our process documentation
    """
    return render_template(
        "github_community_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        issue_key=issue_key,
        has_signed_agreement=pull_request_has_cla(pull_request),
        is_draft=is_draft_pull_request(pull_request),
        is_merged=pull_request.get("merged", False),
        jira_server=settings.JIRA_SERVER,
        **kwargs
    )


def github_community_pr_comment_closed(pull_request: PrDict, issue_key: str, **kwargs) -> str:
    """
    For adding a first comment to a closed pull request (happens during
    rescanning).
    """
    return render_template(
        "github_community_pr_comment_closed.md.j2",
        issue_key=issue_key,
        is_merged=pull_request.get("merged", False),
        jira_server=settings.JIRA_SERVER,
        **kwargs
    )


def github_blended_pr_comment(
    pull_request: PrDict,
    issue_key: str,
    blended_epic: Optional[JiraDict],
    **kwargs
) -> str:
    """
    Create a Blended PR comment.
    """
    custom_fields = get_jira_custom_fields()
    if custom_fields and blended_epic is not None:
        project_name = blended_epic["fields"].get(custom_fields["Blended Project ID"])
        project_page = blended_epic["fields"].get(custom_fields["Blended Project Status Page"])
    else:
        project_name = project_page = None

    return render_template("github_blended_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        issue_key=issue_key,
        project_name=project_name,
        project_page=project_page,
        is_draft=is_draft_pull_request(pull_request),
        jira_server=settings.JIRA_SERVER,
        **kwargs
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

def _format_datetime(datetime_string):
    return arrow.get(datetime_string).format('YYYY-MM-DD+HH:mm')

def github_end_survey_comment(pull_request: PrDict) -> str:
    """
    Create a "please fill out this survey" comment.
    """
    is_merged = pull_request.get("merged", False)
    url = SURVEY_URL.format(
        repo_full_name=pull_request["base"]["repo"]["full_name"],
        pull_request_url=pull_request["html_url"],
        contributor_url=pull_request["user"]["html_url"],
        created_at=_format_datetime(pull_request["created_at"]),
        closed_at=_format_datetime(pull_request["closed_at"]),
        is_merged="Yes" if is_merged else "No",
    )
    return render_template(
        "github_end_survey.md.j2",
        user=pull_request["user"]["login"],
        is_merged=is_merged,
        survey_url=url,
    )


def no_contributions_thanks(pull_request: PrDict) -> str:   # pylint: disable=unused-argument
    """
    Create a "no contributions" comment.
    """
    return render_template("no_contributions.md.j2")


def extract_data_from_comment(text: str) -> Dict:
    """
    Extract the data from a data HTML comment in the comment text.
    """
    if match := re.search("<!-- data: ([^ ]+) -->", text):
        try:
            return json.loads(binascii.a2b_base64(match[1]).decode("utf8"))
        except Exception:  # pylint: disable=broad-except
            return {}
    return {}


def format_data_for_comment(data: Dict) -> str:
    """
    Format a data dictionary for appending to a comment.
    """
    b64 = binascii.b2a_base64(json.dumps(data).encode("utf8")).strip().decode("ascii")
    return f"\n<!-- data: {b64} -->\n"
