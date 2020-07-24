"""
To properly manipulate labels, we need to know which labels are controlled
by which authority. This is that information.
"""

# These are labels that correspond to Jira statuses.  Only one of them should
# be used at a time.

STATUS_LABELS = {
    "architecture review",
    "awaiting prioritization",
    "blocked by other work",
    "changes requested",
    "community manager review",
    "engineering review",
    "merged",
    "needs triage",
    "open edx community review",
    "product review",
    "rejected",
    "waiting on author",
}

# These are categorization labels the bot assigns based on other information.

CATEGORY_LABELS = {
    "blended",
    "core committer",
    "open-source-contribution",
}
