from __future__ import print_function

import os
import sys
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
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from JIRA: {data}".format(data=request.data))

    if app.debug:
        print(json.dumps(event), file=sys.stderr)

    issue_key = event["issue"]["key"]
    issue_status = event["issue"]["fields"]["status"]["name"]
    if issue_status != "Needs Triage":
        print(
            "{key} has status {status}, does not need to be processed".format(
                key=issue_key, status=issue_status,
            ),
            file=sys.stderr,
        )
        return "issue does not need to be triaged"

    issue_url = URLObject(event["issue"]["self"])
    user_url = URLObject(event["user"]["self"])
    user_url = user_url.set_query_param("expand", "groups")
    user_resp = api.get(user_url)
    if not user_resp.ok:
        raise requests.exceptions.RequestException(user_resp.text)
    user = user_resp.json()
    groups = {g["name"]: g["self"] for g in user["groups"]["items"]}

    # skip "Needs Triage" if bug was created by edX employee
    transitioned = False
    if "edx-employees" in groups:
        transitions_url = issue_url.with_path(issue_url.path + "/transitions")
        transitions_resp = api.get(transitions_url)
        if not transitions_resp.ok:
            raise requests.exceptions.RequestException(transitions_resp.text)
        transitions = {t["name"]: t["id"] for t in transitions_resp.json()["transitions"]}
        if "Open" in transitions:
            new_status = "Open"
        elif "Design Backlog" in transitions:
            new_status = "Design Backlog"
        else:
            raise ValueError("No valid transition! Possibilities are {}".format(transitions.keys()))

        body = {
            "transition": {
                "id": transitions[new_status],
            }
        }
        transition_resp = api.post(transitions_url, data=json.dumps(body))
        if not transition_resp.ok:
            raise requests.exceptions.RequestException(transition_resp.text)
        transitioned = True

    # log to stderr
    print(
        "{key} created by {name} ({username}), {action}".format(
            key=issue_key, name=event["user"]["displayName"],
            username=event["user"]["name"],
            action="Transitioned to Open" if transitioned else "ignored",
        ),
        file=sys.stderr,
    )
    return "Processed"


if __name__ == "__main__":
    app.run()
