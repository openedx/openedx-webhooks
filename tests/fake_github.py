"""A fake implementation of the GitHub API."""

import os.path
import random
import re
from datetime import datetime


class FakeGitHub:
    """A fake implementation of the GitHub API."""

    API_HOST = "api.github.com"
    RAW_HOST = "raw.githubusercontent.com"

    WEBHOOK_BOT_NAME = "the-webhook-bot"

    def __init__(self, requests_mocker):
        self.requests_mocker = requests_mocker
        self.requests_mocker.get(
            "https://api.github.com/user",
            json={"login": self.WEBHOOK_BOT_NAME}
        )

        self.requests_mocker.get(
            re.compile(f"https://{self.RAW_HOST}/edx/repo-tools-data/master/"),
            text=self._repo_data_callback,
        )

    def _repo_data_callback(self, request, _):
        """Read repo_data data from local data."""
        return self._repo_data(filename=request.path.split("/")[-1])

    def _repo_data(self, filename):
        """Read data from a file in our repo_data directory."""
        repo_data_dir = os.path.join(os.path.dirname(__file__), "repo_data")
        with open(os.path.join(repo_data_dir, filename)) as data:
            return data.read()

    def fake_user(self, user_data):
        """Define a user in the fake GitHub."""
        user_data.setdefault("type", "User")
        self.requests_mocker.get(
            f"https://{self.API_HOST}/users/{user_data['login']}",
            json=user_data,
        )

    def make_pull_request(
        self,
        user, title="generic title", body="generic body", number=None,
        base_repo_name="edx/edx-platform",
        base_ref="master", head_ref="patch-1", user_type="User",
        created_at=None
    ):
        """Create fake pull request data."""
        # This should really use a framework like factory_boy.
        created_at = created_at or datetime.now().replace(microsecond=0)
        if number is None:
            number = random.randint(1111, 9999)
        return {
            "user": {
                "login": user,
                "type": user_type,
                "url": f"https://{self.API_HOST}/users/{user}",
            },
            "number": number,
            "title": title,
            "body": body,
            "created_at": created_at.isoformat(),
            "head": {
                "repo": {
                    "full_name": f"{user}/some-repo",
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

    def make_closed_pull_request(self, merged, **kwargs):
        """Create fake data for a closed pull request."""
        pr = self.make_pull_request(**kwargs)
        pr["merged"] = merged
        return pr

    def _pr_api_url(self, pr, suffix=""):
        """Construct the API url for a pull request."""
        repo = pr["base"]["repo"]["full_name"]
        num = pr["number"]
        url = f"https://{self.API_HOST}/repos/{repo}/issues/{num}{suffix}"
        return url

    def fake_comments(self, pr, comments):
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

    def fake_labels(self, repo, label_data):
        """Create fake labels in a repo."""
        self.requests_mocker.get(
            f"https://{self.API_HOST}/repos/{repo}/labels",
            json=label_data,
        )

    def labels_post(self, repo):
        """Get the mocked POST endpoint for creating labels in a repo."""
        return self.requests_mocker.post(f"https://{self.API_HOST}/repos/{repo}/labels")

    def labels_delete(self, repo):
        """Get the mocked DELETE endpoint for deleting labels in a repo."""
        return self.requests_mocker.delete(
            re.compile(f"https://{self.API_HOST}/repos/{repo}/labels"),
        )
