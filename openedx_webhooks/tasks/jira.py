from collections import defaultdict

from openedx_webhooks import celery
from openedx_webhooks.oauth import jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.utils import jira_group_members, jira_users, sentry_extra_context


@celery.task
def rescan_users(domain_groups):
    jira = jira_bp.session
    failures = defaultdict(dict)
    for groupname, domain in domain_groups.items():
        users_in_group = jira_group_members(groupname, session=jira, debug=True)
        usernames_in_group = set(u["name"] for u in users_in_group)
        sentry_extra_context({
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
                    # Is this a failure saying that the user is already in
                    # the group? If so, ignore it.
                    nothing_to_do_msg = (
                        "Cannot add user '{username}', "
                        "user is already a member of '{groupname}'"
                    ).format(username=username, groupname=groupname)
                    error = resp.json()
                    if error.get("errorMessages", []) == [nothing_to_do_msg]:
                        continue
                    else:
                        # it's some other kind of failure, so log it
                        failures[groupname][username] = resp.text

    if failures:
        logger.error("Failures in trying to rescan JIRA users: {}".format(failures))
    return failures
