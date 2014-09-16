from __future__ import unicode_literals, print_function

from openedx_webhooks import app
from flask import render_template

from .github import github_pull_request
from .jira import jira_issue_created


@app.route("/")
def index():
    """
    Just to verify that things are working
    """
    return render_template("main.html")
