#!/usr/bin/env python
"""
Start an instance of the RQ worker.

``python rq_worker.py``
"""

import os

from rq import Connection, Queue, Worker

from openedx_webhooks.lib.rq import store

LISTEN = ('default',)


if __name__ == '__main__':
    logging_level = os.environ.get('RQ_WORKER_LOGGING_LEVEL', 'INFO').upper()
    with Connection(store):
        worker = Worker(map(Queue, LISTEN))
        worker.work(logging_level=logging_level)
