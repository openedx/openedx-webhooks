Details
=======

Here are the details of what the bot does.

.. _pr_to_jira:

Making a Jira issue for a pull request
--------------------------------------

The bot gets notifications from GitHub when a pull request is created in the
organizations and/or repos where it is configured.  It's currently configured
in the edx organization, and probably a few other places we have lost track of.

A number of aspects of the pull request are examined:

- The author is looked up in the contributors database
- The title of the pull request might have indicators

The bot has to choose:

- The Jira project to create the issue in,
- The initial status of the Jira issue,
- The Jira labels to apply to the issue,
- The GitHub labels to apply to the pull request.

Pull requests fall into a number of categories, which determine how it is
handled:

- If the author is marked as "internal" (an edX employee), the bot does
  nothing.

- If the author is marked as "contractor", the bot puts a comment on the pull
  request indicating that it doesn't know whether to make a Jira issue or not,
  with a link the author can use to make one.  The bot is done.

- If the title of the pull request indicates this is a blended project (with
  "[BD-XXX]" in the title), then this is a blended pull request.

- Otherwise, the author is checked for core committer status in the repo.  If
  so, this is a core commiter pull request.

- Otherwise, this is a regular pull request.

Now we can decide what to do:

- Create a Jira issue:

  - Blended pull requests use the BLENDED Jira project.

  - Others use OSPR.

  - The Jira ticket has these fields:

    - Issue type is "Pull Request Review".
    - Summary is the title of the pull request.
    - Description is the description of the pull request.
    - URL is the GitHub URL of the pull request.
    - PR Number is the number of the pull request.
    - Repo is the name of the repo (like "edx/edx-platform").
    - Contributor Name is the name of the author.
    - Customer is the author's institution, if one is present in people.yaml.
    - Blended Jira issues also:

      - have a link to their Blended epic
      - copy the "Platform Map Area (Levels 1 & 2)" field from the epic.

- Initial Jira status:

  - Core committer pull requests get "Open edX Community Review".

  - Blended pull requests get "Needs Triage".

  - For regular pull requests, if the author doesn't have a signed CLA, the
    initial status is "Community Manager Review".  If they do have a signed
    CLA, it is "Needs Triage".

- Labels:

  - Blended pull requests get "blended" applied as a GitHub label and Jira
    label.

  - Core committer pull requests get "core-commiter" as a Jira label. They get
    "core committer" and "open-source-contribution" as GitHub labels.

  - Regular pull requests get "open-source-contribution" as a GitHub label.

  - The initial Jira status is set as a GitHub label on the pull request.

- Initial bot comment:

  - All four kinds of pull requests (contractor, blended, core committer, and
    regular) get different comments.

  - If the user doesn't have a signed CLA, the bot adds a paragraph about
    needing to sign one.

  - If the user has a signed CLA, the bot adds an invisible "ok to test" to get
    the tests started.


Updating GitHub labels when Jira status changes
-----------------------------------------------

The bot gets notifications from Jira when issues in either the OSPR or BLENDED
project get updated.

If the change is a status change, the bot finds the pull request based on
fields in the issue. It removes the GitHub label for the old Jira status, and
adds the GitHub label for the new Jira status.
