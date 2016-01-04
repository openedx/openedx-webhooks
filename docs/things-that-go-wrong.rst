Things That Go Wrong
====================

This project isn't perfect. Here are a few things that sometimes go wrong,
and some suggestions for how to fix them.

Missed pull requests
--------------------

Sometimes, the bot just doesn't detect pull requests on GitHub. As a result,
they don't get OSPR tickets, and they get forgotten about. We don't know
why they get missed -- in theory, GitHub should send a webhook notification
for every pull request, and this application should process each one.

It's a good idea to run the rescan job once a week or so, and see if any
pull requests turn up. In addition, check Sentry to see if any errors have
been logged, and verify that the repos that have the missing pull requests
are under the bot's management. (You can check the list of webhooks on the
repository admin page.)

Request timeout from Heroku
---------------------------

Heroku has a strict limit on page load times: a page cannot take more than 30
seconds to return a response. Some of the tasks that this bot does take more
than 30 seconds, so Heroku will cut them off if the task is run on a web dyno.
Instead, these tasks must be run on a worker dyno, using a task queue
architecture. Some of our tasks have been migrated to this architecture, such
as the repository rescan task. However, some tasks are still run inline.

If one of these tasks starts timing out, there is no quick and easily solution:
it must be rewritten to use a task queue architecture. Fortunately, you can
follow the example of the existing Celery tasks in this codebase. Celery's
documentation is pretty good, as well.
