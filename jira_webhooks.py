import json

from flask import Flask, request
from raven.contrib.flask import Sentry
import requests
from urlobject import URLObject


app = Flask(__name__)
sentry = Sentry(app)


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
    user_url = user_url.set_query_param("expand", "group")
    user_resp = requests.get(user_url)
    if not user_resp.ok:
        raise requests.exceptions.RequestException(user_resp.text)
    user = user_resp.json()
    groups = {g["name"]: g["self"] for g in user["groups"]["items"]}

    if "edx-employees" not in groups:
        body = {
            "update": {
                "labels": [{
                    "add": "needs-triage",
                }]
            }
        }
        issue_resp = requests.put(issue_url, data=json.dumps(body))
        if not issue_resp.ok:
            raise requests.exceptions.RequestException(issue_resp.text)

    return "Processed"


if __name__ == "__main__":
    app.run()
