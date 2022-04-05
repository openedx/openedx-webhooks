import arrow

from openedx_webhooks.lib.edx_repo_tools_data.models import Person


class TestAgreement:
    def test_agreement(self, active_person):
        assert active_person.agreement == 'individual'

    def test_no_agreement(self, before_expired_person):
        assert before_expired_person.agreement is None


class TestAgreementExpired:
    def test_not_expired(self, active_person):
        assert active_person.has_agreement_expired is False

    def test_expired(self, expired_person):
        assert expired_person.has_agreement_expired is True

    def test_before_expired(self, before_expired_person):
        assert before_expired_person.has_agreement_expired is True


class TestAgreementExpiresOn:
    def test_not_expired(self, active_person):
        assert active_person.agreement_expires_on is None

    def test_expired(self, expired_person):
        assert (
            expired_person.agreement_expires_on ==
            arrow.get('2012-10-01').date()
        )

    def test_before_expired(self, before_expired_person):
        assert (
            before_expired_person.agreement_expires_on ==
            arrow.get('2016-08-08').date()
        )

    def test_no_agreement(self):
        p = Person('', {'agreement': 'none'})
        yesterday = arrow.now().shift(days=-1).date()
        assert p.agreement_expires_on == yesterday


class TestBefore:
    def test_before(self, before_expired_person, before):
        assert before_expired_person._before == before

    def test_no_before(self, active_person):
        assert active_person._before is None


class TestInstitution:
    def test_institution(self, active_edx_person):
        assert active_edx_person.institution == 'edX'

    def test_no_institution(self, active_person):
        assert active_person.institution is None


class TestIsEdxUser:
    def test_true(self, active_edx_person):
        assert active_edx_person.is_edx_user is True

    def test_expired(self, before_expired_person, expired_person):
        assert before_expired_person.is_edx_user is False
        assert expired_person.is_edx_user is False

    def test_individual(self, active_person):
        assert active_person.is_edx_user is False

    def test_another_institution(self, active_non_edx_person):
        assert active_non_edx_person.is_edx_user is False


class TestIsRobot:
    def test_true(self, robot):
        assert robot.is_robot is True

    def test_false(self, active_person):
        assert active_person.is_robot is False
