"""
The bot makes comments on pull requests. This is stuff needed to do it well.
"""

from enum import Enum, auto
from typing import Optional

from flask import render_template

from openedx_webhooks.info import pull_request_has_cla
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
    CLOSED = auto()
    MERGED = auto()

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
    # does the user have a valid, signed contributor agreement?
    has_signed_agreement = pull_request_has_cla(pull_request)
    return render_template("github_community_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        issue_key=issue_key,
        has_signed_agreement=has_signed_agreement,
        **kwargs
    )


def github_contractor_pr_comment(pull_request: PrDict, **kwargs) -> str:
    """
    For a newly-created pull request from a contractor that edX works with,
    write a comment on the pull request. The comment should:

    * Help the author determine if the work is paid for by edX or not
    * If not, show the author how to trigger the creation of an OSPR issue
    """
    return render_template("github_contractor_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        repo=pull_request["base"]["repo"]["full_name"],
        number=pull_request["number"],
        **kwargs
    )


def github_committer_pr_comment(pull_request: PrDict, issue_key: str, **kwargs) -> str:
    """
    Create the body of the comment for new pull requests from core committers.
    """
    return render_template("github_committer_pr_comment.md.j2",
        user=pull_request["user"]["login"],
        issue_key=issue_key,
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
        **kwargs
    )
