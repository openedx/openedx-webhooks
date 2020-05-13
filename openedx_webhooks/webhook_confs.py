"""
Configuration for webhooks we want to install.
"""

import os

from flask import url_for

# List[Dict[str, Any]]: A list of GitHub webhook configurations. Currently
#     we use these configurations to create webhooks in the specified GitHub
#     repo. Each configuration expects the following keys:
#
# -  config (Dict[str, Any]): See `GitHub documentation`_ for more details
#    on possible keys and values.
# -  events (List[str]): See `list of possible events`_.
#
# .. _GitHub documentation: https://developer.github.com/v3/repos/hooks/#create-a-hook
# .. _list of possible events: https://developer.github.com/webhooks/#events
WEBHOOK_CONFS = [{
    'config': {
        'url': url_for("github_views.pull_request", _external=True),
        'content_type': 'json',
        'insecure_ssl': False,
    },
    'events': ['pull_request']
}, {
    'config': {
        'url': url_for("github_views.hook_receiver", _external=True),
        'content_type': 'json',
        'insecure_ssl': False,
        'secret': os.environ.get('GITHUB_WEBHOOKS_SECRET'),
    },
    'events': [
        'issue_comment',
        'pull_request',
        'pull_request_review',
        'pull_request_review_comment',
    ]
}]
