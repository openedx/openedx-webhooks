"""Tests of the helpers in tests/helpers.py"""

import pytest

from .helpers import check_good_markdown, random_text


@pytest.mark.parametrize("text, ok", [
    ("This is a paragraph", True),
    ("This is a paragraph\n\nThis is also\n", True),
    ("   Bad: initial space", False),
    ("<!-- ok -->\nA paragraph", True),
    ("<!-- bad -->A paragraph", False),
    ("Trailing comment<!-- bad -->\n", False),
    ("Look here: [None](https://foo.com).", False),
    ("Look here: [foo](https://foo.com/api/id/None).", False),
    ("Look here: [foo](https://foo.com/api/id/None/comments).", False),
])
def test_check_good_markdown(text, ok):
    if ok:
        check_good_markdown(text)
    else:
        with pytest.raises(ValueError):
            check_good_markdown(text)


def test_random_text():
    texts = set(random_text() for _ in range(10))
    assert len(texts) == 10
    assert "" not in texts
