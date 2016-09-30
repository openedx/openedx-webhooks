from openedx_webhooks.tasks.example import add


def test_add():
    assert add(5, 6) == 11
