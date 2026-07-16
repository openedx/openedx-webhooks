import logging

from flask import Blueprint, render_template

from openedx_webhooks.auth import get_github_session
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

    return render_template("main.html", github_username=github_username)
