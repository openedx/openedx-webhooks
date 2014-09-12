from __future__ import print_function, unicode_literals

import os
import sys
import json

from flask import Flask, render_template, request
import requests
import yaml
from urlobject import URLObject
from .oauth import jira_bp, jira, jira_get, github_bp
from .models import db
from .utils import pop_dict_id
import bugsnag
from bugsnag.flask import handle_exceptions

app = Flask(__name__)
handle_exceptions(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "secrettoeveryone")
app.register_blueprint(jira_bp, url_prefix="/login")
app.register_blueprint(github_bp, url_prefix="/login")
db.init_app(app)


@app.route("/")
def index():
    """
    Just to verify that things are working
    """
    return render_template("main.html")


@app.route("/jira/issue/created", methods=("POST",))
def jira_issue_created():
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
    bugsnag.configure_request(meta_data={"event": event})

    if app.debug:
        print(json.dumps(event), file=sys.stderr)

    issue_key = event["issue"]["key"]
    issue_status = event["issue"]["fields"]["status"]["name"]
    project = event["issue"]["fields"]["project"]["key"]
    if issue_status != "Needs Triage":
        print(
            "{key} has status {status}, does not need to be processed".format(
                key=issue_key, status=issue_status,
            ),
            file=sys.stderr,
        )
        return "issue does not need to be triaged"
    if project == "OSPR":
        # open source pull requests do not skip Needs Triage
        print(
            "{key} is an open source pull request, and does not need to be processed.".format(
                key=issue_key
            ),
            file=sys.stderr,
        )
        return "issue is OSPR"

    issue_url = URLObject(event["issue"]["self"])
    user_url = URLObject(event["user"]["self"])
    user_url = user_url.set_query_param("expand", "groups")

    user_resp = jira_get(user_url)
    if not user_resp.ok:
        raise requests.exceptions.RequestException(user_resp.text)

    user = user_resp.json()
    groups = {g["name"]: g["self"] for g in user["groups"]["items"]}

    # skip "Needs Triage" if bug was created by edX employee
    transitioned = False
    if "edx-employees" in groups:
        transitions_url = issue_url.with_path(issue_url.path + "/transitions")
        transitions_resp = jira_get(transitions_url)
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
        transition_resp = jira.post(transitions_url, data=body)
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


@app.route("/github/pr", methods=("POST",))
def github_pull_request():
    try:
        event = request.get_json()
    except ValueError:
        raise ValueError("Invalid JSON from Github: {data}".format(data=request.data))
    bugsnag_context = {"event": event}
    bugsnag.configure_request(meta_data=bugsnag_context)

    pr = event["pull_request"]
    user = pr["user"]["login"]

    # get the list of organizations that the user is in
    people_resp = requests.get("https://raw.githubusercontent.com/edx/repo-tools/master/people.yaml")
    if not people_resp.ok:
        raise requests.exceptions.RequestException(people_resp.text)
    people = yaml.safe_load(people_resp.text)

    if user in people and people[user].get("institution", "") == "edX":
        # not an open source pull request, don't create an issue for it
        print(
            "@{user} opened PR #{num} against {repo} (internal PR)".format(
                user=user, repo=pr["base"]["repo"]["full_name"],
                num=pr["number"]
            ),
            file=sys.stderr
        )
        return "internal pull request"

    field_resp = jira.get("/rest/api/2/field")
    if not field_resp.ok:
        raise requests.exceptions.RequestException(field_resp.text)
    field_map = dict(pop_dict_id(f) for f in field_resp.json())
    custom_fields = {
        value["name"]: id
        for id, value in field_map.items()
        if value["custom"]
    }

    if event["action"] == "opened":
        # create an issue on JIRA!
        new_issue = {
            "fields": {
                "project": {
                    "key": "OSPR",
                },
                "issuetype": {
                    "name": "Pull Request Review",
                },
                "summary": pr["title"],
                "description": pr["body"],
                custom_fields["URL"]: pr["html_url"],
                custom_fields["PR Number"]: pr["number"],
                custom_fields["Repo"]: pr["base"]["repo"]["full_name"],
            }
        }
        bugsnag_context["new_issue"] = new_issue
        bugsnag.configure_request(meta_data=bugsnag_context)
        resp = jira.post("/rest/api/2/issue", data=new_issue)
        new_issue_body = resp.json()
        if resp.ok:
            print(
                "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
                    user=user, repo=pr["base"]["repo"]["full_name"],
                    num=pr["number"], issue=new_issue_body["key"]
                ),
                file=sys.stderr
            )
            return "created!"
        else:
            print(new_issue_body, file=sys.stderr)

    print(
        "Received {action} event on PR #{num} against {repo}, don't know how to handle it".format(
            action=event["action"], repo=pr["base"]["repo"]["full_name"],
            num=pr["number"]
        ),
        file=sys.stderr
    )
    return "Don't know how to handle this.", 400


if __name__ == "__main__":
    app.run()
