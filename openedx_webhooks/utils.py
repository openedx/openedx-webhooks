# coding=utf-8
from __future__ import print_function, unicode_literals

import sys
import os
import functools
import requests
from urlobject import URLObject
from flask import request


def pop_dict_id(d):
    id = d["id"]
    del d["id"]
    return (id, d)


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
        resp = session.get(url, **kwargs)
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
        for _ in xrange(retries):
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


def jira_group_members(groupname, session=None, start=0, retries=3, debug=False):
    """
    JIRA's group members API is horrible. This makes it easier to use.
    """
    session = session or requests.Session()
    url = URLObject("/rest/api/2/group").set_query_param("groupname", groupname)
    more_results = True
    while more_results:
        end = start + 49  # max 50 users per page
        expand = "users[{start}:{end}]".format(start=start, end=end)
        result_url = url.set_query_param("expand", expand)
        for _ in xrange(retries):
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
        users = result["users"]["items"]
        for user in users:
            yield user
        returned = len(users)
        total = result["users"]["size"]
        if start + returned < total:
            start += returned
        else:
            more_results = False


def jira_users(filter=None, session=None, debug=False):
    """
    JIRA has an API for returning all users, but it's not ready for primetime.
    It's used only by the admin pages, and it does authentication based on
    session cookies only. We'll use it anyway, since there is no alternative.
    """
    session = session or requests.Session()
    session.cookies["studio.crowd.tokenkey"] = studio_crowd_tokenkey()

    users = jira_paginated_get(
        "/admin/rest/um/1/user/search",
        filter=filter,
        start_param="start-index",
        session=session,
        debug=debug,
    )
    for user in users:
        yield user


def memoize(func):
    cache = {}

    def mk_key(*args, **kwargs):
        return (tuple(args), tuple(sorted(kwargs.items())))

    @functools.wraps(func)
    def memoized(*args, **kwargs):
        key = memoized.mk_key(*args, **kwargs)
        try:
            return cache[key]
        except KeyError:
            cache[key] = func(*args, **kwargs)
            return cache[key]

    memoized.mk_key = mk_key

    def uncache(*args, **kwargs):
        key = memoized.mk_key(*args, **kwargs)
        if key in cache:
            del cache[key]
            return True
        else:
            return False

    memoized.uncache = uncache

    def flush_cache():
        cache = {}

    memoized.flush_cache = flush_cache

    return memoized


def memoize_except(values):
    """
    Just like normal `memoize`, but don't cache when the function returns
    certain values. For example, you could use this to make a function not
    cache `None`.
    """
    if not isinstance(values, (list, tuple)):
        values = (values,)

    def decorator(func):
        cache = {}

        def mk_key(*args, **kwargs):
            return (tuple(args), tuple(sorted(kwargs.items())))

        @functools.wraps(func)
        def memoized(*args, **kwargs):
            key = memoized.mk_key(*args, **kwargs)
            try:
                return cache[key]
            except KeyError:
                value = func(*args, **kwargs)
                if value not in values:
                    cache[key] = value
                return value

        memoized.mk_key = mk_key

        def uncache(*args, **kwargs):
            key = memoized.mk_key(*args, **kwargs)
            if key in cache:
                del cache[key]
                return True
            else:
                return False

        memoized.uncache = uncache

        def flush_cache():
            cache = {}

        memoized.flush_cache = flush_cache

        return memoized

    return decorator


def to_unicode(s):
    if isinstance(s, unicode):
        return s
    return s.decode('utf-8')


@memoize
def studio_crowd_tokenkey(base_url="https://openedx.atlassian.net"):
    """
    This is the authentication cookie used to authenticate to the admin site.
    """
    JIRA_USERNAME = os.environ.get("JIRA_USERNAME")
    JIRA_PASSWORD = os.environ.get("JIRA_PASSWORD")

    if not JIRA_USERNAME or not JIRA_PASSWORD:
        raise Exception("Missing required environment variables: JIRA_USERNAME, JIRA_PASSWORD")

    login_url = URLObject(base_url).relative("/login")
    payload = {"username": JIRA_USERNAME, "password": JIRA_PASSWORD}
    login_resp = requests.post(login_url, data=payload, allow_redirects=False)
    if not login_resp.status_code in (200, 303):
        raise requests.exceptions.RequestException(login_resp.text)
    return login_resp.cookies["studio.crowd.tokenkey"]


def minimal_wsgi_environ():
    values = set((
        "HTTP_HOST", "SERVER_NAME", "SERVER_PORT", "REQUEST_METHOD",
        "SCRIPT_NAME", "PATH_INFO", "QUERY_STRING", "wsgi.url_scheme",
    ))
    return {key: value for key, value in request.environ.items()
            if key in values}
