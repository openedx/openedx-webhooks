.. A new scriv changelog fragment.

- Refactored some code that handles pull requests being closed, so now it
  operates on any change to the pull request.  The behavior should be the same,
  except now if a pull request is closed or merged after the Jira issue has
  been manually deleted, the bot will create a new issue so that it can mark it
  Rejected or Merged.
