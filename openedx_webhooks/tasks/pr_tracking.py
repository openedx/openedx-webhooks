"""
State-based updating of the information surrounding pull requests.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, cast

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
    no_jira_mapping_comment,
    no_jira_server_comment,
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
    update_project_pr_custom_field,
)
from openedx_webhooks.info import (
    NoJiraMapping,
    NoJiraServer,
    get_blended_project_id,
    get_bot_comments,
    get_github_user_info,
    get_repo_spec,
    is_bot_pull_request,
    is_draft_pull_request,
    is_internal_pull_request,
    is_private_repo_no_cla_pull_request,
    jira_details_for_pr,
    projects_for_pr,
    pull_request_has_cla,
    repo_refuses_contributions,
)
from openedx_webhooks.labels import (
    GITHUB_CATEGORY_LABELS,
    GITHUB_CLOSED_PR_OBSOLETE_LABELS,
    GITHUB_MERGED_PR_OBSOLETE_LABELS,
    GITHUB_STATUS_LABELS,
)
from openedx_webhooks import settings
from openedx_webhooks.tasks import logger
from openedx_webhooks.tasks.jira_work import (
    update_jira_issue,
)
from openedx_webhooks.types import GhProject, JiraId, PrDict, PrId
from openedx_webhooks.utils import (
    get_pr_state,
    log_check_response,
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
    # Jira nick labels that have created error comments.
    jira_errors: Set[str] = field(default_factory=set)

    def update(self, data: dict) -> None:
        """Add data from `data` to this BotData."""
        if "draft" in data:
            self.draft = data["draft"]
        if "jira_issues" in data:
            self.jira_issues.update(JiraId(**jd) for jd in data["jira_issues"])
        if "jira_errors" in data:
            self.jira_errors.update(data["jira_errors"])


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
    jira_title: Optional[str] = None
    jira_description: Optional[str] = None

    # The Jira instances we want to have issues on.
    jira_nicks: Set[str] = field(default_factory=set)

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
    label_names = set(lbl["name"] for lbl in pr["labels"])

    user_is_bot = is_bot_pull_request(pr)
    no_cla_is_needed = is_private_repo_no_cla_pull_request(pr)
    is_internal = is_internal_pull_request(pr)
    if not is_internal:
        if pr["state"] == "closed" and "open-source-contribution" not in label_names:
            # If we are closing a PR, and it isn't already an OSPR, then it
            # shouldn't be considered one now.
            logger.info(f"{repo}#{num} is closing, but seemed to be internal originally")
            is_internal = True

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

    state = get_pr_state(pr)
    # A label of jira:xyz means we want a Jira issue in the xyz Jira.
    desired.jira_nicks = {name.partition(":")[-1] for name in label_names if name.startswith("jira:")}

    if "crash!123" in label_names:
        # Low-tech backdoor way to test error handling and reporting.
        raise Exception(f"A crash label was applied by {user}")

    desired.jira_title = pr["title"]
    desired.jira_description = (
        "(From {url} by {user_url})\n------\n\n{body}"
        ).format(
            url=pr["html_url"],
            body=(pr["body"] or ""),
            user_url=pr["user"]["html_url"],
        )

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
            desired.bot_comments.add(BotComment.END_OF_WIP)

        if not has_signed_agreement:
            desired.bot_comments.add(BotComment.NEED_CLA)

        if state == "reopened":
            desired.bot_comments_to_remove.add(BotComment.SURVEY)

#        # temp: Disable survey link on pull requests
#        # https://github.com/openedx/openedx-webhooks/issues/259
#        if state in ["closed", "merged"]:
#            desired.bot_comments.add(BotComment.SURVEY)

    if desired.is_refused and state not in ["closed", "merged"]:
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
        self.exceptions: List[Exception] = []

    def result(self) -> FixResult:
        return self.fix_result

    @contextlib.contextmanager
    def saved_exceptions(self):
        """
        A context manager to wrap around isolatable steps.

        An exception raised in the with-block will be added to `self.exceptions`.
        """
        try:
            yield
        except Exception as exc:    # pylint: disable=broad-exception-caught
            self.exceptions.append(exc)

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
            with self.saved_exceptions():
                self.actions.set_cla_status(status=self.desired.cla_check)

        if self.desired.is_ospr:
            with self.saved_exceptions():
                self._fix_ospr()

        if self.desired.is_refused:
            with self.saved_exceptions():
                self._fix_comments()

        # Make needed Jira issues.
        current_jira_nicks = {ji.nick for ji in self.current.bot_data.jira_issues}
        current_jira_nicks.update(self.current.bot_data.jira_errors)
        for jira_nick in self.desired.jira_nicks:
            if jira_nick not in current_jira_nicks:
                with self.saved_exceptions():
                    self._make_jira_issue(jira_nick)

        if self.exceptions:
            raise ExceptionGroup("Some actions failed", self.exceptions)

    def _fix_comments(self) -> None:
        fix_comment = True
        if self.pr["state"] == "closed" and self.current.bot_comments:
            # If the PR is closed and already has bot comments, then don't
            # change the bot comment.
            fix_comment = False
        if fix_comment:
            self._fix_bot_comment()
        self._add_bot_comments()

    def _fix_ospr(self) -> None:
        # Draftiness
        self.bot_data.draft = is_draft_pull_request(self.pr)

        # Check the GitHub labels.
        self._fix_github_labels()

        # Check the bot comments.
        self._fix_comments()

        # Check the GitHub projects.
        self._fix_projects()

    def _fix_projects(self) -> None:
        """
        Update projects for pr.
        """
        for project in (self.desired.github_projects - self.current.github_projects):
            project_item_id = self.actions.add_pull_request_to_project(
                pr_node_id=self.pr["node_id"], project=project
            )
            if not project_item_id:
                continue
            self.actions.update_project_pr_custom_field(
                field_name="Date opened",
                field_value=self.pr["created_at"],
                item_id=project_item_id,
                project=project
            )
            # get base repo owner info
            repo_spec = get_repo_spec(self.pr["base"]["repo"]["full_name"])
            owner = repo_spec.owner
            if not owner:
                continue
            # get user info if owner is an individual
            if repo_spec.is_owner_individual:
                owner_info = get_github_user_info(owner)
                if owner_info:
                    owner = f"{owner_info['name']} (@{owner})"
            self.actions.update_project_pr_custom_field(
                field_name="Repo Owner / Owning Team",
                field_value=owner,
                item_id=project_item_id,
                project=project
            )

    def _make_jira_issue(self, jira_nick) -> None:
        """
        Make a Jira issue in a particular Jira server.
        """
        try:
            project, issuetype = jira_details_for_pr(jira_nick, self.pr)
        except NoJiraServer:
            self.current.bot_data.jira_errors.add(jira_nick)
            comment_body = no_jira_server_comment(jira_nick)
        except NoJiraMapping:
            self.current.bot_data.jira_errors.add(jira_nick)
            comment_body = no_jira_mapping_comment(jira_nick)
        else:
            issue_data = self.actions.create_jira_issue(
                jira_nick=jira_nick,
                project=project,
                issuetype=issuetype,
                summary=self.desired.jira_title,
                description=self.desired.jira_description,
                labels=["from-GitHub"],
            )

            jira_id = JiraId(jira_nick, issue_data["key"])
            self.current.bot_data.jira_issues.add(jira_id)
            self.fix_result.jira_issues.add(jira_id)
            self.fix_result.changed_jira_issues.add(jira_id)
            comment_body = jira_issue_comment(self.pr, jira_id)

        self.actions.add_comment_to_pull_request(comment_body=comment_body)

    def _fix_github_labels(self) -> None:
        """
        Reconcile the desired bot labels with the actual labels on GitHub.
        Take care to preserve any label we've never heard of.
        """
        desired_labels = set(self.desired.github_labels)
        ad_hoc_labels = self.current.github_labels - GITHUB_CATEGORY_LABELS - GITHUB_STATUS_LABELS
        state = get_pr_state(self.pr)
        if state == "closed":
            ad_hoc_labels -= GITHUB_CLOSED_PR_OBSOLETE_LABELS
        elif state == "merged":
            ad_hoc_labels -= GITHUB_MERGED_PR_OBSOLETE_LABELS
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

        if not comment_body:
            # No body, no comment to make.
            return

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
        project: str,
        issuetype: str,
        summary: Optional[str],
        description: Optional[str],
        labels: List[str],
    ) -> Dict:
        """
        Create a new Jira issue for a pull request.

        Returns the JSON describing the issue.
        """

        new_issue = {
            "fields": {
                "project": {
                    "key": project,
                },
                "issuetype": {
                    "name": issuetype,
                },
                "summary": summary,
                "description": description,
                "labels": labels,
            }
        }
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

    def add_pull_request_to_project(self, *, pr_node_id: str, project: GhProject) -> str | None:
        """
        Add a pull request to a project.
        """
        try:
            return add_pull_request_to_project(self.prid, pr_node_id, project)
        except Exception:    # pylint: disable=broad-exception-caught
            logger.exception("Couldn't add PR to project")
        return None

    def update_project_pr_custom_field(self, *, field_name: str, field_value, item_id: str, project: GhProject) -> None:
        """
        Add a pull request to a project.
        """
        try:
            update_project_pr_custom_field(field_name, field_value, item_id, project)
        except Exception:    # pylint: disable=broad-exception-caught
            logger.exception(f"Couldn't update: {field_name} for a PR in project")

    def set_cla_status(self, *, status: Dict[str, str]) -> None:
        set_cla_status_on_pr(self.prid.full_name, self.prid.number, status)
