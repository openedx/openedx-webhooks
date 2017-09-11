# -*- coding: utf-8 -*-
r"""
Rules evaluted by the dispatcher.

Each dispatcher rule determines whether an event requires additional
processing. Each rule implements the ``run(event_type, event)``
interface.

Inputs
------

-  `event\_type`_ is one of the GitHub event types as delivered via the
   ``X-Github-Event`` header.

-  event is the event payload parsed into a Python ``dict``.

.. _event\_type: https://developer.github.com/v3/activity/events/types/
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from . import github_activity

# List[Module, ...]: A list of rules to process, in order
RULES = [
    github_activity,
]
