import os

import requests
from urlobject import URLObject
from flask import flash, request
from flask_dance.consumer import oauth_authorized, oauth_error
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.contrib.jira import make_jira_blueprint

from openedx_webhooks import db, settings
from openedx_webhooks.models import OAuth

## JIRA ##

jira_bp = make_jira_blueprint(
    # this *should* pick up the client_key and rsa_key from app.config,
    # but it doesn't seem to be doing so... :(
    consumer_key=os.environ.get("JIRA_OAUTH_CONSUMER_KEY"),
    rsa_key=os.environ.get("JIRA_OAUTH_RSA_KEY"),
    # these are actually necessary
    base_url=settings.JIRA_SERVER,
    storage=SQLAlchemyStorage(OAuth, db.session),
)


def get_jira_session():
    """
    Get the Jira session to use, in an easily test-patchable way.
    """
    if settings.JIRA_SERVER:
        return jira_bp.session
    else:
        return None

@oauth_authorized.connect_via(jira_bp)
def jira_logged_in(blueprint, token):
    if token:
        flash("Successfully signed in with JIRA")
    else:
        flash("You denied the request to sign in with JIRA")


@oauth_error.connect_via(jira_bp)
def jira_error(blueprint, message, response=None):
    flash(message, category="error")


## GITHUB ##

github_bp = make_github_blueprint(
    scope="admin:repo_hook,repo,user",
    storage=SQLAlchemyStorage(OAuth, db.session),
)


class BaseUrlSession(requests.Session):
    """
    A requests Session class that applies a base URL to the requested URL.
    This is how the flask-dance OAuth session works. This is a drop-in
    replacement as we move from OAuth authentication to access tokens.
    """
    def __init__(self, base_url):
        super().__init__()
        self.base_url = URLObject(base_url)

    def request(self, method, url, data=None, headers=None, **kwargs):
        return super().request(
            method=method,
            url=self.base_url.relative(url),
            data=data,
            headers=headers,
            **kwargs
        )


def get_github_session():
    """
    Get the GitHub session to use.
    """
    # Create a session that's compatible with the old OAuth session the rest
    # of the code is expecting.
    session = BaseUrlSession("https://api.github.com")
    token = os.environ.get("GITHUB_PERSONAL_TOKEN", "nothing_for_tests")
    session.headers["Authorization"] = f"token {token}"
    return session


@oauth_authorized.connect_via(github_bp)
def github_logged_in(blueprint, token):
    if not token:
        flash("Failed to log in with Github")
    if "error_reason" in token:
        msg = "Access denied. Reason={reason} error={error}".format(
            reason=request.args["error_reason"],
            error=request.args["error_description"],
        )
        flash(msg)
    else:
        flash("Successfully signed in with Github")


## UTILITY FUNCTIONS ##

def jira_get(*args, **kwargs):
    """
    JIRA sometimes returns an empty response to a perfectly valid GET request,
    so this will retry it a few times if that happens.
    """
    for _ in range(3):
        resp = jira_bp.session.get(*args, **kwargs)
        if resp.content:
            return resp
    return jira_bp.session.get(*args, **kwargs)
