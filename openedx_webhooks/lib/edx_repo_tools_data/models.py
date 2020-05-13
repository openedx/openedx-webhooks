"""
edx/repo-tools-data related domain models.
"""

from datetime import date

import arrow

from ..exceptions import NotFoundError


class People(object):
    """
    Logical representation of `people.yaml`.

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
            yield Person(k, v)

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
        person = self._data.get(key)

        if not person:
            raise NotFoundError("{} could not be found".format(key))

        return Person(key, person)


class Person(object):
    """
    Logical representation of an entry in `people.yaml`.

    Attributes:
        _data (Dict[str, Any]): The raw dictionary as parsed from the
            yaml file
        login (str): GitHub login
    """

    def __init__(self, login, data):
        """
        Init.

        Arguments:
            login (str): GitHub login
            data (Dict[str, Any]): The raw dictionary as parsed from
                the yaml file
        """
        self.login = login
        self._data = data

    def is_associated_with_institution(self, institution):
        """
        Check whether person is associated with institution.

        Arguments:
            institution (str)

        Returns:
            bool
        """
        if (
                not self.agreement
                or self.has_agreement_expired
                or not self.institution
        ):
            return False
        result = self.institution.lower() == institution.lower()
        return result

    @property
    def _before(self):
        """
        Optional[Dict[str, Dict]]: User's `before` data.
        """
        return self._data.get('before')

    @property
    def agreement(self):
        """
        Optional[str]: User's agreement.
        """
        data = self._data.get('agreement')
        if data == 'none':
            data = None
        return data

    @property
    def has_agreement_expired(self):
        """
        bool: Has user's agreement expired.
        """
        expired = False
        if self.agreement_expires_on:
            expired = self.agreement_expires_on < date.today()
        return expired

    @property
    def agreement_expires_on(self):
        """
        Optional[datetime.date]: When did the user's agreement expire?
        """
        expires_on = self._data.get('expires_on')
        if expires_on:
            return expires_on

        if not self.agreement:
            # TODO: Is there a better way to handle this edge case?
            #       Is it even possible to have no agreement and no
            #       expiration data at all?
            yesterday = arrow.now().shift(days=-1).date()
            expires_on = yesterday

        if not self.agreement and self._before:
            expires_on = max(self._before.keys())

        return expires_on

    @property
    def institution(self):
        """
        Optional[str]: User's institution.
        """
        data = self._data.get('institution')
        return self.agreement and data

    @property
    def is_edx_user(self):
        """
        bool: Is user associated with edX.
        """
        return self.is_associated_with_institution('edx')

    @property
    def is_robot(self):
        """
        bool: Is the user a robot?
        """
        return self._data.get('is_robot', False)
