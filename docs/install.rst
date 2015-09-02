Installation
============

Make an app on Heroku
---------------------
Don't worry, it's free for one dyno.

Install Add-ons
~~~~~~~~~~~~~~~

This project uses:

* `Heroku Postgres <https://addons.heroku.com/heroku-postgresql>`_
* `Heroku Redis <https://addons.heroku.com/heroku-redis>`_
* `RabbitMQ Bigwig <https://addons.heroku.com/rabbitmq-bigwig>`_
* `Sentry <https://addons.heroku.com/sentry>`_

Flask Secret Key
~~~~~~~~~~~~~~~~

Generate a secret key for Flask, so that it can save information into the session:

.. code-block:: bash

  $ export FLASK_SECRET_KEY=`python -c "import os; print(os.urandom(24))"`
  $ heroku config:set FLASK_SECRET_KEY=$FLASK_SECRET_KEY

Setup OAuth
-----------

JIRA
~~~~

OAuth authentication for JIRA requires a RSA keypair. To set this up:

1.  Run ``openssl genrsa -out jira.pem``. This will generate a private key.
2.  Run ``openssl rsa -in jira.pem -pubout -out jira.pub``. This will generate the
    public key.
3.  Generate a random string to serve as the consumer key. For example, run
    ``python -c "import uuid; print(uuid.uuid4().hex)" > jira.uuid``.
4.  Configure an Application Link in JIRA. The consumer key is the contents
    of ``jira.uuid``, and the public key is the contents of ``jira.pub``.
5.  Set RSA key and consumer key in Heroku environment:

    .. code-block:: bash

        $ export JIRA_OAUTH_RSA_KEY="$(<jira.pem)"
        $ export JIRA_OAUTH_CONSUMER_KEY="$(<jira.uuid)"
        $ heroku config:set JIRA_OAUTH_RSA_KEY=$JIRA_OAUTH_RSA_KEY
        $ heroku config:set JIRA_OAUTH_CONSUMER_KEY=$JIRA_OAUTH_CONSUMER_KEY

Github
~~~~~~

1. `Register a new application on Github <https://github.com/settings/applications/new>`_
2. The new application will give you a consumer key and consumer secret. Set
   these values in the Heroku environment:

   .. code-block:: bash

      $ heroku config:set GITHUB_OAUTH_CLIENT_ID=my-id GITHUB_OAUTH_CLIENT_SECRET=my-secret

Deploy
------

1. Set up your Heroku git remote to point to your Heroku application
2. ``git push heroku``
3. Initialize the database by running ``heroku run python manage.py dbcreate``
4. Visit your website -- it should load!
5. Visit ``/login/jira`` and authorize with JIRA
6. Visit ``/login/github`` and authorize with Github
7. Enjoy the sweet, sweet taste of API integration

Recurring Tasks
---------------

Some of the tasks that our webhooks bot does are meant to be done on a regular,
recurring basis. For example, :func:`~openedx_webhooks.views.jira.jira_rescan_users`
should be run every hour or so. To do that, we use a second, separate Heroku project
whose only function is to wake up once an hour, send an HTTP request to the
Heroku project running this code, and then go to sleep again. Heroku provides
the `Heroku Scheduler`_ addon for this exact purpose. Note that we want to use
a separate Heroku project in order to avoid paying for this service: if we used
the Heroku Scheduler within the same project, the total number of instance-hours
used by the two dynos would exceed the free tier. Since each project has its own
free tier, we can get around this by splitting these up into separate projects.

.. _Heroku Scheduler: https://devcenter.heroku.com/articles/scheduler
