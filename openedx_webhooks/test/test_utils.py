"""Tests of code in utils.py"""

import pytest

from openedx_webhooks.utils import text_summary


@pytest.mark.parametrize("args, summary", [
    (["Hello"], "Hello"),
    ([""], ""),
    (["lorem ipsum quia dolor sit amet consecte"], "lorem ipsum quia dolor sit amet consecte"),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, sed quia non numquam eius modi tempora incidunt."],
      "lorem ipsum quia d...i tempora incidunt."),
    (["lorem ipsum quia dolor sit amet consectetur adipisci velit, sed quia non numquam eius modi tempora incidunt.", 80],
      "lorem ipsum quia dolor sit amet consec...non numquam eius modi tempora incidunt."),
])
def test_text_summary(args, summary):
    assert summary == text_summary(*args)
