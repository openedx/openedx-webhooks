# -*- coding: utf-8 -*-
"""
RQ tools.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import os

from rq import Queue
import redis

_redis_url = os.getenv('REDIS_URL', 'redis://')

# redis.Redis: Instance of a connected Redis store
store = redis.from_url(_redis_url)

# rq.Queue: Instance of RQ queue
q = Queue(connection=store)
