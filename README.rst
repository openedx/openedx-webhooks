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

To install the webhook, use the ``/github/install`` page in the application
itself, or do it manually:

On GitHub, visit the repo webhooks
(``https://github.com/<ORG>/<REPO>/settings/hooks``) or organization webhooks
(``https://github.com/organizations/<ORG>/settings/hooks``) page.

Create or edit a webhook.

https://openedx-webhooks.herokuapp.com/github/pr
    content type: application/json
    - Pull Requests

https://openedx-webhooks.herokuapp.com/github/hook-receiver
    content type: application/json
    - Issue comments
    - Pull requests
    - Pull request reviews
    - Pull request review comments



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

.. |Build Status| image:: https://travis-ci.org/edx/openedx-webhooks.svg?branch=master
   :target: https://travis-ci.org/edx/openedx-webhooks
.. |Coverage Status| image:: http://codecov.io/github/edx/openedx-webhooks/coverage.svg?branch=master
   :target: http://codecov.io/github/edx/openedx-webhooks?branch=master
.. |Documentation badge| image:: https://readthedocs.org/projects/openedx-webhooks/badge/?version=latest
   :target: http://openedx-webhooks.readthedocs.org/en/latest/
