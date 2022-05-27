"""Settings for how the webhook should behave."""

import os


JIRA_HOST = os.environ.get("JIRA_SERVER", "https://none.nojira.net")
