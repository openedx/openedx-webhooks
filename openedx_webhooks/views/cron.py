from __future__ import unicode_literals, print_function

import json
import bugsnag
from flask import make_response
from flask_dance.contrib.jira import jira
from openedx_webhooks import app
from openedx_webhooks.utils import jira_users, jira_group_members


@app.route("/cron/daily", methods=("POST",))
def cron_daily():
    new_edx_employees = []
    new_edx_employee_failures = {}

    edx_employee_users = jira_group_members("edx-employees", session=jira, debug=True)
    edx_employee_usernames = set(u["name"] for u in edx_employee_users)
    bugsnag_context = {"edx_employee_usernames": edx_employee_usernames}
    bugsnag.configure_request(meta_data=bugsnag_context)

    # for all users with an "@edx.org" email address, put them in the
    # edx-employees group
    for user in jira_users(filter="@edx.org", session=jira, debug=True):
        if not user["email"].endswith("@edx.org"):
            pass
        username = user["name"]
        if username not in edx_employee_usernames:
            # add the user to edx-employees!
            resp = jira.post("/rest/api/2/group/user", json={"name": username})
            if not resp.ok:
                new_edx_employee_failures[username] = resp.text
                bugsnag_context["new_edx_employee_failures"] = new_edx_employee_failures
                bugsnag.configure_request(meta_data=bugsnag_context)
            else:
                new_edx_employees.append(username)

    if new_edx_employee_failures:
        resp = make_response(json.dumps(new_edx_employee_failures), 502)
    else:
        resp = make_response(json.dumps(new_edx_employees), 200)
    resp.headers["Content-Type"] = "application/json"
    return resp
