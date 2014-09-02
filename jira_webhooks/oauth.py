from __future__ import unicode_literals, print_function

import os
import sys
import json

from flask_oauthlib.client import OAuth
from oauthlib.oauth1 import SIGNATURE_RSA
import backoff
from urlobject import URLObject
from .models import OAuthCredential

JIRA_URL = URLObject("https://openedx.atlassian.net")
REQUEST_TOKEN_URL = JIRA_URL.with_path("/plugins/servlet/oauth/request-token")
ACCESS_TOKEN_URL = JIRA_URL.with_path("/plugins/servlet/oauth/access-token")
AUTHORIZE_URL = JIRA_URL.with_path("/plugins/servlet/oauth/authorize")

req_env_vars = set(("JIRA_CONSUMER_KEY", "JIRA_RSA_KEY"))
missing = req_env_vars - set(os.environ.keys())
if missing:
    raise Exception(
        "You must define the following variables in your environment: {vars} "
        "See the README for more information.".format(vars=missing)
    )

oauth = OAuth()
jira = oauth.remote_app(
    name="jira",
    base_url=JIRA_URL,
    request_token_url=REQUEST_TOKEN_URL,
    access_token_url=ACCESS_TOKEN_URL,
    authorize_url=AUTHORIZE_URL,
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


@backoff.on_exception(backoff.expo, ValueError, max_tries=5)
def jira_request(url, data=None, headers=None, method="GET",
                 content_type="application/json",
                 *args, **kwargs):
    """
    JIRA sometimes returns an empty response to a perfectly valid GET request,
    so this will retry it a few times if that happens. This also sets a few
    sensible defaults for JIRA requests.
    """
    headers = headers or {}
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", content_type)
    # if data and not isinstance(data, basestring):
    #     data = json.dumps(data)
    print("content_type = {}".format(content_type), file=sys.stderr)
    return jira.request(
        url=url, data=data, headers=headers,
        method=method, content_type=content_type,
        *args, **kwargs
    )
