from __future__ import unicode_literals, print_function

import os
import sys
import json
from datetime import datetime

from flask import Blueprint, url_for, request, flash, redirect
from flask_oauthlib.client import OAuth
from oauthlib.oauth1 import SIGNATURE_RSA
import backoff
from urlobject import URLObject
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


oauth = OAuth()
blueprint = Blueprint('oauth', __name__)

## JIRA ##

JIRA_URL = URLObject("https://openedx.atlassian.net")
JIRA_REQUEST_TOKEN_URL = JIRA_URL.with_path("/plugins/servlet/oauth/request-token")
JIRA_ACCESS_TOKEN_URL = JIRA_URL.with_path("/plugins/servlet/oauth/access-token")
JIRA_AUTHORIZE_URL = JIRA_URL.with_path("/plugins/servlet/oauth/authorize")

jira = oauth.remote_app(
    name="jira",
    base_url=JIRA_URL,
    request_token_url=JIRA_REQUEST_TOKEN_URL,
    access_token_url=JIRA_ACCESS_TOKEN_URL,
    authorize_url=JIRA_AUTHORIZE_URL,
    consumer_key=os.environ["JIRA_CONSUMER_KEY"],
    request_token_params=dict(
        rsa_key=os.environ["JIRA_RSA_KEY"],
        signature_method=SIGNATURE_RSA,
    ),
    request_token_method="POST",
    access_token_method="POST",
)


@jira.tokengetter
def get_jira_token(token=None):
    query = OAuthCredential.query.filter_by(name="jira")
    if token:
        query = query.filter_by(token=token)
    creds = query.first()
    if creds:
        return (creds.token, creds.secret)
    return None


@blueprint.route('/jira')
def jira_oauth():
    return jira.authorize(callback=url_for(
        '.jira_oauth_authorized',
        next=request.args.get('next') or request.referrer or None
    ))


@blueprint.route("/jira/authorized")
def jira_oauth_authorized():
    resp = jira.authorized_response()
    next_url = request.args.get('next') or url_for('index')
    if not resp:
        flash("You denied the request to sign in.")
        return redirect(next_url)
    creds = OAuthCredential(
        name="jira",
        token=resp["oauth_token"],
        secret=resp["oauth_token_secret"],
        created_on=datetime.utcnow(),
    )
    db.session.add(creds)
    db.session.commit()

    flash("Signed in successfully")
    return redirect(next_url)

## GITHUB ##

GITHUB_URL = URLObject("https://github.com")
GITHUB_API_URL = URLObject("https://api.github.com")
GITHUB_ACCESS_TOKEN_URL = GITHUB_URL.with_path("/login/oauth/access_token")
GITHUB_AUTHORIZE_URL = GITHUB_URL.with_path("/login/oauth/authorize")

github = oauth.remote_app(
    name='github',
    consumer_key=os.environ["GITHUB_CLIENT_ID"],
    consumer_secret=os.environ["GITHUB_CLIENT_SECRET"],
    request_token_params={'scope': 'user,repo,admin:repo_hook'},
    base_url=GITHUB_API_URL,
    access_token_method='POST',
    access_token_url=GITHUB_ACCESS_TOKEN_URL,
    authorize_url=GITHUB_AUTHORIZE_URL,
)


@github.tokengetter
def get_github_token(token=None):
    query = OAuthCredential.query.filter_by(name="github")
    if token:
        query = query.filter_by(token=token)
    creds = query.first()
    if creds:
        return (creds.token, creds.secret)
    return None


@blueprint.route("/github")
def github_oauth():
    return github.authorize(callback=url_for(
        '.github_oauth_authorized',
        next=request.args.get('next') or request.referrer or None,
        _external=True,
    ))


@blueprint.route("/github/authorized")
def github_oauth_authorized():
    resp = github.authorized_response()
    next_url = request.args.get('next') or url_for('index')
    if not resp:
        msg = "Access denied. Reason={reason} error={error}".format(
            reason=request.args["error_reason"],
            error=request.args["error_description"],
        )
        flash(msg)
        return redirect(next_url)
    creds = OAuthCredential(
        name="github",
        token=resp["access_token"],
        secret="",
        created_on=datetime.utcnow(),
    )
    db.session.add(creds)
    db.session.commit()

    flash("Signed in successfully")
    return redirect(next_url)

## UTILITY FUNCTIONS ##

@backoff.on_exception(backoff.expo, ValueError, max_tries=5)
def jira_request(url, data=None, headers=None, method="GET",
                 *args, **kwargs):
    """
    JIRA sometimes returns an empty response to a perfectly valid GET request,
    so this will retry it a few times if that happens. This also sets a few
    sensible defaults for JIRA requests.
    """
    headers = headers or {}
    headers.setdefault("Accept", "application/json")
    if data:
        kwargs["content_type"] = "application/json"
    if data and not isinstance(data, basestring):
        data = json.dumps(data)
    return jira.request(
        url=url, data=data, headers=headers,
        method=method, *args, **kwargs
    )
