.. A new scriv changelog fragment.

- The bot used to create a Jira issue to replace an issue that had been
  deleted.  This interfered with rescanning, so the bot no longer does this.
  If a Jira issue mentioned in the bot comment has been deleted, it will not be
  recreated.
