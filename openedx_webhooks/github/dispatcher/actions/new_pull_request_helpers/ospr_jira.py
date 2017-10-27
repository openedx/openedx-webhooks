# -*- coding: utf-8 -*-
from __future__ import (
    absolute_import, division, print_function, unicode_literals
)

from .....lib.jira.decorators import inject_jira


@inject_jira
def create_ospr(jira, event, workflow_stage='Needs Triage'):
    # TODO: implement
    pass
