import sys
from raven.processors import Processor
from requests.exceptions import HTTPError


class RequestsURLProcessor(Processor):
    """
    A processor for Raven, to add information to stack traces that involve
    a Requests HTTPError exception. This processor will make sure that the
    URL of the offending exception is reported in the "extra" data.
    """
    def process(self, data, **kwargs):
        # get the last exception thrown by the system
        exc = sys.exc_info()[1]
        # only process it if it's a Requests HTTPError
        if isinstance(exc, HTTPError):
            # HTTPError objects have a reference to the original request object,
            # and we can use that to get the URL. (They also have a reference
            # to the response object for that request, in case that's helpful
            # in the future.)
            url = exc.request.url
            # add this to the extra data, but only if no one else is using
            # this key in the dictionary
            data['extra'].setdefault('request_url', url)

        # return the updated data dictionary
        return data
