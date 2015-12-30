# coding=utf-8
from __future__ import unicode_literals, print_function

import os
from flask import request, flash
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.contrib.jira import make_jira_blueprint
from flask_dance.consumer import oauth_authorized, oauth_error
from flask_dance.consumer.backend.sqla import SQLAlchemyBackend
from openedx_webhooks import db
from openedx_webhooks.models import OAuth

## JIRA ##

jira_bp = make_jira_blueprint(
    # this *should* pick up the client_key and rsa_key from app.config,
    # but it doesn't seem to be doing so... :(
    consumer_key=os.environ.get("JIRA_OAUTH_CONSUMER_KEY"),
    rsa_key=os.environ.get("JIRA_OAUTH_RSA_KEY"),
    # these are actually necessary
    base_url="https://openedx.atlassian.net",
    backend=SQLAlchemyBackend(OAuth, db.session),
)


@oauth_authorized.connect_via(jira_bp)
def jira_logged_in(blueprint, token):
    if token:
        flash("Successfully signed in with JIRA")
    else:
        flash("You denied the request to sign in with JIRA")


@oauth_error.connect_via(jira_bp)
def jira_error(blueprint, request):
    msg = "Error signing in to JIRA. Message is: {}".format(request.text)
    flash(msg, category="error")


## GITHUB ##

github_bp = make_github_blueprint(
    scope="admin:repo_hook,repo,user",
    backend=SQLAlchemyBackend(OAuth, db.session),
)


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
