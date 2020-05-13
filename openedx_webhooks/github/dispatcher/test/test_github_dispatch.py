import pytest

from openedx_webhooks.github.dispatcher import dispatch


class BaseDummyAction:
    def run(self, event_type, event):
        pass


class DummyAction1(BaseDummyAction):
    EVENT_TYPES = ('event_type',)


class DummyAction2(BaseDummyAction):
    EVENT_TYPES = ('event_type', 'type2')


class DummyAction3(BaseDummyAction):
    EVENT_TYPES = ('type2',)


@pytest.fixture(autouse=True)
def patch_event_type(mocker):
    mocker.patch(
        (
            'openedx_webhooks.github.dispatcher.GithubWebHookRequestHeader'
            '.event_type'
        ),
        new_callable=mocker.PropertyMock,
        return_value='event_type'
    )


class TestDispatch:
    def test_match_event_type(self, mocker):
        actions = [DummyAction1(), DummyAction2()]
        for a in actions:
            mocker.spy(a, 'run')

        dispatch('header', 'event', actions)

        for a in actions:
            a.run.assert_called_once_with('event_type', 'event')

    def test_no_match_event_type(self, mocker):
        actions = [DummyAction3()]
        for a in actions:
            mocker.spy(a, 'run')

        dispatch('header', 'event', actions)

        for a in actions:
            assert a.run.call_count == 0
