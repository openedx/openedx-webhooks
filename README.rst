Open edX Webhooks Handlers (and Other JIRA/GitHub Utilities)
============================================================

Webhooks for `Open edX`_ integrating `JIRA`_ and `Github`_. Designed to
be deployed at `Heroku`_.

|Build Status| |Coverage Status| |Documentation badge|

Set Up Development Environment
------------------------------

Prerequisites
~~~~~~~~~~~~~

Make sure you've installed:

-  Python 2.7.x development environment (virtualenv strongly
   recommended)

   *Hint*: See `runtime.txt`_ for the exact version
-  `Heroku Command Line`_

Set up
~~~~~~

1. Log in using the email address and password you used when creating
   your Heroku account:

   .. code:: sh

       heroku login

   Authenticating is required to allow both the ``heroku`` and ``git``
   commands to operate.

2. Add the Heroku app repo as a git remote:

   .. code:: sh

       heroku git:remote -a openedx-webhooks-staging

3. Verify that the remote is added properly:

   .. code:: sh

       git remote -v

   You should see output similar to:

   .. code:: sh

       heroku  https://git.heroku.com/openedx-webhooks-staging.git (push)
       heroku  https://git.heroku.com/openedx-webhooks-staging.git (fetch)
       origin  git@github.com:edx/openedx-webhooks.git (fetch)
       origin  git@github.com:edx/openedx-webhooks.git (push)

Develop
-------

This app relies on the following addons from Heroku:

-  PostgreSQL
-  Redis
-  IronMQ
-  Papertrail
-  Scheduler

While it's possible to replicate the entire stack locally, it'll be
difficult to ensure consistent experience for each developer. Instead,
we utilize the `pipeline`_ facility offered by Heroku to handle our
development needs.

The general development cycle will be:

Code → Deploy branch to staging → Test → Iterate

To deploy a local branch to staging:

.. code:: sh

    git push heroku [branch_or_tag_or_hash:]master

Once you're satisfied with your changes, go ahead and open a pull
request per normal development procedures.

Run Tests
---------

.. code:: sh

    make install-requirements
    make test

Deploy
------

In most cases, you'll want to deploy by promoting from staging to
production.

.. code:: sh

    heroku pipelines:promote -r heroku

--------------

TODO
----

-  Describe the different processes that are run on Heroku
-  Make sure ``docs/`` is up to date

.. _Open edX: http://openedx.org
.. _JIRA: https://openedx.atlassian.net
.. _Github: https://github.com/edx
.. _Heroku: http://heroku.com
.. _runtime.txt: runtime.txt
.. _Heroku Command Line: https://devcenter.heroku.com/articles/heroku-command-line
.. _pipeline: https://devcenter.heroku.com/articles/pipelines

.. |Build Status| image:: https://travis-ci.org/edx/openedx-webhooks.svg?branch=master
   :target: https://travis-ci.org/edx/openedx-webhooks
.. |Coverage Status| image:: http://codecov.io/github/edx/openedx-webhooks/coverage.svg?branch=master
   :target: http://codecov.io/github/edx/openedx-webhooks?branch=master
.. |Documentation badge| image:: https://readthedocs.org/projects/openedx-webhooks/badge/?version=latest
   :target: http://openedx-webhooks.readthedocs.org/en/latest/
