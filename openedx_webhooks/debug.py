"""Helpers for debugging."""

import base64
import gzip
import json
import logging


def is_debug(module_name):
    """Is this module configured for debug-level information?"""
    return logging.getLogger(module_name).isEnabledFor(logging.DEBUG)


def print_long(label, long_text):
    """Print a long data dump in a logging-safe way."""
    data = base64.b85encode(gzip.compress(long_text.encode())).decode()
    print(
        f"{label}:",
        "import base64,gzip;" +
        f"print(gzip.decompress(base64.b85decode({data!r})).decode())"
    )

def print_long_json(label, jdata):
    """Like print_long, but for JSON data."""
    print_long(label, json.dumps(jdata, sort_keys=True, indent=4))
