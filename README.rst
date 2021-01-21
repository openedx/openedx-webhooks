.. highlight: sh

Open edX Webhooks Handlers (and Other JIRA/GitHub Utilities)
============================================================

Webhooks for `Open edX`_ integrating `JIRA`_ and `Github`_. Designed to
be deployed at `Heroku`_.

`Access the app`_ at https://openedx-webhooks.herokuapp.com.

|Build Status| |Coverage Status| |Documentation badge|

Set Up Development Environment
------------------------------

Prerequisites
~~~~~~~~~~~~~

Make sure you've installed:

-  Python 2.7.x development environment (virtualenv strongly
   recommended)
-  `Heroku Command Line`_

   All ``heroku`` commands can be performed through the Heroku web-based
   dashboard as well, if you don't want to use the CLI.

Set up
~~~~~~

1. Log in using the email address and password you used when creating
   your Heroku account::

       heroku login

   Authenticating is required to allow both the ``heroku`` and ``git``
   commands to operate.

2. Add the Heroku app repo as a git remote::

       heroku git:remote -a openedx-webhooks-staging

3. Verify that the remote is added properly::

       git remote -v

   You should see output similar to::

       heroku  https://git.heroku.com/openedx-webhooks-staging.git (push)
       heroku  https://git.heroku.com/openedx-webhooks-staging.git (fetch)
       origin  git@github.com:edx/openedx-webhooks.git (fetch)
       origin  git@github.com:edx/openedx-webhooks.git (push)

Develop
-------

This app relies on the following addons from Heroku:

-  PostgreSQL
-  Redis
-  Papertrail
-  Scheduler

While it's possible to replicate the entire stack locally, it'll be
difficult to ensure consistent experience for each developer. Instead,
we utilize the `pipeline`_ facility offered by Heroku to handle our
development needs.

The general development cycle is:

Code → Deploy branch to staging → Test → Iterate

To deploy a local branch to staging::

    git push heroku [branch_or_tag_or_hash:]master

In most cases, to push your current working branch, use::

    git push heroku @:master

Once you're satisfied with your changes, go ahead and open a pull
request per normal development procedures.

Smoke test the deployment
~~~~~~~~~~~~~~~~~~~~~~~~~

Navigate to https://openedx-webhooks-staging.herokuapp.com to make sure
the app has started. If the URL is too hard to remember, you can also
use::

    heroku open

If the application isn't running, visit the `openedx-webhooks-staging
Resources`_ page to make sure there are dynos running.

.. _openedx-webhooks-staging Resources: https://dashboard.heroku.com/apps/openedx-webhooks-staging/resources


Run Tests
---------

::

    make install-dev-requirements
    make test

Deploy
------

In most cases, you'll want to deploy by promoting from staging to
production. The general workflow is:

Merge to ``master`` → Deploy ``master`` to staging → Test → Promote to
production

**Prior to the promotion**, make sure all the changes have been merged
to ``master``, and you've deployed the ``master`` branch successfully to
staging::

    git push heroku master

When you're ready to promote from staging to production::

    heroku pipelines:promote -r heroku

Ensure the same versions are deployed
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Make sure the same git commit is deployed to both environments. First
see what's deployed on staging::

    heroku releases -n 1

Then see what's deployed on production::

    heroku releases -a openedx-webhooks -n 1

Make sure the abbreviated git SHAs match.

Smoke test the deployment
~~~~~~~~~~~~~~~~~~~~~~~~~

Navigate to https://openedx-webhooks.herokuapp.com to make sure the app
has started. If the URL is too hard to remember, you can also use::

    heroku open -a openedx-webhooks


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

2021-01-21
~~~~~~~~~~

- Rescanning never considers pull requests created before 2018.  This is a
  quick fix to deal with contractor comments.

  Because we don't track when companies started and stopped being contractors,
  we can't decide now if a pull request should have had a contractor comment
  when it was created.

  The latest contractor comment on one of our pull requests was in December
  2017.  So don't consider pull requests that old.  Later we can implement a
  better solution if we need to rescan those old pull requests.

- Rescanning now has a dry-run mode which record what would have been done, but
  takes no action.

- Before-clauses in people.yaml are now handled differently.  Previously, only
  one before clause was found, the earliest one that applied to the date we're
  interested in.  Now, all before clauses that apply (with dates after the date
  we are interested in) are layered together starting with now and working
  back in time to build a dict of data.

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
.. _JIRA: https://openedx.atlassian.net
.. _Github: https://github.com/edx
.. _Heroku: http://heroku.com
.. _Access the app: https://openedx-webhooks.herokuapp.com
.. _Heroku Command Line: https://devcenter.heroku.com/articles/heroku-command-line
.. _pipeline: https://devcenter.heroku.com/articles/pipelines

.. |Build Status| image:: https://travis-ci.com/edx/openedx-webhooks.svg?branch=master
   :target: https://travis-ci.com/edx/openedx-webhooks
.. |Coverage Status| image:: http://codecov.io/github/edx/openedx-webhooks/coverage.svg?branch=master
   :target: http://codecov.io/github/edx/openedx-webhooks?branch=master
.. |Documentation badge| image:: https://readthedocs.org/projects/openedx-webhooks/badge/?version=latest
   :target: http://openedx-webhooks.readthedocs.org/en/latest/
