"""
The bot makes comments on pull requests. This is stuff needed to do it well.
"""

import binascii
import json
import re

from enum import Enum, auto
from typing import Dict, List, Optional

from flask import render_template

from openedx_webhooks.info import (
    is_draft_pull_request,
    pull_request_has_cla,
)
from openedx_webhooks.oauth import get_jira_session
from openedx_webhooks.types import JiraDict, PrDict
from openedx_webhooks.utils import get_jira_custom_fields


class BotComment(Enum):
    """
    Comments the bot can leave on pull requests.
    """
    WELCOME = auto()
    NEED_CLA = auto()
    CONTRACTOR = auto()
    CORE_COMMITTER = auto()
    BLENDED = auto()
    OK_TO_TEST = auto()
    CHAMPION_MERGE_PING = auto()
    END_OF_WIP = auto()

BOT_COMMENT_INDICATORS = {
    BotComment.WELCOME: [
        "<!-- comment:external_pr -->",
        "Feel free to add as much of the following information to the ticket:",
    ],
    BotComment.NEED_CLA: [
        "<!-- comment:no_cla -->",
        "We can't start reviewing your pull request until you've submimitted",
    ],
    BotComment.CONTRACTOR: [
        "<!-- comment:contractor -->",
        "company that does contract work for edX",
    ],
    BotComment.CORE_COMMITTER: [
        "<!-- comment:welcome-core-committer -->",
    ],
    BotComment.BLENDED: [
        "<!-- comment:welcome-blended -->",
    ],
    BotComment.OK_TO_TEST: [
        "<!-- jenkins ok to test -->",
    ],
    BotComment.CHAMPION_MERGE_PING: [
        "<!-- comment:champion_merge_ping -->",
    ],
    BotComment.END_OF_WIP: [
        "<!-- comment:end_of_wip -->",
    ],
}

# These are bot comments in the very first bot comment.
BOT_COMMENTS_FIRST = {
    BotComment.WELCOME,
    BotComment.BLENDED,
    BotComment.CONTRACTOR,
    BotComment.CORE_COMMITTER,
    BotComment.OK_TO_TEST,
}

def is_comment_kind(kind: BotComment, text: str) -> bool:
    """
    Is this `text` a comment of this `kind`?
    """
    return BOT_COMMENT_INDICATORS[kind][0] in text


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
        **kwargs
    )


def github_contractor_pr_comment(pull_request: PrDict, **kwargs) -> str:
    """
    For a newly-created pull request from a contractor that edX works with,
    write a comment on the pull request. The comment should:

    * Help the author determine if the work is paid for by edX or not
    * If not, show the author how to trigger the creation of an OSPR issue
    """
    return render_template(
        "github_contractor_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
        is_draft=is_draft_pull_request(pull_request),
        **kwargs
    )


def github_committer_pr_comment(pull_request: PrDict, issue_key: str, **kwargs) -> str:
    """
    Create the body of the comment for new pull requests from core committers.
    """
    return render_template(
        "github_committer_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        issue_key=issue_key,
        is_draft=is_draft_pull_request(pull_request),
        **kwargs
    )


def github_committer_merge_ping_comment(pull_request: PrDict, champions: List[str], **kwargs) -> str:
    """
    Create the body of the comment saying, "Hey champion: a core committer merged something!"
    """
    return render_template(
        "github_committer_merge_ping_comment.md.j2",
        user=pull_request["user"]["login"],
        champions=champions,
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
    custom_fields = get_jira_custom_fields(get_jira_session())
    if blended_epic is not None:
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
        **kwargs
    )


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
