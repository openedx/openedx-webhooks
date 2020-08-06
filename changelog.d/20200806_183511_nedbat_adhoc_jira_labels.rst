.. A new scriv changelog fragment.

- BUG: previously the bot could clobber ad-hoc labels on Jira issues when it
  set its own labels.  This is now fixed.  The bot will preserve any labels it
  didn't make.
