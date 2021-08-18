"""
Dispatch incoming webhook events to matching actions.
"""

import logging

from ...lib.github.models import GithubWebHookRequestHeader
from .actions import ACTIONS


logger = logging.getLogger(__name__)

def dispatch(raw_headers, event, actions=ACTIONS):
    """
    Determine how an event needs to be processed.

    Arguments:
        raw_headers (flask.Request.headers)
        event (Dict[str, Any]): The parsed event payload
        actions (List[Module, ...]): A list of actions to process, in order
    """
    event_type = GithubWebHookRequestHeader(raw_headers).event_type

    for action in [a for a in actions if event_type in a.EVENT_TYPES]:
        pr_url = event.get("pull_request", {}).get("url", "?")
        logger.info(f"dispatching action={action.__name__} for {event_type=}, {pr_url=}")
        action.run(event_type, event)
