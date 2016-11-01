# -*- coding: utf-8 -*-
"""
Decorators for working with GitHub.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from functools import wraps

from github3 import GitHub


def inject_gh(f):
    """
    Inject authenticated GitHub client (``gh``) if one is not supplied.

    Use this decorator for functions that need to talk to the GitHub API
    server::

        @inject_gh
        def my_func(gh, param1, param2):
            ...

    The decorator expects an authenticated ``github3.GitHub`` instance to
    be passed in, either as the first parameter::

        my_func(my_client_instance, param1, param2)

    Or as a ``gh`` keyword parameter::

        my_func(param1, param2, gh=my_client_instance)

    If you don't pass an authenticated client instance, it will default to
    using ``openedx_webhooks.lib.github.client.github_client``::

        my_func(param1, param2)

    The decorated function **must** accept a ``github3.GitHub`` client as
    its first parameter.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        tmp_args = list(args)
        if args and isinstance(args[0], GitHub):
            gh = tmp_args.pop(0)
        else:
            gh = kwargs.pop('gh', None)

        if not gh:
            from .client import github_client as gh

        return f(gh, *tmp_args, **kwargs)
    return wrapper
