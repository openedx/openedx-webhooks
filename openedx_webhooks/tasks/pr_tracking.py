from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, cast

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
from openedx_webhooks.oauth import get_github_session, get_jira_session
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.jira_work import (
    delete_jira_issue,
    transition_jira_issue,
    update_jira_issue,
)
from openedx_webhooks.types import JiraDict, PrDict
from openedx_webhooks.utils import (
    get_jira_custom_fields,
    get_jira_issue,
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
    jira_id: Optional[str] = None
    jira_actual_id: Optional[str] = None    # Can differ if the issue was moved.
    jira_project: Optional[str] = None
    jira_title: Optional[str] = None
    jira_description: Optional[str] = None
    jira_status: Optional[str] = None
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
    current.jira_id = get_jira_issue_key(pr)
    if current.jira_id:
        issue = get_jira_issue(current.jira_id)
        current.jira_actual_id = issue["key"]
        current.jira_title = issue["fields"]["summary"]
        current.jira_description = issue["fields"]["description"]
        current.jira_status = issue["fields"]["status"]["name"]
    current.github_labels = set(lbl["name"] for lbl in pr["labels"])
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

    desired.jira_status = "Needs Triage"
    desired.jira_title = pr["title"]
    desired.jira_description = pr["body"]

    has_signed_agreement = pull_request_has_cla(pr)
    blended_id = get_blended_project_id(pr)
    if blended_id is not None:
        comment = BotComment.BLENDED
        desired.jira_project = "BLENDED"
        desired.github_labels.add("blended")
        desired.jira_labels.add("blended")
        blended_epic = find_blended_epic(blended_id)
        if blended_epic is not None:
            desired.jira_epic = blended_epic
            custom_fields = get_jira_custom_fields(get_jira_session())
            desired.jira_extra_fields.extend([
                ("Platform Map Area (Levels 1 & 2)",
                    blended_epic["fields"].get(custom_fields["Platform Map Area (Levels 1 & 2)"])),
            ])
    else:
        comment = BotComment.WELCOME
        desired.jira_project = "OSPR"
        desired.github_labels.add("open-source-contribution")
        committer = is_committer_pull_request(pr)
        if committer:
            comment = BotComment.CORE_COMMITTER
            desired.jira_labels.add("core-committer")
            desired.jira_status = "Open edX Community Review"
            desired.bot_comments.add(BotComment.CORE_COMMITTER)
            desired.github_labels.add("core committer")
        else:
            if not has_signed_agreement:
                desired.bot_comments.add(BotComment.NEED_CLA)
                desired.jira_status = "Community Manager Review"

    if has_signed_agreement:
        desired.bot_comments.add(BotComment.OK_TO_TEST)

    desired.bot_comments.add(comment)
    desired.github_labels.add(desired.jira_status.lower())

    return desired


class PrTrackingFixer:
    def __init__(self, pr: PrDict, current: PrTrackingInfo, desired: PrTrackingInfo):
        self.pr = pr
        self.current = current
        self.desired = desired
        self.happened = False

    def result(self) -> Tuple[Optional[str], bool]:
        return self.current.jira_id, self.happened

    def fix(self) -> None:
        comment_kwargs = {}

        # We might have an issue already, but in the wrong project.
        if self.current.jira_id is not None:
            assert self.current.jira_actual_id is not None
            mentioned_project = self.current.jira_id.partition("-")[0]
            actual_project = self.current.jira_actual_id.partition("-")[0]
            if mentioned_project != self.desired.jira_project:
                if actual_project == self.desired.jira_project:
                    # Looks like the issue already got moved to the right
                    # project.
                    self.current.jira_id = self.current.jira_actual_id
                else:
                    # Delete the existing issue and forget the current state.
                    delete_jira_issue(self.current.jira_actual_id)
                    comment_kwargs["deleted_issue_key"] = self.current.jira_id
                    self.current.jira_id = None
                    self.current.jira_actual_id = None
                    self.current.jira_project = None
                    self.current.jira_title = None
                    self.current.jira_description = None
                    self.current.jira_status = None

        # If needed, make a Jira issue.
        if self.desired.jira_project is not None:
            if self.current.jira_id is None:
                extra_fields = self.desired.jira_extra_fields
                if self.desired.jira_epic:
                    extra_fields.append(("Epic Link", self.desired.jira_epic["key"]))
                new_issue = create_ospr_issue(
                    self.pr,
                    project=self.desired.jira_project,
                    summary=self.desired.jira_title,
                    description=self.desired.jira_description,
                    labels=self.desired.jira_labels,
                    extra_fields=extra_fields,
                )
                self.current.jira_id = new_issue["key"]
                self.current.jira_status = new_issue["fields"]["status"]["name"]
                self.current.jira_title = self.desired.jira_title
                self.current.jira_description = self.desired.jira_description
                self.current.jira_labels = self.desired.jira_labels
                self.current.jira_epic = self.desired.jira_epic
                self.happened = True

        # Check the state of the Jira issue.
        if self.desired.jira_status != self.current.jira_status:
            transition_jira_issue(self.current.jira_id, self.desired.jira_status)
            self.happened = True

        update_kwargs: Dict[str, Any] = {}
        if self.desired.jira_title != self.current.jira_title:
            update_kwargs["summary"] = self.desired.jira_title
        if self.desired.jira_description != self.current.jira_description:
            update_kwargs["description"] = self.desired.jira_description
        if self.desired.jira_labels != self.current.jira_labels:
            update_kwargs["labels"] = self.desired.jira_labels
        if self.desired.jira_epic is not None:
            if self.current.jira_epic is None or (self.desired.jira_epic["key"] != self.current.jira_epic["key"]):
                update_kwargs["epic_link"] = self.desired.jira_epic["key"]
        if update_kwargs:
            update_jira_issue(self.current.jira_id, extra_fields=self.desired.jira_extra_fields, **update_kwargs)
            self.current.jira_title = self.desired.jira_title
            self.current.jira_description = self.desired.jira_description
            self.current.jira_labels = self.desired.jira_labels
            self.current.jira_epic = self.desired.jira_epic
            self.happened = True

        # Check the GitHub labels.
        if self.desired.github_labels != self.current.github_labels:
            update_labels_on_pull_request(self.pr, list(self.desired.github_labels))
            self.happened = True

        # Check the bot comments.
        needed_comments = self.desired.bot_comments - self.current.bot_comments
        comment_body = ""
        if BotComment.WELCOME in needed_comments:
            comment_body += github_community_pr_comment(self.pr, cast(str, self.current.jira_id), **comment_kwargs)
            needed_comments.remove(BotComment.WELCOME)

        if BotComment.CONTRACTOR in needed_comments:
            comment_body += github_contractor_pr_comment(self.pr, **comment_kwargs)
            needed_comments.remove(BotComment.CONTRACTOR)

        if BotComment.CORE_COMMITTER in needed_comments:
            comment_body += github_committer_pr_comment(self.pr, cast(str, self.current.jira_id), **comment_kwargs)
            needed_comments.remove(BotComment.CORE_COMMITTER)

        if BotComment.BLENDED in needed_comments:
            comment_body += github_blended_pr_comment(
                self.pr,
                cast(str, self.current.jira_id),
                self.current.jira_epic,
                **comment_kwargs
            )
            needed_comments.remove(BotComment.BLENDED)

        if BotComment.OK_TO_TEST in needed_comments:
            if comment_body:
                comment_body += "\n<!-- jenkins ok to test -->"
            needed_comments.remove(BotComment.OK_TO_TEST)

        if BotComment.NEED_CLA in needed_comments:
            # This is handled in github_community_pr_comment.
            needed_comments.remove(BotComment.NEED_CLA)

        if comment_body:
            # If there are current-state comments, then we need to edit the
            # comment, otherwise create one.
            if self.current.bot_comments:
                edit_comment_on_pull_request(self.pr, comment_body)
            else:
                add_comment_to_pull_request(self.pr, comment_body)
            self.happened = True

        assert needed_comments == set(), "Couldn't make comments: {}".format(needed_comments)


def find_blended_epic(project_id: int) -> Optional[JiraDict]:
    """
    Find the blended epic for a blended project.
    """
    jql = (
        '"Blended Project ID" ~ "BD-00{id}" or ' +
        '"Blended Project ID" ~ "BD-0{id}" or ' +
        '"Blended Project ID" ~ "BD-{id}"'
    ).format(id=project_id)
    issues = list(jira_paginated_get("/rest/api/2/search", jql=jql, obj_name="issues", session=get_jira_session()))
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
    github = get_github_session()
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


def create_ospr_issue(pr, project, summary, description, labels, extra_fields=None):
    """
    Create a new OSPR or OSPR-like issue for a pull request.

    Returns the JSON describing the issue.
    """
    num = pr["number"]
    repo = pr["base"]["repo"]["full_name"]

    user_name, institution = get_name_and_institution_for_pr(pr)

    custom_fields = get_jira_custom_fields(get_jira_session())
    new_issue = {
        "fields": {
            "project": {
                "key": project,
            },
            "issuetype": {
                "name": "Pull Request Review",
            },
            "summary": summary,
            "description": description,
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
    resp = get_jira_session().post("/rest/api/2/issue", json=new_issue)
    log_check_response(resp)

    # Jira only sends the key.  Put it into the JSON we started with, and
    # return it as the state of the issue.
    new_issue_body = resp.json()
    new_issue["key"] = new_issue_body["key"]
    # Our issues all start as "Needs Triage".
    new_issue["fields"]["status"] = {"name": "Needs Triage"}
    return new_issue


def add_comment_to_pull_request(pr: PrDict, comment_body: str) -> None:
    """
    Add a comment to a pull request.
    """
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]
    url = f"/repos/{repo}/issues/{num}/comments"
    logger.info(f"Commenting on PR {repo} #{num}: {text_summary(comment_body, 90)!r}")
    resp = get_github_session().post(url, json={"body": comment_body})
    log_check_response(resp)


def edit_comment_on_pull_request(pr: PrDict, comment_body: str) -> None:
    """
    Edit the bot-authored comment on this pull request.
    """
    repo = pr["base"]["repo"]["full_name"]
    bot_comments = list(get_bot_comments(pr))
    comment_id = bot_comments[0]["id"]
    url = f"/repos/{repo}/issues/comments/{comment_id}"
    resp = get_github_session().patch(url, json={"body": comment_body})
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
    resp = get_github_session().patch(url, json={"labels": labels})
    log_check_response(resp)
