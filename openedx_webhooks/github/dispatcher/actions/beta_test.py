from ....lib.edx_repo_tools_data.utils import get_people
from ....lib.exceptions import NotFoundError

INSTITUTIONS = (
    'ExtensionEngine',
    'OpenCraft',
    'QRF',
    'Stanford',
    'TELTEK',
)


def _belongs_to_beta_group(person):
    for institution in INSTITUTIONS:
        if person.is_associated_with_institution(institution):
            return True
    else:
        return False


def is_tester(login):
    people = get_people()
    try:
        person = people.get(login)
        return _belongs_to_beta_group(person)
    except NotFoundError:
        return False
