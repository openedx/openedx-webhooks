How To Activate Recording GitHub Activities in JIRA Issues
==========================================================

Currently we have the code to receive GitHub PR events via webhooks, and
record them in JIRA. However, we don't want to activate this code yet
until we've determined that we can tune the workflow to the appropriate
level of email notifications.

In order to activate this feature:

1. Add the following config vars at Heroku:

   -  [ ] GITHUB\_PERSONAL\_TOKEN
   -  [ ] GITHUB\_WEBHOOKS\_SECRET
   -  [ ] JIRA\_ACCESS\_TOKEN
   -  [ ] JIRA\_ACCESS\_TOKEN\_SECRET
   -  [ ] JIRA\_OAUTH\_PRIVATE\_KEY
   -  [ ] JIRA\_SERVER
   -  [ ] RQ\_WORKER\_LOGGING\_LEVEL

2. Add ``rqworker`` dyno type

   ::

       heroku ps:scale rqworker=1 -a openedx-webhooks

3. Install the webhooks at various repos by using the
   ``bin/gh_list_repos_with_webhook.py`` command. This command can be
   run locally or remotely at Heroku.

4. Add the following webhook configuration to
   ``openedx_webhooks.webhook_confs.WEBHOOK_CONFS``:

   .. code:: python

       {
           'config': {
               'url': url_for("github_views.hook_receiver", _external=True),
               'content_type': 'json',
               'insecure_ssl': False,
               'secret': os.environ.get('GITHUB_WEBHOOKS_SECRET'),
           },
           'events': [
               'issue_comment',
               'pull_request',
               'pull_request_review',
               'pull_request_review_comment',
           ]
       }

5. Commit changes to GitHub
6. Deploy to ``openedx-webhooks-staging`` at Heroku
7. Promote from staging to ``openedx-webhooks`` at Heroku
