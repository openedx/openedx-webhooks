Installation
============

Make an app on Heroku
---------------------
You can use the free tier if you want, but then the application won't run
all the time. If you need it to run all the time, you'll need to pay.

Install Add-ons
~~~~~~~~~~~~~~~

This project uses:

* `Heroku Postgres <https://elements.heroku.com/addons/heroku-postgresql>`_
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

GitHub
~~~~~~

1. `Register a new application on GitHub <https://github.com/settings/applications/new>`_
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
6. Visit ``/login/github`` and authorize with GitHub
7. Enjoy the sweet, sweet taste of API integration

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
