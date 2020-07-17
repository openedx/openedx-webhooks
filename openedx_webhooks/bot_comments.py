"""
The bot makes comments on pull requests. This is stuff needed to do it well.
"""

from enum import Enum, auto


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
        "Thanks for the pull request,",
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
