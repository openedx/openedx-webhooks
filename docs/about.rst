What This App Does
==================

This app is a bot installed as a webhook for GitHub and Jira to automate
aspects of the Open edX contribution flow.

Here is an overview of what it does.

GitHub PR to Jira issue
-----------------------

The most well-known need this bot serves is automatically creating Jira issues
for incoming GitHub pull requests. It detects the author of the pull request,
and determines whether that author is an edX employee
or someone in the Open edX community. If the author
is an edX employee, the pull request is utterly ignored.
Otherwise, the bot automatically makes an OSPR issue for the
pull request, and adds a comment to the pull request that links to the OSPR
issue.

The details of this process are explained in :ref:`pr_to_jira`.

Synchronize Jira issue states with GitHub PR labels
---------------------------------------------------

Issues in Jira can go through many states that represent the progress of the
review process. Many people in the open source community don't want to look
at the Jira issue, and prefer to keep all their activity on GitHub. As a result,
any time an issue is transitioned from one state to another, the bot checks
to see if the issue is an OSPR issue. If so, it modifies the labels on GitHub
to reflect the state of the OSPR issue on Jira.
