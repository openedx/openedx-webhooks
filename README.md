Webhooks for [Open edX](http://openedx.org), integrating
[JIRA](https://openedx.atlassian.net) and
[Github](https://github.com/edx), designed to be deployed onto
[Heroku](http://heroku.com).

# Setup

## Make an app on Heroku

Don't worry, it's free for one dyno.

## Install Add-ons

This project uses:
* [Heroku Postgres](https://addons.heroku.com/heroku-postgresql)
* [Bugsnag](https://addons.heroku.com/bugsnag)

## Flask Secret Key

Generate a secret key for Flask, so that it can save information into the session:

```bash
$ export FLASK_SECRET_KEY=`python -c "import os; print(os.urandom(24))"`
$ heroku config:set FLASK_SECRET_KEY=$FLASK_SECRET_KEY
```

# Setup OAuth

## JIRA

OAuth authentication for JIRA requires a RSA keypair. To set this up:

1. Run `openssl genrsa -out jira.pem`. This will generate a private key.
2. Run `openssl rsa -in jira.pem -pubout -out jira.pub`. This will generate the
   public key.
3.  Generate a random string to serve as the consumer key. For example, run
   `python -c "import uuid; print(uuid.uuid4().hex)" > jira.uuid`.
4. Configure an Application Link in JIRA. The consumer key is the contents
   of `jira.uuid`, and the public key is the contents of `jira.pub`.
5. Set RSA key and consumer key in Heroku environment:
    ```
    $ export JIRA_RSA_KEY="$(<jira.pem)"
    $ export JIRA_CONSUMER_KEY="$(<jira.uuid)"
    $ heroku config:set JIRA_RSA_KEY=$JIRA_RSA_KEY JIRA_CONSUMER_KEY=$JIRA_CONSUMER_KEY
    ```

## Github

1. [Register a new application on Github](https://github.com/settings/applications/new)
2. The new application will give you a consumer key and consumer secret. Set
   these values in the Heroku environment:
    ```
    $ heroku config:set GITHUB_CLIENT_ID=my-id GITHUB_CLIENT_SECRET=my-secret
    ```

# Deploy

1. Set up your Heroku git remote to point to your Heroku application
2. `git push heroku`
3. Initialize the database by running `heroku run python manage.py dbcreate`
4. Visit your website -- it should load!
5. Visit `/oauth/jira` and authorize with JIRA
6. Visit `/oauth/github` and authorize with Github
7. Enjoy the sweet, sweet taste of API integration
