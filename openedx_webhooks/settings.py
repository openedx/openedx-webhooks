"""Settings for how the webhook should behave."""

import os


JIRA_SERVER = os.environ.get("JIRA_SERVER", "https://none.nojira.net")

# The project all OSPRs should be added to.
# This should be in the form of org:num, like "openedx:19"
project = os.environ.get("GITHUB_OSPR_PROJECT", "none:0")
org, num = project.split(":")
GITHUB_OSPR_PROJECT = (org, int(num))
