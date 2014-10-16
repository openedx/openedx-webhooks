from __future__ import unicode_literals, print_function

from openedx_webhooks import app
from flask import render_template
from flask_dance.contrib.github import github
from flask_dance.contrib.jira import jira

from .github import github_pull_request, github_rescan, github_install
from .jira import jira_issue_created, jira_rescan


@app.route("/")
def index():
    """
    Just to verify that things are working
    """
    github_username = None
    if github.token:
        gh_user_resp = github.get("/user")
        if gh_user_resp.ok:
            github_username = gh_user_resp.json()["login"]
    jira_username = None
    if jira.auth.client.resource_owner_key:
        jira_user_resp = jira.get("/rest/api/2/myself")
        if jira_user_resp.ok:
            jira_username = jira_user_resp.json()["name"]
    return render_template("main.html",
        github_username=github_username, jira_username=jira_username,
    )
