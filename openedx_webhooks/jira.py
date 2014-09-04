import json
from pprint import pprint

import requests
from urlobject import URLObject

from .utils import memoize, paginated_api


class MissingUserInfo(Exception):
    pass


def pop_dict_id(d):
    id = d["id"]
    del d["id"]
    return (id, d)


# used by `Jira.resource_map()` and friends
MAPPED_RESOURCES = ("project", "issuetype", "priority", "resolution", "status")


class Jira(object):
    """Wrapper object for dealing with JIRA instances."""
    def __init__(self, host, session=None, auth=None):
        self.host = host
        self.session = session or requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        if auth:
            self.session.auth = auth
        self.user_map = {}  # used to memoize _get_or_create_user

    ## Basic requests stuff.

    def get(self, url, retries=3):
        """Returns a requests object."""
        url = self.url(url)
        for _ in xrange(retries):
            resp = self.session.get(url)
            try:
                resp.json()
            except ValueError:
                continue
            else:
                return resp
        return self.session.get(url)

    def post(self, url, data=None, as_json=None):
        assert not (data and as_json), "Only provide one of data or as_json"
        assert data or as_json, "Provide either data or as_json"
        if as_json:
            data = json.dumps(as_json)
        url = self.url(url)
        return self.session.post(url, data)

    def put(self, url, data=None, as_json=None):
        assert not (data and as_json), "Only provide one of data or as_json"
        assert data or as_json, "Provide either data or as_json"
        if as_json:
            data = json.dumps(as_json)
        url = self.url(url)
        return self.session.put(url, data)

    def delete(self, url):
        url = self.url(url)
        return self.session.delete(url)

    def url(self, url):
        if not isinstance(url, URLObject):
            url = self.host.with_path(url)
        return url

    def paginated_api(self, url, object_name, start=0):
        url = self.url(url)
        return paginated_api(url, object_name, session=self.session, start=start)

    ## JIRA concepts.

    def get_issue(self, key):
        issue_resp = self.get("/rest/api/2/issue/{key}".format(key=key))
        if issue_resp.ok:
            data = issue_resp.json()
            return data
        else:
            return None

    def get_jql_issues(self, jql, offset=0):
        url = self.url("/rest/api/2/search").add_query_param("jql", jql)
        issues = self.paginated_api(url, "issues", start=offset)
        return issues

    def create_user(self, user):
        kwargs = {
            "username": user["name"],
            "name": user["displayName"],
            "email": user["emailAddress"],
        }
        return self._create_user(**kwargs)

    def _create_user(self, username, name, email):
        user_url = self.url("/rest/api/2/user")
        data = {
            "name": username,
            "displayName": name,
            "emailAddress": email,
        }
        create_resp = self.post(user_url, as_json=data)
        if create_resp.ok:
            return create_resp.json()
        else:
            raise requests.exceptions.RequestException(create_resp.text)

    def get_or_create_user(self, user):
        kwargs = {
            "username": user["name"],
        }
        if "displayName" in user:
            kwargs["name"] = user["displayName"]
        if "emailAddress" in user:
            kwargs["email"] = user["emailAddress"]
        return self._get_or_create_user(**kwargs)

    def _get_or_create_user(self, username, name=None, email=None):
        if username in self.user_map:
            return self.user_map[username]

        user_url = self.url("/rest/api/2/user").add_query_param("username", username)
        user_resp = self.get(user_url)
        if user_resp.ok:
            self.user_map[username] = user_resp.json()
            return self.user_map[username]

        # user doesn't exist!
        if not name or not email:
            raise MissingUserInfo()
        self.user_map[username] = self._create_user(username, name, email)
        return self.user_map[username]

    @property
    def field_map(self):
        field_resp = self.get_resource("field")
        return dict(pop_dict_id(f) for f in field_resp.json())

    @property
    def custom_field_names(self):
        """
        Returns a mapping of custom field name to system ID.
        """
        return {
            value["name"]: id
            for id, value in self.field_map.items()
            if value["custom"]
        }

    @property
    def user_fields(self):
        """
        Returns a set of field IDs that are of type "user"
        """
        return set(
            id for id, value in self.field_map.items()
            if value.get("schema", {}).get("type", "") == "user"
        )

    @memoize
    def get_resource(self, resource):
        resp = self.get("/rest/api/2/{resource}".format(resource=resource))
        if not resp.ok:
            raise requests.exceptions.RequestException(resp.text)
        return resp

    @memoize
    def get_project(self, project_key):
        resp = self.get("/rest/api/2/project/{key}".format(key=project_key))
        if not resp.ok:
            raise requests.exceptions.RequestException(resp.text)
        return resp

    def resource_map(self, resource):
        """
        Returns a mapping of ID to name for the given resource.
        """
        resp = self.get_resource(resource)
        return {x["id"]: x["name"] for x in resp.json()}

    @property
    def project_map(self):
        return self.resource_map("project")

    @property
    def issuetype_map(self):
        return self.resource_map("issuetype")

    @property
    def priority_map(self):
        return self.resource_map("priority")

    @property
    def resolution_map(self):
        return self.resource_map("resolution")

    @property
    def status_map(self):
        return self.resource_map("status")

    def make_link(self, issue_key, url, title):
        link_data = {
            "object": {
                "url": url,
                "title": title,
            }
        }
        link_url = self.url("/rest/api/2/issue/{key}/remotelink".format(key=issue_key))
        link_resp = self.post(link_url, as_json=link_data)
        if not link_resp.ok:
            print("Adding link to {} failed".format(link_url))
            errors = link_resp.json()["errors"]
            pprint(errors)

    def transition(self, issue_key, to, resolution=None):
        transitions_url = (
            "/rest/api/2/issue/{key}/transitions"
            "?expand=transitions.fields".format(key=issue_key)
        )
        transitions_resp = self.get(transitions_url)
        if not transitions_resp.ok:
            msgs = transitions_resp.json()["errorMessages"]
            raise requests.exceptions.RequestException(msgs)

        for t in transitions_resp.json()["transitions"]:
            if t["to"]["name"] == to:
                data = {
                    "transition": {
                        "id": t["id"]
                    }
                }

                if t.get("fields", {}):
                    fields = {}
                    if t["fields"]["resolution"] and resolution:
                        fields["resolution"] = {"name": resolution}
                    if fields:
                        data["fields"] = fields

                set_transition_resp = self.post(transitions_url, as_json=data)
                if not set_transition_resp.ok:
                    msgs = set_transition_resp.json()["errorMessages"]
                    raise requests.exceptions.RequestException(msgs)
                return True

        return False
