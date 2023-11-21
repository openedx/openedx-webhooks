Installation
============

Make an app on Heroku
---------------------
You can use the free tier if you want, but then the application won't run
all the time. If you need it to run all the time, you'll need to pay.

Install Add-ons
~~~~~~~~~~~~~~~

This project uses:

* `Heroku Redis <https://elements.heroku.com/addons/heroku-redis>`_
* `Heroku Scheduler <https://elements.heroku.com/addons/scheduler>`_

This project also uses `Sentry <https://getsentry.com>`_ as a monitoring system,
but doesn't use the official Sentry add-on for Heroku. Sentry offers a free
tier which is enough for our needs, but their Heroku add-on doesn't support
the free tier. Instead, we set the ``SENTRY_DSN`` config variable in the project
settings, and log in on the Sentry website to view the tracebacks.

This project uses `Celery`_ for managing asynchronous tasks.
Celery needs a "`message broker`_" and a "`result backend`_" to run.
Celery recommends using `RabbitMQ`_ as a message broker, but we had problems
with a few RabbitMQ providers on Heroku. Instead, we switched to `Redis`_,
which seems to work better. We can always switch back to RabbitMQ in the future,
or switch to a different message broker if necessary. Celery recommends using
`Redis`_ as a result backend, which is why we're using the Heroku Redis add-on.

.. _Celery: http://www.celeryproject.org/
.. _message broker: http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html#choosing-a-broker
.. _result backend: http://docs.celeryproject.org/en/latest/userguide/tasks.html#task-result-backends
.. _RabbitMQ: https://www.rabbitmq.com/
.. _Redis: http://redis.io/

Flask Secret Key
~~~~~~~~~~~~~~~~

Generate a secret key for Flask, so that it can save information into the session:

.. code-block:: bash

  $ export FLASK_SECRET_KEY=`python -c "import os; print(os.urandom(24))"`
  $ heroku config:set FLASK_SECRET_KEY=$FLASK_SECRET_KEY


Set Up Authentication Tokens
----------------------------

GitHub
~~~~~~

#. Create a GitHub personal access token for the bot user.  It will need these
   scopes: admin:repo_hook, repo, user:email, workflow, write:org.  Specify it
   as a Heroku setting:

   .. code-block:: bash

       $ heroku config:set GITHUB_PERSONAL_TOKEN=my-pat

#. A GitHub project will be needed for blended pull requests, and another for
   other OSPRs.  Specify them as ``org:number``:

   .. code-block:: bash

      $ heroku config:set GITHUB_OSPR_PROJECT=openedx:19
      $ heroku config:set GITHUB_BLENDED_PROJECT=edx:9


Jira
~~~~

The bot can be configured to work with many Jira servers.

The JIRA_INFO_FILE setting specifies a YAML file name in openedx-webhooks-data repo.
For a hypothetical organization named MegaCorp, it might look like this:

    .. code-block:: yaml

        # The key is a short name that will be looked up from the label.
        # This configures the settings for a "jira:mega" label.
        Mega:
            # The URL of the Jira instance.
            server: https://megacorp.atlassian.net
            # The email address and user token for the account that will make
            # Jira issues.  Be sure it has the privileges needed.
            email: bot-account@megacorp.com
            token: 84Ma................z1FC
            # The URL of a YAML file mapping repos to Jira project details.
            mapping: https://raw.githubusercontent.com/megacorp/.github/HEAD/jira-mapping-prod.yaml
            # A textual description of the Jira instance, to use in comments.
            # It will be used in a sentence like this:
            # "I've created issue PROJ-123 in {description}."
            description: the private MegaCorp Jira
            # The person to contact for updating the Jira project settings.
            # It will be used like: "Contact {contact} for help."
            contact: Wes Admin (wes@megacorp.com)

The mapping file is YAML that maps a repo name to two pieces of information: a
Jira project and an issue type to create in that project. The file can be at
any URL.  As shown above, a raw GitHub URL is convenient.  The reason this is
separate from other config is so that this mapping file can be managed by Megacorp
while the info file above with credentials in it is managed by the team running
openedx-webhooks. The file specifies repos, possibly with wildcards, and for each
provides the project and issue type to use:

    .. code-block:: yaml

        defaults:
          type: Task
        repos:
          # The repo name is an org/repo string from GitHub.
          - name: openedx/edx-platform
            project: ARCHBOM
          - name: nedbat/webhook-testing    # For Ned to test the bot on stage
            project: NEDBAT
            type: TestIssue
          # The repo name can have shell-like wildcards
          - name: openedx/*
            project: OPENSOURCE
          - name: *
            project: ENGR


Deploy
------

#. Set up your Heroku git remote to point to your Heroku application

#. ``git push heroku``

#. Visit your website -- it should load!

#. Enjoy the sweet, sweet taste of API integration


Recurring Tasks
---------------

Some of the tasks that our webhooks bot does are meant to be done on a regular,
recurring basis. For example, :func:`~openedx_webhooks.views.jira.jira_rescan_users`
should be run every hour or so. To do that, we use the `Heroku Scheduler`_
add-on, which executes whatever code you want it to at whatever interval you
specify.

Go to your Heroku project's dashboard, and click on the "Heroku Scheduler" add-on
you installed. That will open a new page where you can manage scheduled jobs.
Add one job to hit the ``/jira/user/rescan`` endpoint with a POST request
once per hour. If your app is named "openedx-webhooks", the command you want
to run is:

.. code-block:: bash

    $ curl -X POST https://openedx-webhooks.herokuapp.com/jira/user/rescan
