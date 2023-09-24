"""
Base classes for defining fake implementations of APIs.

"""

import functools
import inspect
import json
import re
from typing import Any


class FakerException(Exception):
    """
    An exception to be raised from a route handler.

    It will be converted to an HTTP response using `status_code` and
    `as_json()`.
    """

    status_code: int = 500

    def as_json(self):
        return {"error": str(self)}


def route(path_regex, http_method="GET", data_type="json"):
    """
    Decorator to associate a method with a particular mocked HTTP route.

    The decorated function should have this signature:

        def _route_handler(self, match, request, context):

    The regex is matched against the path. It should not include a host name,
    or query parameters.  If you need the query parameters, access them on the
    request object.

    In the route handler, `match` is the re.match object matching the request
    path.  `request` and `context` are as defined by requests-mock.

    Arguments:
        path_regex: a regex to match against the path of the request.
        http_method: the HTTP method this function will receive.
        data_type: "json" or "text", the type of data the function will return.

    """
    def _decorator(func):
        func.callback_spec = (path_regex, http_method.upper(), data_type)
        @functools.wraps(func)
        def _decorated(self, request, context) -> Any:
            for fn in self.middleware:
                result = fn(request, context)
                if context.status_code != 200 or result is not None:
                    return result
            match = re.match(path_regex, request.path)
            try:
                return func(self, match, request, context)
            except FakerException as ex:
                context.status_code = ex.status_code
                return ex.as_json()
        return _decorated
    return _decorator


class Faker:
    """
    A Fake implementation of a web service, with mocked requests.

    Subclass this and implement handlers decorated with `faker.route` to
    handle mock requests.  Use `install_mocks` to install this Faker's mock
    handlers on a `requests_mocker`.

    """

    def __init__(self, host):
        self.host = host
        self.requests_mocker = None
        self.middleware = []

    def add_middleware(self, middleware_func):
        """
        Add a middleware function to be invoked on all requests.

        The function receives `request` and `context` just as route handlers
        do.  If the function returns non-None, or the context.status_code is
        set to something other than 200, then the request is ended, and the
        route handler is not called.
        """
        self.middleware.append(middleware_func)

    def install_mocks(self, requests_mocker) -> None:
        """
        Install mock requests for all of this Faker's handlers.
        """
        self.requests_mocker = requests_mocker
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, "callback_spec"):
                path_regex, http_method, data_type = method.callback_spec
                self.requests_mocker.register_uri(
                    http_method,
                    re.compile(fr"^{self.host}{path_regex}(\?.*)?$"),
                    **{data_type: method},
                )

    def requests_made(
        self,
        path_regex: str | None = None,
        method: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        Return a list of (method, url) pairs that have been made to this host.

        If no method is provided, all methods are returned.
        """
        reqs = []
        assert self.requests_mocker is not None
        for req in self.requests_mocker.request_history:
            if f"{req.scheme}://{req.hostname}" != self.host:
                continue
            if method is not None and method != req.method:
                continue
            if path_regex is not None and not re.search(path_regex, req.path):
                continue
            url = req.path
            if req.query:
                url += "?" + req.query
            meth = req.method
            # GraphQL hack: everything is a POST, so sniff the body to see if it's
            # a query or a mutation.
            if "/graphql" in url and req.text is not None:
                body = json.loads(req.text)
                meth = body["query"].split()[0]
            reqs.append((url, meth))
        return reqs

    def reset_mock(self) -> None:
        """
        Clear the `requests_made` history.
        """
        assert self.requests_mocker is not None
        self.requests_mocker.reset_mock()

    def assert_readonly(self) -> None:
        """
        Assert that no changes were made, only GET requests.
        """
        writing_requests = [(url, method) for url, method in self.requests_made() if method not in {"GET", "query"}]
        assert writing_requests == [], f"Found writing requests: {writing_requests}"
