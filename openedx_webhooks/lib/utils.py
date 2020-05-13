"""
Shared lib utilities.
"""


def dependency_exists(klass, *args, **kwargs):
    exist_in_args = bool([a for a in args if isinstance(a, klass)])
    exist_in_kwargs = bool(
        [a for a in kwargs.values() if isinstance(a, klass)]
    )
    return exist_in_args or exist_in_kwargs
