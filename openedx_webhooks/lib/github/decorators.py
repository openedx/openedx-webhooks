"""
Decorators for working with GitHub.
"""

from functools import wraps

from github3 import GitHub

from ..utils import dependency_exists


def inject_gh(f):
    """
    Inject authenticated GitHub client (``gh``) if one is not supplied.

    Use this decorator for functions that need to talk to the GitHub API
    server::

        @inject_gh
        def my_func(gh, param1, param2):
            ...

    The decorator expects an authenticated ``github3.GitHub`` instance to
    be passed in, either as one of the parameters::

        my_func(my_client_instance, param1, param2)

    Or as a keyword parameter::

        my_func(param1=param1, param2=param2, gh=my_client_instance)

    If you don't pass an authenticated client instance, it will inject
    ``openedx_webhooks.lib.github.client.github_client`` as the first
    parameter::

        my_func(param1, param2)

    becomes:

        my_func(my_client_instance, param1, param2)
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if dependency_exists(GitHub, *args, **kwargs):
            return f(*args, **kwargs)

        from .client import github_client as gh
        return f(gh, *args, **kwargs)
    return wrapper
