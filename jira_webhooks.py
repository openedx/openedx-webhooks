import os
import json

from flask import Flask, request
from raven.contrib.flask import Sentry
import requests
from urlobject import URLObject


app = Flask(__name__)
sentry = Sentry(app)

username = os.environ.get("JIRA_USERNAME", None)
password = os.environ.get("JIRA_PASSWORD", None)
api = requests.Session()
api.auth = (username, password)
api.headers["Content-Type"] = "application/json"


@app.route("/")
def index():
    """
    Just to verify that things are working
    """
    return "JIRA Webhooks home"


@app.route("/issue/created", methods=("POST",))
def issue_created():
    """
    Received an "issue created" event from JIRA.
    https://developer.atlassian.com/display/JIRADEV/JIRA+Webhooks+Overview

    Ideally, this should be handled in a task queue, but we want to stay within
    Heroku's free plan, so it will be handled inline instead.
    (A worker dyno costs money.)
    """
    event = request.get_json()
    issue_url = URLObject(event["issue"]["self"])
    user_url = URLObject(event["user"]["self"])
    user_url = user_url.set_query_param("expand", "groups")
    user_resp = api.get(user_url)
    if not user_resp.ok:
        raise requests.exceptions.RequestException(user_resp.text)
    user = user_resp.json()
    groups = {g["name"]: g["self"] for g in user["groups"]["items"]}

    # skip "Needs Triage" if bug was created by edX employee
    if "edx-employees" in groups:
        transitions_url = issue_url.with_path(issue_url.path + "/transitions")
        body = {
            "transition": {
                "name": "Open"
            }
        }
        transition_resp = api.post(transitions_url, data=json.dumps(body))
        if not transition_resp.ok:
            raise requests.exceptions.RequestException(transition_resp.text)

    return "Processed"


if __name__ == "__main__":
    app.run()
