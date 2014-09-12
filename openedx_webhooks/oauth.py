from __future__ import unicode_literals, print_function

import os
from datetime import datetime

from flask import request, flash
from flask_dance.contrib.github import make_github_blueprint
from flask_dance.contrib.jira import make_jira_blueprint
from .models import db, OAuthCredential

# Check for required environment variables

req_env_vars = set((
    "JIRA_CONSUMER_KEY", "JIRA_RSA_KEY",
    "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET",
))
missing = req_env_vars - set(os.environ.keys())
if missing:
    raise Exception(
        "You must define the following variables in your environment: {vars} "
        "See the README for more information.".format(vars=", ".join(missing))
    )


## JIRA ##

jira_bp = make_jira_blueprint(
    consumer_key=os.environ["JIRA_CONSUMER_KEY"],
    rsa_key=os.environ["JIRA_RSA_KEY"],
    base_url="https://openedx.atlassian.net",
    redirect_to="index",
)
jira = jira_bp.session


@jira_bp.token_setter
def set_jira_token(token, identifier=None):
    creds = OAuthCredential(
        name="jira",
        token=token["oauth_token"],
        secret=token["oauth_token_secret"],
        created_on=datetime.utcnow(),
    )
    db.session.add(creds)
    db.session.commit()


@jira_bp.token_getter
def get_jira_token(identifier=None):
    creds = OAuthCredential.query.filter_by(name="jira").first()
    if creds:
        return {
            "oauth_token": creds.token,
            "oauth_token_secret": creds.secret,
        }
    return None


@jira_bp.logged_in
def jira_logged_in(token):
    if token:
        flash("Successfully signed in with JIRA")
    else:
        flash("You denied the request to sign in with JIRA")

## GITHUB ##

github_bp = make_github_blueprint(
    client_id=os.environ["GITHUB_CLIENT_ID"],
    client_secret=os.environ["GITHUB_CLIENT_SECRET"],
    scope=["admin:repo_hook", "repo", "user"],
    redirect_to="index",
)
github = github_bp.session


@github_bp.token_setter
def set_github_token(token, identifier=None):
    creds = OAuthCredential(
        name="github",
        token=token["access_token"],
        type=token["token_type"],
        scope=token["scope"],
        created_on=datetime.utcnow(),
    )
    db.session.add(creds)
    db.session.commit()


@github_bp.token_getter
def get_github_token(identifier=None):
    creds = OAuthCredential.query.filter_by(name="github").first()
    if creds:
        return {
            "access_token": creds.token,
            "token_type": creds.type,
            "scope": creds.scope,
        }
    return None


@github_bp.logged_in
def github_logged_in(token):
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
