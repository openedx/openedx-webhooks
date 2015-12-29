What This App Does
==================

This app is meant to serve multiple uses, doing any automated task
that requires linking up webhooks for JIRA, GitHub, and any other online system
that edX uses. It currently does the following things:

GitHub PR to JIRA issue
-----------------------

The most well-known need this bot serves is automatically creating JIRA issues
for incoming GitHub pull requests. It detects the author of the pull request,
and determines whether that author is an edX employee, a contractor that often
does work for edX, or someone else in the Open edX community. If the author
is an edX employee, the pull request is utterly ignored. If the author is a
contractor that often does work for edX, the bot adds a comment to the pull
request, asking the contractor to make an OSPR issue for their pull request
if necessary. Otherwise, the bot automatically makes an OSPR issue for the
pull request, and adds a comment to the pull request that links to the OSPR
issue.

"Force" process a GitHub pull request
-------------------------------------

Sometimes, a pull request made by an edX employee or a contractor needs an OSPR
issue. The bot has an interface where you can ask it to process a specific
pull request, and it will do so even if the author is an edX employee or
a contractor.

Synchronize JIRA issue states with GitHub PR labels
---------------------------------------------------

Issues in JIRA can go through many states that represent the progress of the
review process. Many people in the open source community don't want to look
at the JIRA issue, and prefer to keep all their activity on GitHub. As a result,
any time an issue is transitioned from one state to another, the bot checks
to see if the issue is an OSPR issue. If so, it modifies the labels on GitHub
to reflect the state of the OSPR issue on JIRA.

Push JIRA issues out of "Needs Triage"
--------------------------------------

Anyone in the Open edX community has permission to create JIRA issues, but the
development teams at edX need to be able to avoid clutter on their respective
JIRA projects. As a result, the "Needs Triage" state is intended for issues
created by the Open edX community -- these issues may be created in the wrong
project, have confusing content, or simply be inappropriate for JIRA (such as
support requests). Issues in the "Needs Triage" state are invisible to most
teams, unless they specifically choose to see those issues.

Due to JIRA's limited workflow capabilities, we can't tell JIRA to make issues
start in different states depending on who made the issue. That's where this
bot comes in. Every time an issue is created, it starts in the "Needs Triage"
state. JIRA alerts this bot that a new issue has been created, and this bot
examines the issue to see who the creator is. If the creator is an edX employee,
the bot moves the ticket out of "Needs Triage" and into a different state. If
the creator is not an edX employee, the bot leaves the issue in "Needs Triage",
and an edX employee will have to look at the issue, triage it, and move it
out of that state manually.

Place JIRA users into groups
----------------------------

JIRA has user groups, which can be assigned various different permission levels.
For example, the "edx-employees" group has many permissions assigned to it.
However, JIRA is really bad at automated user management, and it can't
automatically categorize users into groups. Once again, this bot can make up
for JIRA's shortcomings.

There is a function where the bot will scan *all* the users on JIRA based on their
email address, and categorize the user into a group based on that email. For
example, users with an ``@edx.org`` email address will be placed into the
"edx-employees" group. This function is automatically run once every hour, so
that as new employees join edX, they are automatically placed into the correct
group on JIRA.

Check contributors on GitHub
----------------------------

The bot can identify users that have made commits on a repository, but are
not listed in the AUTHORS file for that repository.

Install GitHub webhooks
-----------------------

GitHub will not inform the bot of events happening in a repository unless a
webhook exists for the bot on that repository. The bot has the ability to
install this webhook automatically for a given repository, but the GitHub user
that the bot runs under needs admin permissions to that repository for this
to work. These permissions are managed from within GitHub.
