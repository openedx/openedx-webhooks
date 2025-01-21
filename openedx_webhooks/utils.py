"""
Generic utilities.
"""

import functools
import hmac
import os
import sys
import time
from functools import wraps
from hashlib import sha1
from time import sleep as retry_sleep   # so that we can patch it for tests.
from typing import Dict, Optional

import cachetools.func
import requests
from flask import jsonify, request, Response, url_for
from urlobject import URLObject

from openedx_webhooks import logger
from openedx_webhooks.auth import get_github_session, get_jira_session
from openedx_webhooks.types import JiraDict, PrDict


def environ_get(name: str, default=None) -> str:
    """
    Get an environment variable, raising an error if it's missing.
    """
    val = os.environ.get(name, default)
    if val is None:
        raise Exception(f"Required environment variable {name!r} is missing")
    return val


def _check_auth(username, password):
    """
    Checks if a username / password combination is valid.
    """
    return (
        username == os.environ.get('HTTP_BASIC_AUTH_USERNAME') and
        password == os.environ.get('HTTP_BASIC_AUTH_PASSWORD')
    )

def _authenticate():
    """
    Sends a 401 response that enables basic auth
    """
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return _authenticate()
        return f(*args, **kwargs)
    return decorated


class RequestFailed(Exception):
    pass

def log_check_response(response, raise_for_status=True):
    """
    Logs HTTP request and response at debug level and checks if it succeeded.

    Arguments:
        response (requests.Response)
        raise_for_status (bool): if True, call raise_for_status on the response
            also.
    """
    msg = "Request: {0.method} {0.url}: {0.body!r}".format(response.request)
    logger.debug(msg)
    msg = "Response: {0.status_code} {0.reason!r} for {0.url}: {0.content!r}".format(response)
    logger.debug(msg)
    if raise_for_status:
        try:
            response.raise_for_status()
        except Exception as exc:
            req = response.request
            raise RequestFailed(f"HTTP request failed: {req.method} {req.url}. Response body: {response.content}") from exc


def log_rate_limit():
    """Get stats from GitHub about the current rate limit, and log them."""
    rate = get_github_session().get("/rate_limit").json()['rate']
    reset = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(rate['reset']))
    logger.info(f"Rate limit: {rate['limit']}, used {rate['used']}, remaining {rate['remaining']}. Reset is at {reset}")


def is_valid_payload(secret: str, signature: str, payload: bytes) -> bool:
    """
    Ensure payload is valid according to signature.

    Make sure the payload hashes to the signature as calculated using
    the shared secret.

    Arguments:
        secret (str): The shared secret
        signature (str): Signature as calculated by the server, sent in
            the request
        payload (bytes): The request payload

    Returns:
        bool: Is the payload legit?
    """
    mac = hmac.new(secret.encode(), msg=payload, digestmod=sha1)
    digest = 'sha1=' + mac.hexdigest()
    return hmac.compare_digest(digest.encode(), signature.encode())


def text_summary(text, length=40):
    """
    Make a summary of `text`, at most `length` chars long.

    The middle will be elided if needed.
    """
    if len(text) <= length:
        return text
    else:
        start = (length - 3) // 2
        end = length - 3 - start
        return text[:start] + "..." + text[-end:]


def retry_get(session, url, **kwargs):
    """
    Get a URL, but retry if it returns a 404.

    GitHub has been known to send us a pull request event, and then return a
    404 when we ask for the comments on the pull request.  This will retry
    with a pause to get the real answer.

    """
    tries = 10
    while True:
        resp = session.get(url, **kwargs)
        if resp.status_code == 404:
            tries -= 1
            if tries == 0:
                break
            retry_sleep(.5)
            continue
        else:
            break
    return resp


def paginated_get(url, session=None, limit=None, per_page=100, callback=None, **kwargs):
    """
    Retrieve all objects from a paginated API.

    Assumes that the pagination is specified in the "link" header, like
    Github's v3 API.

    The `limit` describes how many results you'd like returned.  You might get
    more than this, but you won't make more requests to the server once this
    limit has been exceeded.  For example, paginating by 100, if you set a
    limit of 250, three requests will be made, and you'll get 300 objects.

    """
    url = URLObject(url).set_query_param('per_page', str(per_page))
    limit = limit or 999999999
    session = session or requests.Session()
    returned = 0
    while url:
        resp = retry_get(session, url, **kwargs)
        log_check_response(resp)
        if callable(callback):
            callback(resp)
        for item in resp.json():
            yield item
            returned += 1
        url = None
        if resp.links and returned < limit:
            url = resp.links.get("next", {}).get("url", "")


def jira_paginated_get(url, session=None,
                       start=0, start_param="startAt", obj_name=None,
                       retries=3, debug=False, **fields):
    """
    Like ``paginated_get``, but uses JIRA's conventions for a paginated API, which
    are different from Github's conventions.
    """
    session = session or requests.Session()
    url = URLObject(url)
    more_results = True
    while more_results:
        result_url = (
            url.set_query_param(start_param, str(start))
               .set_query_params(**fields)
        )
        for _ in range(retries):
            try:
                if debug:
                    print(result_url, file=sys.stderr)
                result_resp = session.get(result_url)
                result = result_resp.json()
                break
            except ValueError:
                continue
        result_resp.raise_for_status()
        result = result_resp.json()
        if not result:
            break
        if obj_name:
            objs = result[obj_name]
        else:
            objs = result
        for obj in objs:
            yield obj
        # are we done yet?
        if isinstance(result, dict):
            returned = len(objs)
            total = result["total"]
            if start + returned < total:
                start += returned
            else:
                more_results = False
        else:
            # `result` is a list
            start += len(result)
            more_results = True  # just keep going until there are no more results.


def value_graphql_type(field_type: str) -> str:
    if field_type == "date":
        return "Date"
    elif field_type == "number":
        return "Float"
    else:
        return "String"


def graphql_query(query: str, variables: Dict = {}) -> Dict:    # pylint: disable=dangerous-default-value
    """
    Make a GraphQL query against GitHub.
    """
    url = "https://api.github.com/graphql"
    body = {
        "query": query,
        "variables": variables,
    }
    response = get_github_session().post(url, json=body)
    log_check_response(response)
    returned = response.json()
    if "errors" in returned and returned["errors"]:
        raise Exception(f"GraphQL error: {returned!r}")
    return returned["data"]


# A list of all the memoized functions, so that `clear_memoized_values` can
# clear them all.
_memoized_functions = []

def memoize(func):
    """Cache the value returned by a function call forever."""
    func = functools.lru_cache()(func)
    _memoized_functions.append(func)
    return func

def memoize_timed(minutes):
    """Cache the value of a function for `minutes` minutes."""
    def _timed(func):
        # We use time.time as the timer so that freezegun can test it, and in a
        # new function so that freezegun's patching will work.  Freezegun doesn't
        # patch time.monotonic, and we aren't that picky about the time anyway.
        def patchable_timer():
            return time.time()
        func = cachetools.func.ttl_cache(ttl=60 * minutes, timer=patchable_timer)(func)
        _memoized_functions.append(func)
        return func
    return _timed

def clear_memoized_values():
    """Clear all the values saved by @memoize and @memoize_timed, to ensure isolated tests."""
    for func in _memoized_functions:
        func.cache_clear()


def minimal_wsgi_environ():
    values = {
        "HTTP_HOST", "SERVER_NAME", "SERVER_PORT", "REQUEST_METHOD",
        "SCRIPT_NAME", "PATH_INFO", "QUERY_STRING", "wsgi.url_scheme",
    }
    return {key: value for key, value in request.environ.items()
            if key in values}


def queue_task(task, *args, **kwargs):
    """
    Queue a task to run in the background via Celery.

    Returns the HTTP response to return from a view.
    """
    result = task.delay(*args, wsgi_environ=minimal_wsgi_environ(), **kwargs)
    status_url = url_for("tasks.status", task_id=result.id, _external=True)
    logger.info(f"Job status URL: {status_url}")
    resp = jsonify({"message": "queued", "status_url": status_url})
    resp.status_code = 202
    resp.headers["Location"] = status_url
    return resp


def sentry_extra_context(data_dict):
    """Apply the keys and values from data_dict to the Sentry extra context."""
    from sentry_sdk import configure_scope
    with configure_scope() as scope:
        for key, value in data_dict.items():
            scope.set_extra(key, value)


def get_jira_issue(jira_nick: str, key: str, missing_ok: bool = False) -> Optional[JiraDict]:
    """
    Get the dictionary for a Jira issue, from its key.

    Args:
        key: the Jira id of the issue to find.
        missing_ok: True if this function should return None for missing issue.

    Returns:
        A dict of Jira information, or None if missing_ok is True, and the issue
        is missing.

    """
    resp = jira_get(jira_nick, "/rest/api/2/issue/{key}".format(key=key))
    if resp.status_code == 404 and missing_ok:
        return None
    log_check_response(resp)
    return resp.json()


def jira_get(jira_nick, *args, **kwargs):
    """
    JIRA sometimes returns an empty response to a perfectly valid GET request,
    so this will retry it a few times if that happens.
    """
    for _ in range(3):
        resp = get_jira_session(jira_nick).get(*args, **kwargs)
        if resp.content:
            return resp
    return get_jira_session(jira_nick).get(*args, **kwargs)


def get_pr_state(pr: PrDict):
    """
    Get gthub pull request state.
    """
    if pr.get("hook_action") == "reopened":
        state = "reopened"
    elif pr["state"] == "open":
        state = "open"
    elif pr["merged"]:
        state = "merged"
    else:
        state = "closed"
    return state
