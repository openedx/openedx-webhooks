from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from openedx_webhooks.bot_comments import (
    BOT_COMMENT_INDICATORS,
    BotComment,
    github_community_pr_comment,
    github_contractor_pr_comment,
    github_blended_pr_comment,
    github_committer_pr_comment,
)
from openedx_webhooks.info import (
    get_blended_project_id,
    get_bot_comments,
    get_jira_issue_key,
    get_people_file,
    is_bot_pull_request,
    is_committer_pull_request,
    is_contractor_pull_request,
    is_internal_pull_request,
    pull_request_has_cla,
)
from openedx_webhooks.oauth import github_bp, jira_bp
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.jira_work import transition_jira_issue
from openedx_webhooks.types import JiraDict, PrDict
from openedx_webhooks.utils import (
    get_jira_custom_fields,
    jira_paginated_get,
    log_check_response,
    sentry_extra_context,
    text_summary,
)


@dataclass
class PrTrackingInfo:
    """
    The information we want to have for a pull request.
    """
    bot_comments: Set[BotComment] = field(default_factory=set)
    jira_ticket_id: Optional[str] = None
    jira_project_for_ticket: Optional[str] = None
    jira_ticket_status: Optional[str] = None
    jira_labels: Set[str] = field(default_factory=set)
    jira_epic: Optional[JiraDict] = None
    jira_extra_fields: List[Tuple[str, str]] = field(default_factory=list)
    github_labels: Set[str] = field(default_factory=set)


def existing_bot_comments(pr: PrDict) -> Set[BotComment]:
    comment_ids = set()
    for comment in get_bot_comments(pr):
        body = comment["body"]
        for comment_id, snips in BOT_COMMENT_INDICATORS.items():
            if any(snip in body for snip in snips):
                comment_ids.add(comment_id)
    return comment_ids

def current_support_state(pr: PrDict) -> PrTrackingInfo:
    current = PrTrackingInfo()
    current.bot_comments = existing_bot_comments(pr)
    current.jira_ticket_id = get_jira_issue_key(pr)
    return current

def desired_support_state(pr: PrDict) -> Optional[PrTrackingInfo]:
    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]

    if is_bot_pull_request(pr):
        logger.info(f"@{user} is a bot, ignored.")
        return None

    if is_internal_pull_request(pr):
        logger.info(f"@{user} opened PR {repo} #{num} (internal PR)")
        return None

    desired = PrTrackingInfo()

    if is_contractor_pull_request(pr):
        desired.bot_comments.add(BotComment.CONTRACTOR)
        return desired

    desired.jira_ticket_status = "Needs Triage"

    has_signed_agreement = pull_request_has_cla(pr)
    blended_id = get_blended_project_id(pr)
    if blended_id is not None:
        comment = BotComment.BLENDED
        desired.jira_project_for_ticket = "BLENDED"
        desired.github_labels.add("blended")
        desired.jira_labels.add("blended")
        blended_epic = find_blended_epic(blended_id)
        if blended_epic is not None:
            desired.jira_epic = blended_epic
            custom_fields = get_jira_custom_fields(jira_bp.session)
            desired.jira_extra_fields.extend([
                ("Epic Link", blended_epic["key"]),
                ("Platform Map Area (Levels 1 & 2)",
                    blended_epic["fields"].get(custom_fields["Platform Map Area (Levels 1 & 2)"])),
            ])
    else:
        comment = BotComment.WELCOME
        desired.jira_project_for_ticket = "OSPR"
        desired.github_labels.add("open-source-contribution")
        committer = is_committer_pull_request(pr)
        if committer:
            comment = BotComment.CORE_COMMITTER
            desired.jira_labels.add("core-committer")
            desired.jira_ticket_status = "Open edX Community Review"
            desired.bot_comments.add(BotComment.CORE_COMMITTER)
            desired.github_labels.add("core committer")
        else:
            if not has_signed_agreement:
                desired.bot_comments.add(BotComment.NEED_CLA)
                desired.jira_ticket_status = "Community Manager Review"

    if has_signed_agreement:
        desired.bot_comments.add(BotComment.OK_TO_TEST)

    desired.bot_comments.add(comment)
    desired.github_labels.add(desired.jira_ticket_status.lower())

    return desired


def update_state(pr: PrDict, current: PrTrackingInfo, desired: PrTrackingInfo) -> Tuple[Optional[str], bool]:
    anything_happened = False

    # Check the Jira issue.
    if desired.jira_project_for_ticket is not None:
        if current.jira_ticket_id is None:
            extra_fields = desired.jira_extra_fields
            if desired.jira_epic:
                extra_fields.append(("Epic Link", desired.jira_epic["key"]))
            new_issue = create_ospr_issue(
                pr,
                project=desired.jira_project_for_ticket,
                labels=desired.jira_labels,
                extra_fields=extra_fields,
            )
            current.jira_ticket_id = issue_key = new_issue["key"]
            if desired.jira_ticket_status != "Needs Triage":
                transition_jira_issue(issue_key, desired.jira_ticket_status)

    # Check the bot comments.
    needed_comments = desired.bot_comments - current.bot_comments
    comment_body = ""
    if BotComment.WELCOME in needed_comments:
        comment_body += github_community_pr_comment(pr, new_issue)
        needed_comments.remove(BotComment.WELCOME)

    if BotComment.CONTRACTOR in needed_comments:
        comment_body += github_contractor_pr_comment(pr)
        needed_comments.remove(BotComment.CONTRACTOR)

    if BotComment.CORE_COMMITTER in needed_comments:
        comment_body += github_committer_pr_comment(pr, new_issue)
        needed_comments.remove(BotComment.CORE_COMMITTER)

    if BotComment.BLENDED in needed_comments:
        comment_body += github_blended_pr_comment(pr, new_issue, desired.jira_epic)
        needed_comments.remove(BotComment.BLENDED)

    if BotComment.OK_TO_TEST in needed_comments:
        if comment_body:
            comment_body += "\n<!-- jenkins ok to test -->"
        needed_comments.remove(BotComment.OK_TO_TEST)

    if BotComment.NEED_CLA in needed_comments:
        # This is handled in github_community_pr_comment.
        needed_comments.remove(BotComment.NEED_CLA)

    if comment_body:
        add_comment_to_pull_request(pr, comment_body)
        anything_happened = True

    assert needed_comments == set(), "Couldn't make comments: {}".format(needed_comments)

    # Check the GitHub labels.
    if desired.github_labels:
        update_labels_on_pull_request(pr, list(desired.github_labels))

    return current.jira_ticket_id, anything_happened


def find_blended_epic(project_id: int) -> Optional[JiraDict]:
    """
    Find the blended epic for a blended project.
    """
    jql = (
        '"Blended Project ID" ~ "BD-00{id}" or ' +
        '"Blended Project ID" ~ "BD-0{id}" or ' +
        '"Blended Project ID" ~ "BD-{id}"'
    ).format(id=project_id)
    issues = list(jira_paginated_get("/rest/api/2/search", jql=jql, obj_name="issues", session=jira_bp.session))
    issue = None
    if not issues:
        logger.info(f"Couldn't find a blended epic for {project_id}")
    elif len(issues) > 1:
        logger.info(f"Found {len(issues)} blended epics for {project_id}")
    else:
        issue = issues[0]
    return issue


def get_name_and_institution_for_pr(pr: PrDict) -> Tuple[str, Optional[str]]:
    """
    Get the author name and institution for a pull request.

    The returned name will always be a string. The institution might be None.

    Returns:
        name, institution
    """
    github = github_bp.session
    user = pr["user"]["login"]
    people = get_people_file()

    user_name = None
    if user in people:
        user_name = people[user].get("name", "")
    if not user_name:
        resp = github.get(pr["user"]["url"])
        if resp.ok:
            user_name = resp.json().get("name", user)
        else:
            user_name = user

    institution = people.get(user, {}).get("institution", None)

    return user_name, institution


def create_ospr_issue(pr, project, labels, extra_fields=None):
    """
    Create a new OSPR or OSPR-like issue for a pull request.

    Returns the JSON describing the issue.
    """
    num = pr["number"]
    repo = pr["base"]["repo"]["full_name"]

    user_name, institution = get_name_and_institution_for_pr(pr)

    custom_fields = get_jira_custom_fields(jira_bp.session)
    new_issue = {
        "fields": {
            "project": {
                "key": project,
            },
            "issuetype": {
                "name": "Pull Request Review",
            },
            "summary": pr["title"],
            "description": pr["body"],
            "labels": list(labels),
            "customfield_10904": pr["html_url"],        # "URL" is ambiguous, use the internal name.
            custom_fields["PR Number"]: num,
            custom_fields["Repo"]: repo,
            custom_fields["Contributor Name"]: user_name,
        }
    }
    if institution:
        new_issue["fields"][custom_fields["Customer"]] = [institution]
    if extra_fields:
        for name, value in extra_fields:
            new_issue["fields"][custom_fields[name]] = value
    sentry_extra_context({"new_issue": new_issue})

    logger.info(f"Creating new JIRA issue for PR {repo} #{num}...")
    resp = jira_bp.session.post("/rest/api/2/issue", json=new_issue)
    log_check_response(resp)

    new_issue_body = resp.json()
    new_issue["key"] = new_issue_body["key"]
    return new_issue


def add_comment_to_pull_request(pr, comment_body):
    """
    Add a comment to a pull request.
    """
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    url = f"/repos/{repo}/issues/{num}/comments"
    logger.info(f"Commenting on PR {repo} #{num}: {text_summary(comment_body, 90)!r}")
    resp = github_bp.session.post(url, json={"body": comment_body})
    log_check_response(resp)


def update_labels_on_pull_request(pr, labels):
    """
    Change the labels on a pull request.

    Arguments:
        pr: a dict of pull request info.
        labels: a list of strings.
    """
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    url = f"/repos/{repo}/issues/{num}"
    logger.info(f"Patching labels on PR {repo} #{num}: {labels}")
    resp = github_bp.session.patch(url, json={"labels": labels})
    log_check_response(resp)
