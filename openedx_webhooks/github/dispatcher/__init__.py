# -*- coding: utf-8 -*-
"""
Dispatch incoming webhook events to each rule.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from ...lib.github.models import GithubWebHookRequestHeader
from .rules import RULES


def dispatch(raw_headers, event, rules=RULES):
    """
    Determine how an event needs to be processed.

    Arguments:
        raw_headers (flask.Request.headers)
        event (Dict[str, Any]): The parsed event payload
        rules (List[Module, ...]): A list of rules to process, in order
    """
    event_type = GithubWebHookRequestHeader(raw_headers).event_type

    for rule in rules:
        rule.run(event_type, event)
