Webhooks for the [Open edX JIRA](https://openedx.atlassian.net).

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
6. Deploy to Heroku
7. Do the OAuth dance
8. Enjoy the sweet, sweet taste of API integration
