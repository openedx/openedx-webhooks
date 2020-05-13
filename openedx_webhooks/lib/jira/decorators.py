"""
Decorators for working with JIRA.
"""

from functools import wraps

from jira import JIRA

from ..utils import dependency_exists


def inject_jira(f):
    """
    Inject authenticated JIRA client (``jira``) if one is not supplied.

    Use this decorator for functions that need to talk to the JIRA API
    server::

        @inject_jira
        def my_func(jira, param1, param2):
            ...

    The decorator expects an authenticated ``jira.JIRA`` instance to
    be passed in, either as one of the parameters::

        my_func(my_client_instance, param1, param2)

    Or as a keyword parameter::

        my_func(param1=param1, param2=param2, jira=my_client_instance)

    If you don't pass an authenticated client instance, it will inject
    ``openedx_webhooks.lib.jira.client.jira_client`` as the first parameter::

        my_func(param1, param2)

    becomes:

        my_func(my_client_instance, param1, param2)
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if dependency_exists(JIRA, *args, **kwargs):
            return f(*args, **kwargs)

        from .client import jira_client as jira
        return f(jira, *args, **kwargs)
    return wrapper
