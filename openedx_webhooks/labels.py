"""
To properly manipulate labels, we need to know which labels are controlled
by which authority. This is that information.
"""

# These are labels that correspond to Jira statuses.  Only one of them should
# be used at a time.

GITHUB_STATUS_LABELS: set[str] = set()

# These are categorization labels the bot assigns based on other information.

GITHUB_CATEGORY_LABELS = {
    "blended",
    "open-source-contribution",
}
