from jira import JIRA

from openedx_webhooks.jira.tasks import _make_edx_action_choices

RESULT1 = {'key': True, 'value': 'Yes'}
RESULT2 = {'key': False, 'value': 'No'}


def test_make_edx_action_choices(mocker):
    jira = mocker.Mock(spec_set=JIRA)
    mocker.patch(
        'openedx_webhooks.jira.tasks.find_allowed_values',
        return_value=[RESULT1, RESULT2]
    )
    expected = {True: RESULT1, False: RESULT2}
    choices = _make_edx_action_choices(jira)
    assert expected == choices
