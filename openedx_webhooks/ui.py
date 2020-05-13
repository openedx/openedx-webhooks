import logging

from flask import Blueprint, render_template
from flask_dance.contrib.github import github as github_session
from flask_dance.contrib.jira import jira as jira_session
from openedx_webhooks.utils import requires_auth


ui = Blueprint('ui', __name__)
logger = logging.getLogger()

@ui.route("/")
@requires_auth
def index():
    """
    Display an HTML overview page, with links to other functions that
    this application can perform.
    """
    github_username = None
    if github_session.authorized:
        gh_user_resp = github_session.get("/user")
        if gh_user_resp.ok:
            try:
                github_username = gh_user_resp.json()["login"]
            except Exception as e:
                logger.error("Failed to process response: {}".format(gh_user_resp.text))
                raise


    jira_username = None
    if jira_session.authorized:
        jira_user_resp = jira_session.get("/rest/api/2/myself")
        if jira_user_resp.ok:
            try:
                jira_username = jira_user_resp.json()["displayName"]
            except Exception as e:
                logger.error("Failed to process response: {}".format(jira_user_resp.text))
                raise


    return render_template("main.html",
        github_username=github_username, jira_username=jira_username,
    )
