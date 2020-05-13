"""
Generic JIRA domain models.
"""

from ..exceptions import NotFoundError


class JiraFields(object):
    """
    Represent a collection of JIRA fields.
    """

    def __init__(self, data):
        """
        Init.

        Arguments:
            _data (List[Dict[str, Any]]): Raw data of the fields
        """
        self._data = data

    def get_by_name(self, name):
        """
        Find a field by name.

        Arguments:
            name (str)

        Returns:
            openedx_webhooks.lib.jira.models.JiraField

        Raises:
            openedx_webhooks.lib.exceptions.NotFoundError
        """
        # TODO: It's possible to have two fields by the same name in JIRA,
        #       we're only returning the first one found!
        results = [f for f in self._data if f['name'] == name]

        if not results:
            raise NotFoundError("{} could not be found".format(name))

        return JiraField(results[0])


class JiraField(object):
    """
    Represent a JIRA field.

    Attributes:
        All attributes are delegated to ``self._data``. If a key exists,
        the the attribute is returned.
    """

    def __init__(self, data):
        """
        Init.

        Arguments:
            data (Dict[str, Any]): Raw data of the field.
        """
        self._data = data

    def __getattr__(self, attr):
        """
        Return attribute based on self._data[key].

        Arguments:
            attr (str)

        Returns:
            Any: self._data[key]

        Raises:
            AttributeError
        """
        try:
            return self._data[attr]
        except KeyError:
            msg = "'{}' object has no attribute '{}'".format(
                self.__class__.__name__, attr
            )
            raise AttributeError(msg)
