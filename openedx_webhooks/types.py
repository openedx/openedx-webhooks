"""Types specific to openedx_webhooks."""

from typing import Dict, Tuple

# A pull request as described by a JSON object.
PrDict = Dict

# A pull request comment as described by a JSON object.
PrCommentDict = Dict

# A Jira issue described by a JSON object.
JiraDict = Dict

# A GitHub project: org name, and number.
GhProject = Tuple[str, int]
