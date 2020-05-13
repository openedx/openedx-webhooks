"""
Generic GitHub domain models.
"""

import arrow


class GithubWebHookRequestHeader(object):
    """
    Represent a GitHub webhook request header.

    Attributes:
        headers (flask.Request.headers): HTTP headers as received by Flask
    """

    def __init__(self, headers):
        """
        Init.

        Arguments:
            headers (flask.Request.headers): HTTP headers as received by Flask
        """
        self.headers = headers

    @property
    def event_type(self):
        """
        str: The webhook event type.
        """
        return self.headers.get('X-Github-Event')

    @property
    def signature(self):
        """
        str: Hash signature of the payload.
        """
        return self.headers.get('X-Hub-Signature')


class GithubWebHookEvent(object):
    """
    A GitHub webhook event.

    Attributes:
        event_type (str): GitHub event type
        event (Dict[str, Any]): The parsed event payload
    """

    def __init__(self, event_type, event):
        """
        Init.

        Arguments:
            event_type (str): GitHub event type
            event (Dict[str, Any]): The parsed event payload
        """
        self.event_type = event_type
        self.event = event

    @property
    def _event_resource_key(self):
        """
        str: GitHub reource type, such as 'pull_request' or 'issue'.
        """
        keys = ('pull_request', 'issue')
        try:
            return next((k for k in keys if self.event_type.startswith(k)))
        except StopIteration:
            return self.event_type

    @property
    def event_resource(self):
        return self.event[self._event_resource_key]

    @property
    def action(self):
        """
        str: The action of the event.
        """
        return self.event['action']

    @property
    def description(self):
        """
        str: Description of the event.
        """
        return "{}: {}".format(self.event_type, self.action)

    @property
    def html_url(self):
        """
        str: URL of the GitHub resource that the event is about.
        """
        return self.event_resource['html_url']

    @property
    def repo_full_name(self):
        """
        str: Full name of repo.
        """
        return self.event['repository']['full_name']

    @property
    def repo_name(self):
        """
        str: Name of repo.
        """
        return self.event['repository']['name']

    @property
    def repo_owner_login(self):
        """
        str: Login of repo owner.
        """
        return self.event['repository']['owner']['login']

    @property
    def sender_login(self):
        """
        str: GitHub login of the user who sent the event.
        """
        return self.event['sender']['login']

    @property
    def updated_at(self):
        """
        datetime.datetime: Datetime of the event.
        """
        dt = self.event_resource['updated_at']
        return arrow.get(dt).datetime
