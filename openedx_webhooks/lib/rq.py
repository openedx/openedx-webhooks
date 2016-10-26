# -*- coding: utf-8 -*-
"""
RQ tools.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from rq import Queue
import redis

_redis_url = os.getenv('REDIS_URL', 'redis://')

store = redis.from_url(_redis_url)
"""
redis.Redis: Instance of a connected Redis store
"""

q = Queue(connection=store)
"""
rq.Queue: Instance of RQ queue
"""
