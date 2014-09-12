from __future__ import print_function, unicode_literals

import os
import sys
import json

from flask import Flask, render_template, request
import requests
import yaml
from urlobject import URLObject
from .oauth import jira_bp, jira, jira_get, github_bp, github
from .models import db
from .jira import Jira
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
        transition_resp = jira.post(transitions_url, data=json.dumps(body))
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
    repo = pr["base"]["repo"]["full_name"]

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

    custom_fields = Jira(session=jira).custom_field_names

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
        resp = jira.post("/rest/api/2/issue", data=json.dumps(new_issue))
        if not resp.ok:
            raise requests.exceptions.RequestException(resp.text)
        new_issue_body = resp.json()
        bugsnag_context["new_issue"]["key"] = new_issue_body["key"]
        bugsnag.configure_request(meta_data=bugsnag_context)
        # add a comment to the Github pull request with a link to the JIRA issue
        comment = {
            "body": github_pr_comment(pr, new_issue_body, people),
        }
        comment_resp = github.post("/repos/{repo}/issues/{num}/comments".format(
            repo=repo, num=pr["number"],
        ))
        if not comment_resp.ok:
            raise requests.exceptions.RequestException(comment_resp.text)
        print(
            "@{user} opened PR #{num} against {repo}, created {issue} to track it".format(
                user=user, repo=repo,
                num=pr["number"], issue=new_issue_body["key"]
            ),
            file=sys.stderr
        )
        return "created!"

    print(
        "Received {action} event on PR #{num} against {repo}, don't know how to handle it".format(
            action=event["action"], repo=repo,
            num=pr["number"]
        ),
        file=sys.stderr
    )
    return "Don't know how to handle this.", 400


def github_pr_comment(pull_request, jira_issue, people):
    """
    For a newly-created pull request from an open source contributor,
    write a welcoming comment on the pull request. The comment should:

    * contain a link to the JIRA issue
    * check for contributor agreement
    * check for AUTHORS entry
    * contain a link to our process documentation
    """
    people = {user.lower(): values for user, values in people.items()}
    pr_author = pull_request["user"]["login"].lower()
    # does the user have a signed contributor agreement?
    has_signed_agreement = pr_author in people
    # is the user in the AUTHORS file?
    in_authors_file = False
    authors_entry = people.get(pr_author, {}).get("authors_entry", "")
    if authors_entry:
        authors_url = "https://raw.githubusercontent.com/{repo}/{branch}/AUTHORS".format(
            repo=pull_request["head"]["repo"]["full_name"], branch=pull_request["head"]["ref"],
        )
        authors_resp = github.get(authors_url)
        if authors_resp.ok:
            authors_content = authors_resp.text
            if authors_entry in authors_content:
                in_authors_file = True

    doc_url = "http://edx.readthedocs.org/projects/userdocs/en/latest/process/overview.html"
    issue_key = jira_issue["key"]
    issue_url = "https://openedx.atlassian.net/browse/{key}".format(key=issue_key)
    contributing_url = "https://github.com/edx/edx-platform/blob/master/CONTRIBUTING.rst"
    agreement_url = "http://code.edx.org/individual-contributor-agreement.pdf"
    authors_url = "https://github.com/edx/edx-platform/blob/master/AUTHORS"
    comment = (
        "Thanks for the pull request, @{user}! I've created "
        "[{issue_key}]({issue_url}) to keep track of it in JIRA. "
        "As a reminder, [our process documentation is here]({doc_url})."
    ).format(
        user=pull_request["user"]["login"],
        issue_key=issue_key, issue_url=issue_url, doc_url=doc_url,
    )
    if not has_signed_agreement or not in_authors_file:
        todo = ""
        if not has_signed_agreement:
            todo += "submitted a [signed contributor agreement]({agreement_url})".format(
                agreement_url=agreement_url,
            )
        if not has_signed_agreement and not in_authors_file:
            todo += " and "
        if not in_authors_file:
            todo += "added yourself to the [AUTHORS]({authors_url}) file".format(
                authors_url=authors_url,
            )
        comment += ("\n\n"
            "We can't start reviewing your pull request until you've {todo}."
            "Please see the [CONTRIBUTING]({contributing_url}) file for "
            "more information."
        ).format(todo=todo, contributing_url=contributing_url)
    return comment


if __name__ == "__main__":
    app.run()
