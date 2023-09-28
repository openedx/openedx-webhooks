"""
State-based updating of the information surrounding pull requests.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, cast

from openedx_webhooks.auth import get_github_session, get_jira_session
from openedx_webhooks.bot_comments import (
    BOT_COMMENT_INDICATORS,
    BOT_COMMENTS_FIRST,
    BotComment,
    extract_data_from_comment,
    format_data_for_comment,
    github_blended_pr_comment,
    github_community_pr_comment,
    github_community_pr_comment_closed,
    github_end_survey_comment,
    jira_issue_comment,
    no_contributions_thanks,
)
from openedx_webhooks.cla_check import (
    CLA_STATUS_BAD,
    CLA_STATUS_BOT,
    CLA_STATUS_GOOD,
    CLA_STATUS_NO_CONTRIBUTIONS,
    CLA_STATUS_PRIVATE,
    cla_status_on_pr,
    set_cla_status_on_pr,
)
from openedx_webhooks.gh_projects import (
    add_pull_request_to_project,
    pull_request_projects,
)
from openedx_webhooks.info import (
    get_blended_project_id,
    get_bot_comments,
    get_people_file,
    is_bot_pull_request,
    is_draft_pull_request,
    is_internal_pull_request,
    is_private_repo_no_cla_pull_request,
    projects_for_pr,
    pull_request_has_cla,
    repo_refuses_contributions,
)
from openedx_webhooks.labels import (
    GITHUB_CATEGORY_LABELS,
    GITHUB_STATUS_LABELS,
)
from openedx_webhooks import settings
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.jira_work import (
    update_jira_issue,
)
from openedx_webhooks.types import GhProject, JiraId, PrDict, PrId
from openedx_webhooks.utils import (
    get_jira_custom_fields,
    log_check_response,
    retry_get,
    sentry_extra_context,
    text_summary,
)


@dataclass
class BotData:
    """
    The data we store hidden in bot comments, to track our work.
    """
    # Is this a draft pull request?
    draft: bool = False
    # The Jira issues associated with the pull request.
    jira_issues: Set[JiraId] = field(default_factory=set)

    def update(self, data: dict) -> None:
        """Add data from `data` to this BotData."""
        if "draft" in data:
            self.draft = data["draft"]
        if "jira_issues" in data:
            self.jira_issues.update(JiraId(**jd) for jd in data["jira_issues"])


@dataclass
class PrCurrentInfo:
    """
    The current information we have for a pull request.
    """
    bot_comments: Set[BotComment] = field(default_factory=set)

    # The text of the first bot comment.
    bot_comment0_text: Optional[str] = None

    # The comment id of the survey comment, if any.
    bot_survey_comment_id: Optional[str] = None

    # The last-seen state stored in the first bot comment.
    bot_data: BotData = field(default_factory=BotData)

    # The actual Jira issue id.  Can differ from jira_mentioned_id if the
    # issue was moved, or can be None if the issue has been deleted.
    jira_id: Optional[str] = None

    # The actual set of labels on the pull request.
    github_labels: Set[str] = field(default_factory=set)

    # The GitHub projects the PR is in.
    github_projects: Set[GhProject] = field(default_factory=set)

    # The status of the cla check.
    cla_check: Optional[Dict[str, str]] = None


@dataclass
class PrDesiredInfo:
    """
    The information we want to have for a pull request.
    """
    # Is this an "external" pull request (True), or internal (False)?
    is_ospr: bool = False
    # Is this pull request being refused?
    is_refused: bool = False

    bot_comments: Set[BotComment] = field(default_factory=set)
    bot_comments_to_remove: Set[BotComment] = field(default_factory=set)
    jira_project: Optional[str] = None
    jira_title: Optional[str] = None
    jira_description: Optional[str] = None

    # The Jira instances we want to have issues on.
    jira_nicks: Set[str] = field(default_factory=set)

    # The Jira status to start a new issue at.
    jira_initial_status: Optional[str] = None

    # The Jira status we want to set on an existing issue. Can be None if we
    # don't need to force a new status, but can leave the existing status.
    jira_status: Optional[str] = None

    jira_labels: Set[str] = field(default_factory=set)

    # The bot-controlled labels we want to on the pull request.
    # See labels.py:CATEGORY_LABELS
    github_labels: Set[str] = field(default_factory=set)

    # The GitHub projects we want the PR in.
    github_projects: Set[GhProject] = field(default_factory=set)

    # The status of the cla check.
    cla_check: Optional[Dict[str, str]] = None


@dataclass
class FixResult:
    """
    Return value from PrTrackingFixer.result.
    """
    # The Jira issues associated with the pull request.
    jira_issues: Set[JiraId] = field(default_factory=set)
    # The Jira issues that were created or changed.
    changed_jira_issues: Set[JiraId] = field(default_factory=set)


def current_support_state(pr: PrDict) -> PrCurrentInfo:
    """
    Examine the world to determine what the current support state is.
    """
    prid = PrId.from_pr_dict(pr)
    current = PrCurrentInfo()

    full_bot_comments = list(get_bot_comments(prid))
    if full_bot_comments:
        current.bot_comment0_text = cast(str, full_bot_comments[0]["body"])
        current.bot_data.update(extract_data_from_comment(current.bot_comment0_text))
    for comment in full_bot_comments:
        body = comment["body"]
        for comment_id, snips in BOT_COMMENT_INDICATORS.items():
            if any(snip in body for snip in snips):
                current.bot_comments.add(comment_id)
                if comment_id == BotComment.SURVEY:
                    current.bot_survey_comment_id = comment["id"]
        current.bot_data.update(extract_data_from_comment(body))

    current.github_labels = set(lbl["name"] for lbl in pr["labels"])
    current.github_projects = set(pull_request_projects(pr))
    current.cla_check = cla_status_on_pr(pr)

    return current


def desired_support_state(pr: PrDict) -> PrDesiredInfo:
    """
    Examine a pull request to decide what state we want the world to be in.
    """
    desired = PrDesiredInfo()

    user = pr["user"]["login"]
    repo = pr["base"]["repo"]["full_name"]
    num = pr["number"]

    user_is_bot = is_bot_pull_request(pr)
    no_cla_is_needed = is_private_repo_no_cla_pull_request(pr)
    is_internal = is_internal_pull_request(pr)
    if user_is_bot:
        logger.info(f"@{user} is a bot, not an ospr.")
    elif no_cla_is_needed:
        logger.info(f"{repo}#{num} (@{user}) is in a private repo, not an ospr")
    elif is_internal:
        logger.info(f"@{user} acted on {repo}#{num}, internal PR, not an ospr")
    elif repo_refuses_contributions(pr):
        desired.is_refused = True
    else:
        desired.is_ospr = True

    if pr.get("hook_action") == "reopened":
        state = "reopened"
    elif pr["state"] == "open":
        state = "open"
    elif pr["merged"]:
        state = "merged"
    else:
        state = "closed"

    # A label of jira:xyz means we want a Jira issue in the xyz Jira.
    label_names = set(lbl["name"] for lbl in pr["labels"])
    desired.jira_nicks = {name.partition(":")[-1] for name in label_names if name.startswith("jira:")}

    desired.jira_initial_status = "Needs Triage"
    desired.jira_title = pr["title"]
    desired.jira_description = pr["body"] or ""

    blended_id = get_blended_project_id(pr)
    if blended_id is not None:
        desired.bot_comments.add(BotComment.BLENDED)
        desired.github_labels.add("blended")
        assert settings.GITHUB_BLENDED_PROJECT, "You must set GITHUB_BLENDED_PROJECT"
        desired.github_projects.add(settings.GITHUB_BLENDED_PROJECT)

    elif desired.is_ospr:
        if state in ["open", "reopened"]:
            comment = BotComment.WELCOME
        else:
            comment = BotComment.WELCOME_CLOSED
        desired.github_labels.add("open-source-contribution")
        desired.bot_comments.add(comment)

        assert settings.GITHUB_OSPR_PROJECT, "You must set GITHUB_OSPR_PROJECT"
        desired.github_projects.add(settings.GITHUB_OSPR_PROJECT)

    desired.github_projects.update(projects_for_pr(pr))

    has_signed_agreement = pull_request_has_cla(pr)
    if user_is_bot:
        desired.cla_check = CLA_STATUS_BOT
    elif no_cla_is_needed:
        desired.cla_check = CLA_STATUS_PRIVATE
    elif desired.is_refused:
        desired.cla_check = CLA_STATUS_NO_CONTRIBUTIONS
        desired.is_ospr = False
    elif is_internal or has_signed_agreement:
        desired.cla_check = CLA_STATUS_GOOD
    else:
        desired.cla_check = CLA_STATUS_BAD

    if desired.is_ospr:
        # Some PR states mean we want to insist on a Jira status.
        if is_draft_pull_request(pr):
            desired.jira_initial_status = "Waiting on Author"
            desired.bot_comments.add(BotComment.END_OF_WIP)

        if not has_signed_agreement:
            desired.bot_comments.add(BotComment.NEED_CLA)
            desired.jira_initial_status = "Community Manager Review"

        if state == "closed":
            desired.jira_status = "Rejected"
        elif state == "merged":
            desired.jira_status = "Merged"
        elif state == "reopened":
            desired.bot_comments_to_remove.add(BotComment.SURVEY)

        if state in ["closed", "merged"]:
            desired.bot_comments.add(BotComment.SURVEY)

    if desired.is_refused:
        desired.bot_comments.add(BotComment.NO_CONTRIBUTIONS)

    return desired


def json_safe_dict(dc):
    """
    Make a JSON-safe dict from a dataclass, for recording info during dry runs.
    """
    return {k:repr(v) for k, v in dataclasses.asdict(dc).items()}


class PrTrackingFixer:
    """
    Complex logic to compare the current and desired states and make needed changes.
    """

    def __init__(
        self,
        pr: PrDict,
        current: PrCurrentInfo,
        desired: PrDesiredInfo,
        actions: FixingActions | None = None,
    ) -> None:
        self.pr = pr
        self.current = current
        self.desired = desired
        self.prid = PrId.from_pr_dict(self.pr)
        self.actions = actions or FixingActions(self.prid)

        self.bot_data = copy.deepcopy(current.bot_data)
        self.fix_result: FixResult = FixResult()

    def result(self) -> FixResult:
        return self.fix_result

    def fix(self) -> None:
        """
        The main routine for making needed changes.
        """
        self.actions.initial_state(
            current=json_safe_dict(self.current),
            desired=json_safe_dict(self.desired),
        )

        self.fix_result.jira_issues = set(self.current.bot_data.jira_issues)

        if self.desired.cla_check != self.current.cla_check:
            assert self.desired.cla_check is not None
            self.actions.set_cla_status(status=self.desired.cla_check)

        if self.desired.is_ospr:
            self.fix_ospr()

        if self.desired.is_refused:
            self.fix_comments()

        # Make needed Jira issues.
        current_jira_nicks = {ji.nick for ji in self.current.bot_data.jira_issues}
        for jira_nick in self.desired.jira_nicks:
            if jira_nick not in current_jira_nicks:
                self._make_jira_issue(jira_nick)

    def fix_comments(self) -> None:
        fix_comment = True
        if self.pr["state"] == "closed" and self.current.bot_comments:
            # If the PR is closed and already has bot comments, then don't
            # change the bot comment.
            fix_comment = False
        if fix_comment:
            self._fix_bot_comment()
        self._add_bot_comments()

    def fix_ospr(self) -> None:
        # Draftiness
        self.bot_data.draft = is_draft_pull_request(self.pr)

        # Check the GitHub labels.
        self._fix_github_labels()

        # Check the bot comments.
        self.fix_comments()

        # Check the GitHub projects.
        for project in (self.desired.github_projects - self.current.github_projects):
            self.actions.add_pull_request_to_project(
                pr_node_id=self.pr["node_id"], project=project
            )

    def _make_jira_issue(self, jira_nick) -> None:
        """
        Make a Jira issue in a particular Jira server.
        """
        user_name, institution = get_name_and_institution_for_pr(self.pr)
        issue_data = self.actions.create_jira_issue(
            jira_nick=jira_nick,
            pr_url=self.pr["html_url"],
            project="TODOXXX",  # TODO: get the real project
            summary=self.desired.jira_title,
            description=self.desired.jira_description,
            labels=list(self.desired.jira_labels),
            user_name=user_name,
            institution=institution,
        )

        jira_id = JiraId(jira_nick, issue_data["key"])
        self.current.bot_data.jira_issues.add(jira_id)
        self.fix_result.jira_issues.add(jira_id)
        self.fix_result.changed_jira_issues.add(jira_id)

        comment_body = jira_issue_comment(self.pr, jira_id)
        comment_body += format_data_for_comment({
            "jira_issues": [jira_id.asdict()],
        })
        self.actions.add_comment_to_pull_request(comment_body=comment_body)

    def _fix_github_labels(self) -> None:
        """
        Reconcile the desired bot labels with the actual labels on GitHub.
        Take care to preserve any label we've never heard of.
        """
        desired_labels = set(self.desired.github_labels)
        ad_hoc_labels = self.current.github_labels - GITHUB_CATEGORY_LABELS - GITHUB_STATUS_LABELS
        desired_labels.update(ad_hoc_labels)

        if desired_labels != self.current.github_labels:
            self.actions.update_labels_on_pull_request(
                labels=list(desired_labels),
            )

    def _fix_bot_comment(self) -> None:
        """
        Reconcile the desired comments from the bot with what the bot has said.

        This only updates the first bot comment.
        """
        has_bot_comments = bool(self.current.bot_comments)

        # The comments we need in the first bot comment. Because we reconstruct
        # the full comment, we don't exclude the existing bot comments from the
        # set.
        needed_comments = self.desired.bot_comments & BOT_COMMENTS_FIRST

        comment_body = ""

        if BotComment.WELCOME in needed_comments:
            comment_body += github_community_pr_comment(self.pr)
            needed_comments.remove(BotComment.WELCOME)

        if BotComment.WELCOME_CLOSED in needed_comments:
            comment_body += github_community_pr_comment_closed(self.pr)
            needed_comments.remove(BotComment.WELCOME_CLOSED)
            if BotComment.SURVEY in self.desired.bot_comments:
                self.desired.bot_comments.remove(BotComment.SURVEY)

        if BotComment.BLENDED in needed_comments:
            comment_body += github_blended_pr_comment(self.pr)
            needed_comments.remove(BotComment.BLENDED)

        if BotComment.NO_CONTRIBUTIONS in needed_comments:
            comment_body += no_contributions_thanks(self.pr)
            needed_comments.remove(BotComment.NO_CONTRIBUTIONS)

        # These are handled in github_community_pr_comment and github_blended_pr_comment.
        if BotComment.NEED_CLA in needed_comments:
            needed_comments.remove(BotComment.NEED_CLA)
        if BotComment.END_OF_WIP in needed_comments:
            needed_comments.remove(BotComment.END_OF_WIP)
        # BTW, we never have WELCOME_CLOSED in desired.bot_comments

        comment_body += format_data_for_comment({
            "draft": is_draft_pull_request(self.pr)
        })

        if comment_body != self.current.bot_comment0_text:
            # If there are current-state comments, then we need to edit the
            # comment, otherwise create one.
            if has_bot_comments:
                self.actions.edit_comment_on_pull_request(comment_body=comment_body)
            else:
                self.actions.add_comment_to_pull_request(comment_body=comment_body)

        assert needed_comments == set(), f"Couldn't make first comments: {needed_comments}"

    def _add_bot_comments(self):
        """
        Add any additional bot comments as needed.

        More comments can be added as subsequent comments. We need anything
        in desired.bot_comments that we don't already have and that aren't
        first-comment parts.
        """
        needed_comments = self.desired.bot_comments - self.current.bot_comments - BOT_COMMENTS_FIRST

        if BotComment.SURVEY in needed_comments:
            body = github_end_survey_comment(self.pr)
            self.actions.add_comment_to_pull_request(comment_body=body)
            needed_comments.remove(BotComment.SURVEY)

        if BotComment.SURVEY in self.desired.bot_comments_to_remove:
            if self.current.bot_survey_comment_id:
                self.actions.delete_comment_on_pull_request(comment_id=self.current.bot_survey_comment_id)

        assert needed_comments == set(), f"Couldn't make comments: {needed_comments}"


def get_name_and_institution_for_pr(pr: PrDict) -> Tuple[str, Optional[str]]:
    """
    Get the author name and institution for a pull request.

    The returned name will always be a string. The institution might be None.

    Returns:
        name, institution
    """
    user = pr["user"]["login"]
    people = get_people_file()

    user_name = None
    if user in people:
        user_name = people[user].get("name", "")
    if not user_name:
        resp = retry_get(get_github_session(), pr["user"]["url"])
        if resp.ok:
            user_name = resp.json().get("name", user)
        else:
            user_name = user

    institution = people.get(user, {}).get("institution", None)

    return user_name, institution


class DryRunFixingActions:
    """
    Implementation of actions for dry runs.
    """
    jira_ids = itertools.count(start=9000)

    def __init__(self):
        self.action_calls = []

    def create_jira_issue(self, **kwargs):
        # This needs a special override because it has to return a Jira key.
        self.action_calls.append(("create_jira_issue", kwargs))
        return {
            "key": f"OSPR-{next(self.jira_ids)}",
            "fields": {
                "status": {
                    "name": "Needs Triage",
                },
            },
        }

    def __getattr__(self, name):
        def fn(**kwargs):
            self.action_calls.append((name, kwargs))
        return fn


class FixingActions:
    """
    Implementation for actions needed by the pull request fixer.

    These actions actually make the changes needed. All arguments
    must be JSON-serializable so that dry-runs can report on the
    actions.

    """

    def __init__(self, prid: PrId):
        self.prid = prid

    def initial_state(self, *, current: Dict, desired: Dict) -> None:
        """
        Does nothing when really fixing, but captures information for dry runs.
        """

    def create_jira_issue(
        self, *,
        jira_nick: str,
        pr_url: str,
        project: str,
        summary: Optional[str],
        description: Optional[str],
        labels: List[str],
        user_name: Optional[str],
        institution: Optional[str],
    ) -> Dict:
        """
        Create a new Jira issue for a pull request.

        Returns the JSON describing the issue.
        """

        custom_fields = get_jira_custom_fields(jira_nick)
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
                "labels": labels,
                "customfield_10904": pr_url,            # "URL" is ambiguous, use the internal name.
                custom_fields["PR Number"]: self.prid.number,
                custom_fields["Repo"]: self.prid.full_name,
                custom_fields["Contributor Name"]: user_name,
            }
        }
        if institution:
            new_issue["fields"][custom_fields["Customer"]] = [institution]
        sentry_extra_context({"new_issue": new_issue})

        logger.info(f"Creating new JIRA issue for PR {self.prid}...")
        resp = get_jira_session(jira_nick).post("/rest/api/2/issue", json=new_issue)
        log_check_response(resp)

        # Jira only sends the key.  Put it into the JSON we started with, and
        # return it as the state of the issue.
        new_issue_body = resp.json()
        new_issue["key"] = new_issue_body["key"]
        # Our issues all start as "Needs Triage".
        new_issue["fields"]["status"] = {"name": "Needs Triage"}
        return new_issue

    def update_jira_issue(self, *, jira_id: str, **update_kwargs) -> None:
        update_jira_issue(jira_id, **update_kwargs)

    def add_comment_to_pull_request(self, *, comment_body: str) -> None:
        """
        Add a comment to a pull request.
        """
        url = f"/repos/{self.prid.full_name}/issues/{self.prid.number}/comments"
        logger.info(f"Commenting on PR {self.prid}: {text_summary(comment_body, 90)!r}")
        resp = get_github_session().post(url, json={"body": comment_body})
        log_check_response(resp)

    def edit_comment_on_pull_request(self, *, comment_body: str) -> None:
        """
        Edit the bot-authored comment on this pull request.
        """
        bot_comments = list(get_bot_comments(self.prid))
        comment_id = bot_comments[0]["id"]
        url = f"/repos/{self.prid.full_name}/issues/comments/{comment_id}"
        logger.info(f"Updating comment on PR {self.prid}: {text_summary(comment_body, 90)!r}")
        resp = get_github_session().patch(url, json={"body": comment_body})
        log_check_response(resp)

    def delete_comment_on_pull_request(self, *, comment_id: str) -> None:
        url = f"/repos/{self.prid.full_name}/issues/comments/{comment_id}"
        logger.info(f"Deleting comment on PR {self.prid}")
        resp = get_github_session().delete(url)
        log_check_response(resp)

    def update_labels_on_pull_request(self, *, labels: List[str]) -> None:
        """
        Change the labels on a pull request.

        Arguments:
            labels: a list of strings.
        """
        url = f"/repos/{self.prid.full_name}/issues/{self.prid.number}"
        logger.info(f"Patching labels on PR {self.prid}: {labels}")
        resp = get_github_session().patch(url, json={"labels": labels})
        log_check_response(resp)

    def add_pull_request_to_project(self, *, pr_node_id: str, project: GhProject) -> None:
        """
        Add a pull request to a project.
        """
        try:
            add_pull_request_to_project(self.prid, pr_node_id, project)
        except Exception as exc:    # pylint: disable=broad-exception-caught
            logger.exception(f"Couldn't add PR to project: {exc}")

    def set_cla_status(self, *, status: Dict[str, str]) -> None:
        set_cla_status_on_pr(self.prid.full_name, self.prid.number, status)
