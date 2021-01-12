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
from typing import Optional

import cachetools.func
import requests
from flask import request, Response
from flask_dance.contrib.jira import jira
from urlobject import URLObject

from openedx_webhooks import logger
from openedx_webhooks.oauth import jira_get
from openedx_webhooks.types import JiraDict


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
        response.raise_for_status()


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


def pop_dict_id(d):
    id = d["id"]
    del d["id"]
    return (id, d)


def text_summary(text, length=40):
    """
    Make a summary of `text`, at most `length` chars long.

    The middle will be elided if needed.
    """
    if len(text) <= length:
        return text
    else:
        start = (length - 3) // 2
        end = (length - 3 - start)
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
        if callable(callback):
            callback(resp)
        result = resp.json()
        if not resp.ok:
            msg = "{code} error for url {url}: {message}".format(
                code=resp.status_code,
                url=resp.url,
                message=result["message"]
            )
            raise requests.exceptions.HTTPError(msg, response=resp)
        for item in result:
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
        yield from objs
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


# A list of all the memoized functions, so that `clear_memoized_values` can
# clear them all.
_memoized_functions = []

def memoize(func):
    """Cache the value returned by a function call forever."""
    func = functools.lru_cache(func)
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


def sentry_extra_context(data_dict):
    """Apply the keys and values from data_dict to the Sentry extra context."""
    from sentry_sdk import configure_scope
    with configure_scope() as scope:
        for key, value in data_dict.items():
            scope.set_extra(key, value)


@memoize_timed(minutes=30)
def get_jira_custom_fields(session=None):
    """
    Return a name-to-id mapping for the custom fields on JIRA.
    """
    session = session or jira
    field_resp = session.get("/rest/api/2/field")
    field_resp.raise_for_status()
    field_map = dict(pop_dict_id(f) for f in field_resp.json())
    return {
        value["name"]: id
        for id, value in field_map.items()
        if value["custom"]
    }


def get_jira_issue(key: str, missing_ok: bool = False) -> Optional[JiraDict]:
    """
    Get the dictionary for a Jira issue, from its key.

    Args:
        key: the Jira id of the issue to find.
        missing_ok: True if this function should return None for missing issue.

    Returns:
        A dict of Jira information, or None if missing_ok is True, and the issue
        is missing.

    """
    resp = jira_get(f"/rest/api/2/issue/{key}")
    if resp.status_code == 404 and missing_ok:
        return None
    log_check_response(resp)
    return resp.json()


def github_pr_repo(issue):
    custom_fields = get_jira_custom_fields()
    pr_repo = issue["fields"].get(custom_fields["Repo"])
    parent_ref = issue["fields"].get("parent")
    if not pr_repo and parent_ref:
        parent = get_jira_issue(parent_ref["key"])
        pr_repo = parent["fields"].get(custom_fields["Repo"])
    return pr_repo


def github_pr_num(issue):
    custom_fields = get_jira_custom_fields()
    pr_num = issue["fields"].get(custom_fields["PR Number"])
    parent_ref = issue["fields"].get("parent")
    if not pr_num and parent_ref:
        parent = get_jira_issue(parent_ref["key"])
        pr_num = parent["fields"].get(custom_fields["PR Number"])
    try:
        return int(pr_num)
    except Exception:       # pylint: disable=broad-except
        return None


def github_pr_url(issue):
    """
    Return the pull request URL for the given JIRA issue,
    or raise an exception if they can't be determined.
    """
    pr_repo = github_pr_repo(issue)
    pr_num = github_pr_num(issue)
    if not pr_repo or not pr_num:
        issue_key = issue["key"]
        fail_msg = f'{issue_key} is missing "Repo" or "PR Number" fields'
        raise Exception(fail_msg)
    return f"/repos/{pr_repo}/pulls/{pr_num}"
