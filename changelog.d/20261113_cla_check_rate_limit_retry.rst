- When GitHub refuses a request because the bot's API rate limit is
  exhausted, the pull request task now retries after the limit resets
  (up to five times) instead of silently dropping the work.  Before this,
  a rate-limited task left the pull request without its CLA check and bot
  comments, and reported itself as succeeded.
