.. A new scriv changelog fragment.

- Stopped the bot from updating a repository's labels based on ``labels.yaml``, as this is now handled by the `repo_checks <https://github.com/openedx/repo-tools/tree/master/edx_repo_tools/repo_checks>`_ tool. The ``labels.yaml`` file is now unused and can be safely deleted from any openedx-webhooks data repositories.
