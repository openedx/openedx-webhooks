# -*- coding: utf-8 -*-
"""
Decorators for working with JIRA.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from functools import wraps

from jira import JIRA


def inject_jira(f):
    """
    Inject authenticated JIRA client (``jira``) if one is not supplied.

    Use this decorator for functions that need to talk to the JIRA API
    server::

        @inject_jira
        def my_func(jira, param1, param2):
            ...

    The decorator expects an authenticated ``jira.JIRA`` instance to
    be passed in, either as the first parameter::

        my_func(my_client_instance, param1, param2)

    Or as a ``jira`` keyword parameter::

        my_func(param1, param2, jira=my_client_instance)

    If you don't pass an authenticated client instance, it will default to
    using ``openedx_webhooks.lib.jira.client.jira_client``::

        my_func(param1, param2)

    The decorated function **must** accept a ``jira.JIRA`` client as
    its first parameter.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        tmp_args = list(args)
        if args and isinstance(args[0], JIRA):
            jira = tmp_args.pop(0)
        else:
            jira = kwargs.pop('jira', None)

        if not jira:
            from .client import jira_client as jira

        return f(jira, *tmp_args, **kwargs)
    return wrapper
