# -*- coding: utf-8 -*-
"""
Shared lib utilities.
"""

from __future__ import (
    absolute_import, division, print_function, unicode_literals
)


def dependency_exists(klass, *args, **kwargs):
    exist_in_args = bool([a for a in args if isinstance(a, klass)])
    exist_in_kwargs = bool(
        [a for a in kwargs.values() if isinstance(a, klass)]
    )
    return exist_in_args or exist_in_kwargs
