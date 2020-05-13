r"""
Actions evaluted by the dispatcher.

Each dispatcher action determines whether an event requires additional
processing. Each action implements the ``run(event_type, event)``
interface.

Inputs
------

-  `event\_type`_ is one of the GitHub event types as delivered via the
   ``X-Github-Event`` header.

-  event is the event payload parsed into a Python ``dict``.

.. _event\_type: https://developer.github.com/v3/activity/events/types/
"""

from . import closed_ospr_survey, github_activity

# List[Module, ...]: A list of actions to process, in order
ACTIONS = [
    closed_ospr_survey,
    github_activity,
]
