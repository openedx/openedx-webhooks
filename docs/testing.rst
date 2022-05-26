Testing Notes
#############


The automated tests catch most things and if you add new capabalites you should
add new tests.

Running the Automated Tests
***************************

#. ``make install-dev-requiremnets``

#. ``make test``


Other Manual Tests to Run
*************************

Testing that Celery Starts Up Correctly
=======================================

The tests do not validate that celery will come up correctly or that its config
is correctly loaded.  You'll have to manually validate that.

To see if celery will start up correctly locally you can run the following
steps:

#. ``docker run -it -p 6379:6379 redis``

   This will bring up a redis server that celery can connect to.

#. In a second terminal

.. code-block::

    export REDIS_URL="redis://localhost"
    celery --app openedx_webhooks.worker worker -l INFO

This should produce a bunch of logging but should eventually say something
like::

    celery@<your hostname> ready.
