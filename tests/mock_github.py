"""A mock implementation of the GitHub API."""

import os.path
import random
import re
from datetime import datetime


class MockGitHub:
    """A mock implementation of the GitHub API."""

    WEBHOOK_BOT_NAME = "the-webhook-bot"

    def __init__(self, requests_mocker):
        self.requests_mocker = requests_mocker
        self.requests_mocker.get(
            "https://api.github.com/user",
            json={"login": self.WEBHOOK_BOT_NAME}
        )

        self.requests_mocker.get(
            re.compile("https://raw.githubusercontent.com/edx/repo-tools-data/master/"),
            text=self._repo_data_callback,
        )

    def _repo_data_callback(self, request, _):
        """Read repo_data data from local data."""
        repo_data_dir = os.path.join(os.path.dirname(__file__), "repo_data")
        filename = request.path.split("/")[-1]
        with open(os.path.join(repo_data_dir, filename)) as data:
            return data.read()

    def mock_user(self, user_data):
        """Define a user in the mock GitHub."""
        user_data.setdefault("type", "User")
        self.requests_mocker.get(
            "https://api.github.com/users/{}".format(user_data["login"]),
            json=user_data,
        )

    def make_pull_request(
        self,
        user, title="generic title", body="generic body", number=None,
        base_repo_name="edx/edx-platform", head_repo_name=None,
        base_ref="master", head_ref="patch-1", user_type="User",
        created_at=None
    ):
        """Create fake pull request data."""
        # This should really use a framework like factory_boy.
        created_at = created_at or datetime.now().replace(microsecond=0)
        if head_repo_name is None:
            head_repo_name = f"{user}/edx-platform"
        if number is None:
            number = random.randint(1111, 9999)
        return {
            "user": {
                "login": user,
                "type": user_type,
                "url": f"https://api.github.com/users/{user}",
            },
            "number": number,
            "title": title,
            "body": body,
            "created_at": created_at.isoformat(),
            "head": {
                "repo": {
                    "full_name": head_repo_name,
                },
                "ref": head_ref,
            },
            "base": {
                "repo": {
                    "full_name": base_repo_name,
                },
                "ref": base_ref,
            },
            "html_url": f"https://github.com/{base_repo_name}/pull/{number}",
        }

    def _pr_api_url(self, pr, suffix=""):
        """Construct the API url for a pull request."""
        url = "https://api.github.com/repos/{repo}/issues/{num}".format(
            repo=pr["base"]["repo"]["full_name"],
            num=pr["number"],
        )
        url += suffix
        return url

    def mock_comments(self, pr, comments):
        """Create fake comments on a fake PR."""
        self.requests_mocker.get(
            self._pr_api_url(pr, "/comments"),
            json=comments,
        )

    def comments_post(self, pr):
        """Get the mocked POST endpoint for creating comments on a PR."""
        return self.requests_mocker.post(self._pr_api_url(pr, "/comments"))

    def pr_patch(self, pr):
        """Get the mocked PATCH endpoint for adjusting a PR."""
        return self.requests_mocker.patch(self._pr_api_url(pr))
