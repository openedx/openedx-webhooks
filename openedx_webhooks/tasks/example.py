"""
Example Celery task, can be used for testing the Celery infrastructure
at Heroku.

Example usage::

    from openedx_webhooks.tasks.example import add
    add.delay(1, 2)
"""

from openedx_webhooks import celery
from openedx_webhooks.tasks.utils import log_info


@celery.task(name='example.add', bind=True)
def add(self, num1, num2):
    """
    Example Celery task.

    Args:
        num1 (int): First number
        num2 (int): Second number

    Returns:
        int: Sum
    """
    result = num1 + num2
    msg = "Results for `{}`: {}".format(self.name, result)
    log_info(self.request, msg)
    return result
