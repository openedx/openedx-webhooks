# coding=utf-8
from __future__ import unicode_literals, print_function

from datetime import datetime
import os
import warnings

from flask import request, flash
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.contrib.jira import make_jira_blueprint
from flask_dance.consumer import oauth_authorized

from .models import db, OAuth


# Check for required environment variables

req_env_vars = set((
    "JIRA_CONSUMER_KEY", "JIRA_RSA_KEY",
    "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET",
))
missing = req_env_vars - set(os.environ.keys())
if missing:
    warnings.warn(
        "You must define the following variables in your environment: {vars}. "
        "Using dummy values, but you won't be able to use remote services. "
        "See the docs for more information.".format(vars=", ".join(missing))
    )
    for name in missing:
        os.environ[name] = "xxx"


## JIRA ##

jira_bp = make_jira_blueprint(
    consumer_key=os.environ["JIRA_CONSUMER_KEY"],
    rsa_key=os.environ["JIRA_RSA_KEY"],
    base_url="https://openedx.atlassian.net",
    redirect_to="index",
)
jira_bp.set_token_storage_sqlalchemy(OAuth, db.session)


@oauth_authorized.connect_via(jira_bp)
def jira_logged_in(blueprint, token):
    if token:
        flash("Successfully signed in with JIRA")
    else:
        flash("You denied the request to sign in with JIRA")

## GITHUB ##

github_bp = make_github_blueprint(
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    scope="admin:repo_hook,repo,user",
    redirect_to="index",
)
github_bp.set_token_storage_sqlalchemy(OAuth, db.session)


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
