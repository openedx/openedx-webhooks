# coding=utf-8
from __future__ import print_function, unicode_literals

from flask import Blueprint, render_template
from flask_dance.contrib.github import github as github_session
from flask_dance.contrib.jira import jira as jira_session

ui = Blueprint('ui', __name__)


@ui.route("/")
def index():
    """
    Display an HTML overview page, with links to other functions that
    this application can perform.
    """
    github_username = None
    if github_session.authorized:
        gh_user_resp = github_session.get("/user")
        if gh_user_resp.ok:
            github_username = gh_user_resp.json()["login"]

    jira_username = None
    if jira_session.authorized:
        jira_user_resp = jira_session.get("/rest/api/2/myself")
        if jira_user_resp.ok:
            jira_username = jira_user_resp.json()["name"]

    return render_template("main.html",
        github_username=github_username, jira_username=jira_username,
    )
