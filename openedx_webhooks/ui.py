import logging

from flask import Blueprint, render_template

from openedx_webhooks.auth import get_github_session, get_jira_session
from openedx_webhooks.settings import settings
from openedx_webhooks.utils import requires_auth

ui = Blueprint('ui', __name__)
logger = logging.getLogger(__name__)

@ui.route("/")
@requires_auth
def index():
    """
    Display an HTML overview page, with links to other functions that
    this application can perform.
    """
    github_username = None
    gh_user_resp = get_github_session().get("/user")
    if gh_user_resp.ok:
        try:
            github_username = gh_user_resp.json()["login"]
        except Exception:
            logger.error("Failed to process response: {}".format(gh_user_resp.text))
            raise

    jira_username = None
    if settings.JIRA_SERVER:
        jira_user_resp = get_jira_session().get("/rest/api/2/myself")
        if jira_user_resp.ok:
            try:
                jira_username = jira_user_resp.json()["displayName"]
            except Exception:
                logger.error("Failed to process response: {}".format(jira_user_resp.text))
                raise

    return render_template("main.html",
        github_username=github_username, jira_username=jira_username,
    )
