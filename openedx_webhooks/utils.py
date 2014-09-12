from __future__ import print_function, unicode_literals

import functools
import requests


def pop_dict_id(d):
    id = d["id"]
    del d["id"]
    return (id, d)


def paginated_api(url, obj_name, session=None, start=0, retries=3, **fields):
    session = session or requests.Session()
    more_results = True
    while more_results:
        result_url = (
            url.set_query_param("startAt", str(start))
               .set_query_params(**fields)
        )
        for _ in xrange(retries):
            try:
                result_resp = session.get(result_url)
                result = result_resp.json()
                break
            except ValueError:
                continue
        if not result_resp.ok:
            raise requests.exceptions.RequestException(result)
        result = result_resp.json()
        for obj in result[obj_name]:
            yield obj
        returned = len(result[obj_name])
        total = result["total"]
        if start + returned < total:
            start += returned
        else:
            more_results = False


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
                if not value in values:
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

        return memoized

    return decorator
