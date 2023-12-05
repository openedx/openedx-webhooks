Details
=======

Here are the details of what the bot does.

.. _pr_to_jira:

When a pull request is opened
-----------------------------

The bot gets notifications from GitHub when a pull request is created in the
organizations and/or repos where it is configured.  It's currently configured
in the edx and openedx organizations.

A number of aspects of the pull request are examined:

- The author is looked up in the contributors database
- The title of the pull request might have indicators

The bot has to choose:

- The GitHub labels to apply to the pull request.

Pull requests fall into a number of categories, which determine how it is
handled:

- If the author is "internal" to the pull request's GitHub org (as determined
  by the author's institution affiliation, and the institution's
  "internal-ghorgs" setting in orgs.yaml), the bot only applies the CLA check.
  No comments are put on the pull request, and no Jira ticket is created.

- If the title of the pull request indicates this is a blended project (with
  "[BD-XXX]" in the title), then this is a blended pull request.

- Otherwise, this is a regular pull request.

Additionally, if the pull request is in draft status, or has "WIP" in the
title, it is a draft pull request.

Now we can decide what to do:

- Initial status:

  - Blended pull requests get "Needs Triage".

  - For regular pull requests, if the author doesn't have a signed CLA, the
    initial status is "Community Manager Review".  If they do have a signed
    CLA, it is "Needs Triage".

Draft pull requests start with a status of "Waiting on Author".  The initial
status determined above will be set once the pull request is no longer a
draft.

- Labels:

  - Blended pull requests get "blended" applied as a GitHub label.

  - Regular pull requests just get "open-source-contribution" as a GitHub label.

  - The initial status is set as a GitHub label on the pull request.

- Initial bot comment:

  - Each kind of pull request (blended and regular) gets different comments.

  - If the user doesn't have a signed CLA, the bot adds a paragraph about
    needing to sign one.

- Other information:

  - A GitHub commit status called "openedx/cla" is added to the latest commit.
    This is applied to all pull requests, even ones by authors internal to the
    pull request's organization.


When a pull request is closed
-----------------------------

On internal pull requests, the bot leaves a comment asking the author to
complete a survey about the pull request.

When a pull request is being closed, it will be considered an internal pull
request if it has no "open-source-contribution" label, on the assumption that
it was processed when it was opened, so the lack of a label means the author
was internal at the time the pull request was created.


When a pull request is re-opened
--------------------------------

The bot deletes the "please complete a survey" comment that was added when the
pull request was closed.


Adding pull requests to GitHub projects
---------------------------------------

The bot will add new pull requests to GitHub projects.  Projects are specified
with a string like "openedx:23" meaning `project number 23`_ in the openedx
organization.

.. _project number 23: https://github.com/orgs/openedx/projects/23

- Regular non-internal pull requests get added to the project specified in the
  GITHUB_OSPR_PROJECT setting.

- Blended pull requests get added to the project specified in the
  GITHUB_BLENDED_PROJECT setting.

- Individual repos can specify other projects that external non-draft pull
  requests should be added to.  The projects are listed in an annotation in
  their catalog-info.yaml file:

  .. code-block:: yaml

      annotations:
        # This can be multiple comma-separated projects.
        openedx.org/add-to-projects: "openedx:23"

The bot never removes pull requests from projects.


Making a Jira issue for a pull request
--------------------------------------

The bot used to automatically make Jira issues for pull requests, but no longer
does.  Now a Jira issue will be created if a specific label is added to the
pull request.

The bot is configured to know about a small handful of Jira servers, each with
a short "nickname".  If you add a label of ``jira:xyz`` to a pull request, the
bot will create a Jira issue in the Jira server with the "xyz" nickname.

Each Jira server can specify a mapping of repos to other Jira details such as
the Jira project for the issue, and the issue type to create.

Jira issues created this way will have a "from-GitHub" Jira label applied.
