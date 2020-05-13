#!/usr/bin/env python

import csv
import json
import os

import click
import redis

click.disable_unicode_literals_warning = True


def get_result_for_key(log, key):
    result = json.loads(log.get(key))
    result['job_id'] = key
    return result


def failed(result):
    return result['status'] != 'SUCCESS'


@click.command()
@click.argument('redis-url')
@click.argument('output-csv')
def cli(redis_url, output_csv):
    """
    Get all failed task status from Celery Redis backend.
    """
    log = redis.from_url(redis_url)
    outfile = os.path.abspath(os.path.expanduser(output_csv))

    with open(outfile, 'w') as csvfile:
        fieldnames = ['job_id', 'status', 'result', 'traceback', 'children']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        all_results = [get_result_for_key(log, k) for k in log.keys('*')]
        failed_results = [r for r in all_results if failed(r)]

        for result in failed_results:
            writer.writerow(result)


if __name__ == '__main__':
    cli()
