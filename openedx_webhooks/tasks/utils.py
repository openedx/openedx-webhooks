"""
Utility functions in support of Celery tasks

More information about referenced class objects below:

-  `celery.Task.request`_
-  `requests.PreparedRequest`_
-  `requests.Response`_

.. _celery.Task.request: http://docs.celeryproject.org/en/latest/userguide/tasks.html#context
.. _requests.PreparedRequest: http://docs.python-requests.org/en/master/api/#requests.PreparedRequest
.. _requests.Response: http://docs.python-requests.org/en/master/api/#requests.Response
"""

from openedx_webhooks.tasks import logger


def _log(log_fn, task_request, message):
    """
    Logs a message using the supplied logging function.

    Arguments:
        log_fn: logging.Logger instance method to render log message
        task_request (celery.Task.request): instance of request used to
            call this function
        message (str): Log message
    """
    log_fn("{}: {}".format(task_request.id, message))


def log_debug(task_request, message):
    """
    Logs a message using Celery's app logger at the DEBUG level.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        message (str): Log message
    """
    _log(logger.debug, task_request, message)


def log_info(task_request, message):
    """
    Logs a message using Celery's app logger at the INFO level.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        message (str): Log message
    """
    _log(logger.info, task_request, message)


def log_error(task_request, message):
    """
    Logs a message using Celery's app logger at the ERROR level.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        message (str): Log message
    """
    _log(logger.error, task_request, message)


def log_request(task_request, request):
    """
    Logs HTTP request message using Celery's app logger.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        request (requests.PreparedRequest): the HTTP request
    """
    msg = "{0.method} {0.url}: {0.body}".format(request)
    log_info(task_request, msg)


def log_response(task_request, response):
    """
    Logs HTTP response message using Celery's app logger.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        response (requests.Response): the HTTP response
    """
    msg = "{0.status_code} {0.reason} for {0.url}: {0.content}".format(response)
    log_info(task_request, msg)


def log_request_response(task_request, response):
    """
    Logs HTTP request and response messages using Celery's app logger.

    Arguments:
        task_request (celery.Task.request): instance of request used to
            call this function
        response (requests.Response): the HTTP response
    """
    log_request(task_request, response.request)
    log_response(task_request, response)
