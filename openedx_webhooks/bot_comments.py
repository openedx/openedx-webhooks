"""
The bot makes comments on pull requests. This is stuff needed to do it well.
"""

import binascii
import json
import re

from enum import Enum, auto
from typing import Dict

import arrow
from flask import render_template

from openedx_webhooks.info import (
    get_jira_server_info,
    get_repo_spec,
    is_draft_pull_request,
    pull_request_has_cla,
)
from openedx_webhooks.types import JiraId, PrDict

# Author association values for which we should consider the author new
GITHUB_NEW_AUTHOR_ASSOCIATIONS = (
    "FIRST_TIMER",  # Author has not previously committed to GitHub.
    "FIRST_TIME_CONTRIBUTOR",  # Author has not previously committed to the repository.
)

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
    NO_JIRA_SERVER = auto()
    NO_JIRA_MAPPING = auto()


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
    BotComment.NO_JIRA_MAPPING: [
        "<!-- comment:no-jira-mapping -->",
    ],
    BotComment.NO_JIRA_SERVER: [
        "<!-- comment:no-jira-server -->",
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


def github_community_pr_comment(pull_request: PrDict) -> str:
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * contain a link to our process documentation
    """
    is_first_time = pull_request.get("author_association", None) in GITHUB_NEW_AUTHOR_ASSOCIATIONS
    spec = get_repo_spec(pull_request["base"]["repo"]["full_name"])

    return render_template(
        "github_community_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        has_signed_agreement=pull_request_has_cla(pull_request),
        is_draft=is_draft_pull_request(pull_request),
        is_merged=pull_request.get("merged", False),
        is_first_time=is_first_time,
        owner=spec.owner,
        lifecycle=spec.lifecycle,
    )


def github_community_pr_comment_closed(pull_request: PrDict) -> str:
    """
    For adding a first comment to a closed pull request (happens during
    rescanning).
    """
    return render_template(
        "github_community_pr_comment_closed.md.j2",
        is_merged=pull_request.get("merged", False),
    )


def github_blended_pr_comment(pull_request: PrDict) -> str:
    """
    Create a Blended PR comment.
    """
    return render_template("github_blended_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        is_draft=is_draft_pull_request(pull_request),
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


def jira_issue_comment(pull_request: PrDict, jira_id: JiraId) -> str:   # pylint: disable=unused-argument
    """Render a comment about making a new Jira issue."""
    jira_server = get_jira_server_info(jira_id.nick)
    body = render_template(
        "jira_issue_comment.md.j2",
        server_url=jira_server.server,
        server_description=jira_server.description,
        key=jira_id.key,
    )
    body += format_data_for_comment({"jira_issues": [jira_id.asdict()]})
    return body


def no_contributions_thanks(pull_request: PrDict) -> str:   # pylint: disable=unused-argument
    """
    Create a "no contributions" comment.
    """
    return render_template("no_contributions.md.j2")


def no_jira_mapping_comment(jira_nick: str) -> str:
    """
    Create a comment for the error of not having a Jira project mapping for this repo.
    """
    jira_server = get_jira_server_info(jira_nick)
    body = render_template(
        "no_jira_mapping.md.j2",
        jira_server=jira_server,
    )
    body += format_data_for_comment({"jira_errors": [jira_nick]})
    return body


def no_jira_server_comment(jira_nick: str) -> str:
    """
    Create a comment for the error of not knowing this particular Jira server.
    """
    body = render_template(
        "no_jira_server.md.j2",
        jira_nick=jira_nick,
    )
    body += format_data_for_comment({"jira_errors": [jira_nick]})
    return body


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
