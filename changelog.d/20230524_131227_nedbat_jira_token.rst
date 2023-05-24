.. A new scriv changelog fragment.

- Jira authentication now uses the JIRA_USER_EMAIL and JIRA_USER_TOKEN
  environment variables.  OAuth authentication is removed. These settings are
  now obsolete and can be deleted:

  - DATABASE_URL
  - GITHUB_OAUTH_CLIENT_ID
  - GITHUB_OAUTH_CLIENT_SECRET
  - JIRA_OAUTH_CONSUMER_KEY
  - JIRA_OAUTH_RSA_KEY
  - SQLALCHEMY_DATABASE_URI
