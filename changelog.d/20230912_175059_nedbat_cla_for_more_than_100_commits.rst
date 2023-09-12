.. A new scriv changelog fragment.

- The CLA check used to fail if a pull request had more than 100 commits.  Now
  the head sha is retrieved directly without listing all commits, so the number
  is irrelevant.
