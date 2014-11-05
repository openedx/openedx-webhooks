from __future__ import unicode_literals, print_function

import sys
import json
import bugsnag
from collections import defaultdict
from flask import make_response
from flask_dance.contrib.jira import jira
from openedx_webhooks import app
from openedx_webhooks.utils import jira_users, jira_group_members


@app.route("/cron/daily", methods=("POST",))
def cron_daily():
    # a mapping of group name to email domain
    domain_groups = {
        "edx-employees": "@edx.org",
    }
    failures = defaultdict(dict)

    for groupname, domain in domain_groups.items():
        users_in_group = jira_group_members("edx-employees", session=jira, debug=True)
        usernames_in_group = set(u["name"] for u in users_in_group)
        bugsnag_context = {
            "groupname": groupname,
            "usernames_in_group": usernames_in_group,
        }
        bugsnag.configure_request(meta_data=bugsnag_context)

        for user in jira_users(filter=domain, session=jira, debug=True):
            if not user["email"].endswith(domain):
                pass
            username = user["name"]
            if username not in usernames_in_group:
                # add the user to the group!
                resp = jira.post(
                    "/rest/api/2/group/user?groupname={}".format(groupname),
                    json={"name": username},
                )
                if not resp.ok:
                    failures[groupname][username] = resp.text

    resp = make_response(json.dumps(failures), 502 if failures else 200)
    resp.headers["Content-Type"] = "application/json"
    return resp
