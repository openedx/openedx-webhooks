# -*- coding: utf-8 -*-
"""
edx/repo-tools-data related domain models.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import date

import arrow

from ..exceptions import NotFoundError


class People(object):
    """
    Logical representation of `people.yaml`.

    Attributes:
        data (Dict[str, Any]): The raw dictionary as parsed from the
            yaml file
    """

    def __init__(self, data):
        """
        Init.

        Arguments:
            data (Dict[str, Any]): The raw dictionary as parsed from
                the yaml file
        """
        self.data = data

    def get(self, key):
        """
        Get a specific person by `people.yaml` key.

        Arguments:
            key (str)

        Returns:
            openedx_webhooks.lib.edx_repo_tools_data.models.Person

        Raises:
            openedx_webhooks.lib.exceptions.NotFoundError: If key cannot
                be found
        """
        person = self.data.get(key)

        if not person:
            raise NotFoundError("{} could not be found".format(key))

        return Person(key, person)


class Person(object):
    """
    Logical representation of an entry in `people.yaml`.

    Attributes:
        login (str): GitHub login
        data (Dict[str, Any]): The raw dictionary as parsed from the
            yaml file
    """

    # TODO: Test
    def __init__(self, login, data):
        """
        Init.

        Arguments:
            login (str): GitHub login
            data (Dict[str, Any]): The raw dictionary as parsed from
                the yaml file
        """
        self.login = login
        self.data = data

    @property
    def agreement(self):
        """
        Optional[str]: User's agreement.
        """
        data = self.data.get('agreement')
        if data == 'none':
            data = None
        return data

    @property
    def agreement_expired(self):
        """
        bool: Has user's agreement expired.
        """
        expired = False
        if self.agreement_expires_on:
            expired = self.agreement_expires_on < date.today()
        return expired

    @property
    def before(self):
        """
        Optional[Dict[str, Dict]]: User's `before` data.
        """
        return self.data.get('before')

    @property
    def agreement_expires_on(self):
        """
        Optional[datetime.date]: User's `before` data.
        """
        expires_on = self.data.get('expires_on')
        if expires_on:
            return expires_on

        if not self.agreement:
            # TODO: Is there a better way to handle this edge case?
            #       Is it even possible to have no agreement and no
            #       expiration data at all?
            yesterday = arrow.now().replace(days=-1).date()
            expires_on = yesterday

        if not self.agreement and self.before:
            expires_on = max(self.before.keys())

        return expires_on

    @property
    def institution(self):
        """
        Optional[str]: User's institution.
        """
        data = self.data.get('institution')
        return self.agreement and data

    @property
    def is_edx_user(self):
        """
        bool: Is user associated with edX.
        """
        if (
                not self.agreement
                or self.agreement_expired
                or not self.institution
        ):
            return False
        is_edx = self.institution.lower() == 'edx'
        return is_edx
