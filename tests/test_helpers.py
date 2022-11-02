"""Tests of the helpers in tests/helpers.py"""

import pytest

from .helpers import check_good_graphql, check_good_markdown, random_text


@pytest.mark.parametrize("text, ok, msg", [
    ("This is a paragraph", True, ""),
    ("This is a paragraph\n\nThis is also\n", True, ""),
    ("   Bad: initial space", False, "start with whitespace"),
    ("<!-- ok -->\nA paragraph", True, ""),
    ("<!-- bad -->A paragraph", False, "comment with following text"),
    ("Trailing comment<!-- bad -->\n", False, "comment in the middle"),
    ("Look here: [None](https://foo.com).", False, "link to None"),
    ("Look here: [foo](https://foo.com/api/id/None).", False, "link to a None"),
    ("Look here: [foo](https://foo.com/api/id/None/comments).", False, "link to a None"),
])
def test_check_good_markdown(text, ok, msg):
    if ok:
        assert msg == ""
        check_good_markdown(text)
    else:
        with pytest.raises(ValueError, match=msg):
            check_good_markdown(text)


def test_random_text():
    texts = set(random_text() for _ in range(10))
    assert len(texts) == 10
    assert "" not in texts


@pytest.mark.parametrize("text, ok, msg", [
    ("query { org }", True, ""),
    ("# This is GraphQL!\n query Hello {org}\n", True, ""),
    (" what { org }", False, "wrong word"),
    ("""\
        query OrgProjectId (
          $owner: String!
          $number: Int!
        ) {     # This line has )
          organization (login: $owner) {
            projectV2 (number: $number) {
              id
            }
          }
        }
        """, True, ""),
    ("query (hi {ord}", False, "balanced"),
    ("query hello )hi {ord}", False, "balanced"),
    ("query (((}", False, "balanced"),
    ("""\
        mutation AddProjectItem (
          $projectId: String!
          $prNodeId: String!
        {   # This line is missing )
          addProjectV2ItemById (input: {projectId: $projectId, contentId: $prNodeId}) {
            item {
              id
            }
          }
        }
        """, False, "balanced"),
])
def test_check_good_graphql(text, ok, msg):
    if ok:
        assert msg == ""
        check_good_graphql(text)
    else:
        with pytest.raises(ValueError, match=msg):
            check_good_graphql(text)
