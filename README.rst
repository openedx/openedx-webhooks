.. highlight: sh

Open edX Webhooks Handlers (and Other JIRA/GitHub Utilities)
============================================================

Webhooks for `Open edX`_ integrating JIRA and GitHub. Designed to
be deployed at `Heroku`_.

`Access the app`_ at https://openedx-webhooks.herokuapp.com.

|Build Status| |Coverage Status| |Documentation badge|

Set Up Development Environment
------------------------------

Prerequisites
~~~~~~~~~~~~~

Make sure you've installed:

-  Python 3.12.x development environment
   (virtualenv strongly recommended)
-  `Heroku Command Line`_

   All ``heroku`` commands can be performed through the Heroku web-based
   dashboard as well, if you don't want to use the CLI.

Set up
~~~~~~

Log in using the email address and password you used when creating
your Heroku account::

    make deploy-configure

Authenticating is required to allow both the ``heroku`` and ``git``
commands to operate.

Alternatively, to authenticate with SSH keys::

    make deploy-configure DEPLOY_USE_SSH=true

You should see output similar to::

    heroku  https://git.heroku.com/openedx-webhooks-staging.git (push)
    heroku  https://git.heroku.com/openedx-webhooks-staging.git (fetch)
    origin  git@github.com:edx/openedx-webhooks.git (fetch)
    origin  git@github.com:edx/openedx-webhooks.git (push)

Develop
-------

This app relies on the following addons from Heroku:

-  Redis
-  Papertrail
-  Scheduler

While it's possible to replicate the entire stack locally, it'll be
difficult to ensure consistent experience for each developer. Instead,
we utilize the `pipeline`_ facility offered by Heroku to handle our
development needs.

The general development cycle is:

Code → Deploy branch to staging → Test → Iterate

To deploy your current working branch to staging::

    make deploy-stage-branch

To deploy an arbitrary branch::

    make deploy-stage-branch DEPLOY_STAGING_BRANCH=feat/my-branch

Once you're satisfied with your changes, go ahead and open a pull
request per normal development procedures.

Smoke test the deployment.

If the application isn't running, visit the `openedx-webhooks-staging
Resources`_ page to make sure there are dynos running.

.. _openedx-webhooks-staging Resources: https://dashboard.heroku.com/apps/openedx-webhooks-staging/resources


Run Tests
---------

::

    make install-dev-requirements test

If you are testing a change to `repo-tools-data-schema`_, you need to coordinate
changes in both repos:

- Name your branch here the same as your branch in repo-tools-data-schema.

- Be sure your changes in repo-tools-data-schema are pushed to your branch on
  GitHub.

- Run ``make testschema`` to install your branch of repo-tools-data-schema in
  this virtualenv.

- Run tests here as usual.

.. _repo-tools-data-schema: https://github.com/openedx/repo-tools-data-schema

Deploy
------

In most cases, you'll want to deploy by promoting from staging to
production. The general workflow is:

Merge to ``master`` → Deploy ``master`` to staging → Test → Promote to
production

**Prior to the promotion**, make sure all the changes have been merged
to ``master``, and you've deployed the ``master`` branch successfully to
staging::

    make deploy-stage

When you're ready to promote from staging to production::

    make deploy-prod

Make sure the same git commit is deployed to both environments.

Make sure the abbreviated git SHAs match.

Smoke test the deployment.


Other things to know
--------------------

**This should no longer be an issue as of July 9th, 2018.**

If you re-process pull requests, an unfortunate thing can happen: it will find
stale pull requests that were written by edX employees who have now left.  The
bot will see that the author has no contributor agreement, and will make a new
JIRA issue for the pull request.  This is needless noise.

The bot looks for comments it wrote that have a JIRA issue id in them.  You can
leave the bot comment on the stale pull request so that at least it won't happen
again in the future.


Configuring a webhook
---------------------

On GitHub, visit the repo webhooks
(``https://github.com/<ORG>/<REPO>/settings/hooks``) or organization webhooks
(``https://github.com/organizations/<ORG>/settings/hooks``) page.

Create or edit a webhook.

- Payload URL: https://openedx-webhooks.herokuapp.com/github/hook-receiver
- Content type: application/json
- Secret: same as setting GITHUB_WEBHOOK_SECRET in Heroku
- Events:
    - Issue comments
    - Pull requests
    - Pull request reviews
    - Pull request review comments



Changelog
---------

Unreleased
~~~~~~~~~~

See the fragment files (if any) in the changelog.d directory.

.. scriv-insert-here

2025-02-24
~~~~~~~~~~

- Add support for Python 3.12

2023-12-07
~~~~~~~~~~

- When a pull request is closed, if it doesn't have a
  "open-source-contribution" label on it, it is considered an internal pull
  request.  We assume that it was processed when it was opened, and since it
  didn't get the label then, the author must have been internal at the time.

2023-11-27
~~~~~~~~~~

- Now issues created in Jira will have a label of "from-GitHub" on them. Closes
  `issue 279`_.

- Two possible errors with "jira:foo" labels now create bot comments so people
  understand why there's no Jira issue. Closes `issue 280`_.

- Fix: we no longer comment twice on a pull request closed with a comment.
  Closes `issue 277`_.

.. _issue 277: https://github.com/openedx/openedx-webhooks/issues/277
.. _issue 279: https://github.com/openedx/openedx-webhooks/issues/279
.. _issue 280: https://github.com/openedx/openedx-webhooks/issues/280


2023-11-03
~~~~~~~~~~

- Don't add a "no contributions accepted" comment if the pull request is being
  closed. It's needlessly discouraging. Fixed #273.

2023-10-31
~~~~~~~~~~

- Adding a label like ``jira:xyz`` to a pull request will look in a private
  registry of Jira servers for one nicknamed ``xyz``, and then create a Jira
  issue there to correspond to the pull request.

2023-09-13
~~~~~~~~~~

- The CLA check used to fail if a pull request had more than 100 commits.  Now
  the head sha is retrieved directly without listing all commits, so the number
  is irrelevant.

2023-08-30
~~~~~~~~~~

- Adding a comment to pull request now re-runs the checks and updates the state
  of the pull request.  Previously, we'd edit the title of the PR to trigger
  updates.

2023-08-11
~~~~~~~~~~

- Removed: the bot no longer understands the past state of users.  This data
  hasn't been maintained for the last few years.  There's no point relying on
  stale data, so the capability is removed.

- Removed: any understanding of who is a core contributor.  The bot no longer
  makes comments or labels particular to core contributors. `Issue 227`_.

.. _issue 227: https://github.com/openedx/openedx-webhooks/issues/227

- Removed: we no longer read people.yaml.

- Removed: we no longer add "jenkins ok to test" to start testing, since that
  comment was only read by Jenkins, which we no longer use.

2023-08-03
~~~~~~~~~~

- Jira authentication now uses the JIRA_USER_EMAIL and JIRA_USER_TOKEN
  environment variables.  OAuth authentication is removed. These settings are
  now obsolete and can be deleted:

  - DATABASE_URL
  - GITHUB_OAUTH_CLIENT_ID
  - GITHUB_OAUTH_CLIENT_SECRET
  - JIRA_OAUTH_CONSUMER_KEY
  - JIRA_OAUTH_RSA_KEY
  - SQLALCHEMY_DATABASE_URI

- Stopped the bot from updating a repository's labels based on ``labels.yaml``, as this is now handled by the `repo_checks <https://github.com/openedx/repo-tools/tree/master/edx_repo_tools/repo_checks>`_ tool. The ``labels.yaml`` file is now unused and can be safely deleted from any openedx-webhooks data repositories.

- Stopped the bot from adding the ``core committer`` GitHub label to pull requests to repos on which the bot believes the author to have write access. The bot's data source for repository access, ``people.yaml``, is outdated, we do not yet have a strategy for keeping it updated. Until further notice, coding Core Contributors are asked to add the ``core contributor`` label to their pull requests manually.

2023-03-03
~~~~~~~~~~

- Removed the code that used the now-obsolete ``internal`` setting in
  orgs.yaml.

- Tweaked the CLA messages.

2023-03-02
~~~~~~~~~~

- The "internal" setting is being replaced by an "internal-ghorgs" list on an
  institution.  A pull request is now internal if the author's associated
  institution (in orgs.yaml) has the org the PR is being made to as an
  internal-ghorgs org.  The old "internal" setting is still used, but we'll be
  deleting it once the new code is in place.

2023-01-30
~~~~~~~~~~

- Added: contribution pull requests will be added to GitHub projects if the
  base repo says to by adding an "openedx.org/add-to-projects" annotation in
  its catalog-info.yaml file.

2022-07-21
~~~~~~~~~~

- Adding a pull request to a project could fail if the two are in different
  GitHub orgs (like edx and openedx).  This failure used to stop the bot from
  making further changes, but now we log the exception and continue.

2022-06-13
~~~~~~~~~~

- Removing the JIRA_SERVER setting will disable Jira access for the bot. No Jira
  issues will be created or updated.

2022-06-03
~~~~~~~~~~

- Blended pull requests now go into a separate project, specified with
  the GITHUB_BLENDED_PROJECT setting.

2022-06-01
~~~~~~~~~~

- The JIRA server is now configurable with the JIRA_SERVER environment
  variable.

- New external pull requests will be added to a GitHub project.  The project is
  configurable with the GITHUB_OSPR_PROJECT environment variable.

- Removed mention of unused JIRA credentials JIRA_ACCESS_TOKEN and
  JIRA_ACCESS_TOKEN_SECRET.

2022-04-06
~~~~~~~~~~

- Repos with more than 30 labels might not have properly labelled pull requests
  that transitioned into late-alphabet statuses (like Open edX Community
  Review).  This is now fixed.

2022-04-05
~~~~~~~~~~

- Load yaml and csv data files from the `openedx/openedx-webhooks-data` repo.

2022-03-25
~~~~~~~~~~

- Pull requests can now be closed and re-opened.  When the pull request is
  re-opened, the survey comment that was added on closing is deleted.  The Jira
  ticket is returned to the state it was in before the pull request was closed.

2022-01-27
~~~~~~~~~~

- Removed the code that handled "contractor" pull requests, where the bot
  couldn't know if an OSPR ticket was needed or not.

- The CLA check is now applied to all pull requests, even edX internal ones.

2021-12-20
~~~~~~~~~~

- The bot now ignores any private repo in the edx organization.

2021-12-17
~~~~~~~~~~

- We no longer use OAuth authentication for GitHub.  All access is with a
  personal access token.

- The bot now depends on a csv generated by Salesforce to inform which users
  have signed the Contributor License Agreement (CLA)

- After processing a pull request, the GitHub rate limit is checked and logged:
    Rate limit: 5000, used 29, remaining 4971. Reset is at 2021-12-16 23:26:48

- The "needs CLA" message now includes the possibility that you've signed
  before and need to re-sign.

2021-09-29
~~~~~~~~~~

- Removed the NEED-CLA label. We have a check now, which is better.

2021-09-14
~~~~~~~~~~

- Due to an internal refactoring, now rescanning pull requests will add the
  end-of-pull-request survey comment if needed.

- Four Jira fields are no longer updated:
    'Github PR Last Updated At'
    'Github PR Last Updated By'
    'Github Latest Action'
    'Github Latest Action by edX'

2021-09-13
~~~~~~~~~~

- A GitHub check indicates whether the author has a contributor agreement or
  not.

2021-09-02
~~~~~~~~~~

- Fix an assertion error that could happen if a pull request had no body
  (description).  The assertion was:

      File "/app/openedx_webhooks/tasks/jira_work.py", line 117, in update_jira_issue
        assert fields

- Change error handling so that more actions can complete even if one fails.

2021-08-30
~~~~~~~~~~

- Removed one setting: JIRA_OAUTH_PRIVATE_KEY, which was just JIRA_OAUTH_RSA_KEY base64 encoded.

2021-08-18
~~~~~~~~~~

- fix: all UI pages are now protected with basic auth.

2021-02-25
~~~~~~~~~~

- Update the CLA link to go to https://openedx.org/cla, which currently
  redirects to our new Docusign form.  If we have to change the form in the
  future, we can change the redirect on openedx.org.

2021-01-22
~~~~~~~~~~

- When considering a pull request, we won't update the Jira extra fields if
  none of our desired fields are different.  We used to update a Jira issue if
  (for example) it had platform map info, but we didn't want to add platform
  map info.

2021-01-21
~~~~~~~~~~

- More control over rescanning:

  - You can provide an earliest and latest date to consider.  Only pull
    requests created within that window will be rescanned.

    Rescanning never considers pull requests created before 2018.  This is a
    quick fix to deal with contractor comments.

    Because we don't track when companies started and stopped being
    contractors, we can't decide now if a pull request should have had a
    contractor comment when it was created.

    The latest contractor comment on one of our pull requests was in December
    2017.  So don't consider pull requests that old.  Later we can implement a
    better solution if we need to rescan those old pull requests.

  - Rescanning now has a dry-run mode which records what would have been done,
    but takes no action.

- Before-clauses in people.yaml are now handled differently.  Previously, only
  one before clause was found, the earliest one that applied to the date we're
  interested in.  Now, all before clauses that apply (with dates after the date
  we are interested in) are layered together starting with now and working
  back in time to build a dict of data.

- Updates to Jira tickets will try not to notify users unless the title or body
  (summary or description) change.  This requires that the bot Jira user be an
  administrator of the projects it is updating.

2021-01-08
~~~~~~~~~~

- Rescanning changes:

  - Now you have the option to include closed pull requests.

  - Pull requests are fetched in full to ensure all the needed fields will be
    available.

2020-11-24
~~~~~~~~~~

- The bot used to create a Jira issue to replace an issue that had been
  deleted.  This interfered with rescanning, so the bot no longer does this.
  If a Jira issue mentioned in the bot comment has been deleted, it will not be
  recreated.

2020-10-29
~~~~~~~~~~

- The number of lines added and deleted by a pull request are recorded in
  custom Jira fields.

2020-10-15
~~~~~~~~~~

- Core Committer pull requests now start with a Jira status of "Waiting on
  Author" rather than "Open edX Community Review".

2020-09-23
~~~~~~~~~~

- Draft pull requests start with a status of "Waiting on Author".  Once the
  pull request is no longer a draft, the status is set to the initial status it
  would have originally had.

2020-08-08
~~~~~~~~~~

- BUG: if the PR description was edited, the Jira issue status would be
  incorrectly reset to its initial value [OPENEDX-424].  This is now fixed.

2020-08-07
~~~~~~~~~~

- When a core committer merges a pull request, the bot will add a comment
  pinging the committer's edX champions to let them know the merge has
  happened.

- BUG: previously the bot could clobber ad-hoc labels on Jira issues when it
  set its own labels.  This is now fixed.  The bot will preserve any labels it
  didn't make.

- Removed the code that managed webhooks in repos.

- Refactored some code that handles pull requests being closed, so now it
  operates on any change to the pull request.  The behavior should be the same,
  except now if a pull request is closed or merged after the Jira issue has
  been manually deleted, the bot will create a new issue so that it can mark it
  Rejected or Merged.


2020-07-24
~~~~~~~~~~

- BUG: previously, the bot might change GitHub labels and incorrectly drop
  ad-hoc labels that people had put on the pull request.  This is now fixed.


2020-07-23
~~~~~~~~~~

- GitHub very occasionally sends us a pull request event, but then serves us a
  404 error when we ask it about the pull request.  Now the bot will retry GET
  requests that return 404, to give GitHub a chance to get its act together.

- BUG: when a pull request was edited, the associated Jira issue would be reset
  to its initial status.  This is now fixed: the Jira status is unchanged.


2020-07-21
~~~~~~~~~~

- Previously, if an OSPR issue had been manually moved to BLENDED, and then the
  title of the pull request amended to have "[BD-xx]", the bot would try and
  fail to delete the moved issue.  Now it understands the move, and doesn't
  try to delete the original issue.  It also updates the issue with Blended
  information.


2020-07-20
~~~~~~~~~~

- Changes to the title or description of a pull request are copied over to the
  associated Jira issue to keep them in sync.

- If a change to a pull request requires a different Jira issue, the old issue
  is deleted, and a new one made.  For example, if a blended pull request
  doesn't have "[BD-xx]" in the title, an OSPR issue gets made initially.
  Now when the developer updates the title, the OSPR issue is deleted, and a
  new BLENDED issue is created for it.


2020-07-14
~~~~~~~~~~

- The "expires_on" key in people.yaml is officially obsolete, and no longer
  interpreted.

- Some incorrect CLA logic was fixed. An entry in people.yaml with no
  "expires_on" key would be considered to have a signed CLA, even if the
  agreement was "none".


2020-07-02
~~~~~~~~~~

- If an opened pull request has a CLA, then the bot will comment "jenkins ok to
  test" on it to get the tests started automatically.


2020-07-01
~~~~~~~~~~

- Blended workflow: if "[BD-XX]" is found in the title of an opened pull
  request, then the Jira ticket will be in the BLENDED project, with links to
  the correct epic, etc.


2020-06-25
~~~~~~~~~~

- Core committer logic has to be particular to specific repos, it's not a
  blanket right.  Now "committer" isn't a simple boolean, it's an object with
  subkeys: "repos" is a list of repos the user can commit to, and "orgs" is a
  list of GitHub organizations the user can commit to (any repo).


2020-06-24
~~~~~~~~~~

- Slight change to people.yaml schema: "internal:true" is used to indicate edX
  people (or Arbisoft).  The "committer:true" flag indicates core committers.

- Core committer pull request handling: a different welcome message is used,
  OSPR issues are started in the "Open edX Community Review" status, and "core
  committer" GitHub and Jira labels are applied.


2020-06-19
~~~~~~~~~~

- We used to have two GitHub webhooks.  They have been combined.  Only
  /github/hook-receiver is needed now.  The obsolete /github/pr endpoint still
  exists just to log unneeded webhook action so we can fix the GitHub
  configuration.


2020-06-15
~~~~~~~~~~

- Labels in GitHub repos are synchronized from repo-tools-data/labels.yaml
  before any labels are adjusted in the repo.

- Data read from repo-tools-data (people.yaml, label.yaml) is only cached for
  15 minutes. It used to be until the bot was restarted.


2020-06-08
~~~~~~~~~~

- Pull requests that need a CLA signed now create Jira tickets in the
  "Community Manager Review" status.


TODO
----

-  Describe the different processes that are run on Heroku
-  Describe how to access logs
-  Make sure ``docs/`` is up to date

.. _Open edX: http://openedx.org
.. _Heroku: http://heroku.com
.. _Access the app: https://openedx-webhooks.herokuapp.com
.. _Heroku Command Line: https://devcenter.heroku.com/articles/heroku-command-line
.. _pipeline: https://devcenter.heroku.com/articles/pipelines

.. |build-status| image:: https://github.com/openedx/openedx-webhooks/workflows/Python%20CI/badge.svg?branch=master
   :target: https://github.com/openedx/openedx-webhooks/actions?query=workflow%3A%22Python+CI%22
.. |Coverage Status| image:: http://codecov.io/github/edx/openedx-webhooks/coverage.svg?branch=master
   :target: http://codecov.io/github/edx/openedx-webhooks?branch=master
.. |Documentation badge| image:: https://readthedocs.org/projects/openedx-webhooks/badge/?version=latest
   :target: http://openedx-webhooks.readthedocs.org/en/latest/
