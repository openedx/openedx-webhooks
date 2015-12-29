What This App Could Do
======================

These features are not currently implemented, but they would be really nice.

Hook into GitHub's organization APIs
------------------------------------

Right now, new repositories on GitHub are not managed by this application
until a person puts them under its management. GitHub provides an API at the
organization level, which allows applications to know when new repositories
are added to an organization. It would be really nice to have this bot hook
into that API, so that it can set up new repositories for management
automatically when they are created.

Auto-close stale pull requests
------------------------------

Lots of pull requests on the edX repositories are abandoned, which is sad.
It would be really nice to have this bot run over all open pull requests
once a day, and check how long it's been since there has been *any* activity
whatsoever: a new comment, a new commit, anything. If it's been two weeks since
the last activity, the bot would add a comment asking if the pull request is
still being worked on. If another two weeks go by without any further activity,
the bot would automatically close the pull request.

Note that this auto-close functionality should operate on *all* open pull
requests, regardless of the author! Developers at edX are definitely guilty
of forgetting about open pull requests and leaving them to go stale indefinitely.

Add a review checklist to pull requests
---------------------------------------

Pull request reviews must go through many steps. It would be nice if pull
requests had a checklist of those steps, perhaps in the description of the
pull request. Then, as each step is completed, that step could be checked off.
This bot could create a checklist like this automatically for each pull request
-- or perhaps link to a checklist created on another site, which has different
edit permissions than the edit permissions on pull request comments and
descriptions on GitHub.
