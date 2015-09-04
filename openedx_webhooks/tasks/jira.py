# coding=utf-8
from __future__ import unicode_literals, print_function

from collections import defaultdict

from openedx_webhooks import sentry, celery
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks import jira_session as jira
from openedx_webhooks.utils import jira_users, jira_group_members


@celery.task
def rescan_users(domain_groups):
    failures = defaultdict(dict)
    for groupname, domain in domain_groups.items():
        users_in_group = jira_group_members(groupname, session=jira, debug=True)
        usernames_in_group = set(u["name"] for u in users_in_group)
        sentry.client.extra_context({
            "groupname": groupname,
            "usernames_in_group": usernames_in_group,
        })

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

    if failures:
        logger.error("Failures in trying to rescan JIRA users: {}".format(failures))
    return failures
