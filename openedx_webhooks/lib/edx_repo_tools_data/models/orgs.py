# -*- coding: utf-8 -*-
"""
edx/repo-tools-data related domain models.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from ...exceptions import NotFoundError


# TODO: These classes share quite a bit in common with classes in people.py
#       module. Refactor?
class Orgs(object):
    """
    Logical representation of `orgs.yaml`.

    Attributes:
        _data (Dict[str, Any]): The raw dictionary as parsed from the
            yaml file
    """

    def __init__(self, data):
        """
        Init.

        Arguments:
            data (Dict[str, Any]): The raw dictionary as parsed from
                the yaml file
        """
        self._data = data

    def __iter__(self):
        for k, v in self._data.items():
            yield Org(k, v)

    def get(self, key):
        """
        Get a specific org by `orgs.yaml` key.

        Arguments:
            key (str)

        Returns:
            openedx_webhooks.lib.edx_repo_tools_data.models.Org

        Raises:
            openedx_webhooks.lib.exceptions.NotFoundError: If key cannot
                be found
        """
        org = self._data.get(key)

        if not org:
            raise NotFoundError("{} could not be found".format(key))

        return Org(key, org)


class Org(object):
    """
    Logical representation of an entry in `orgs.yaml`.

    Attributes:
        _data (Dict[str, Any]): The raw dictionary as parsed from the
            yaml file
        name (str): Org name
    """

    def __init__(self, name, data):
        """
        Init.

        Arguments:
            name (str): Org name
            data (Dict[str, Any]): The raw dictionary as parsed from
                the yaml file
        """
        self.name = name
        self._data = data

    @property
    def is_committer(self):
        """
        bool: Is org a committer?
        """
        return self._data.get('committer', False)

    @property
    def is_contractor(self):
        """
        bool: Is org a contractor?
        """
        return self._data.get('contractor', False)
