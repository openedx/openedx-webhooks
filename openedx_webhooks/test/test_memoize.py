"""Tests of the memoize decorators."""

from freezegun import freeze_time

from openedx_webhooks.utils import memoize, memoize_timed, clear_memoized_values


def test_memoize():
    vals = []
    @memoize
    def add_to_vals(x):
        vals.append(x)
        return x * 2

    with freeze_time("2020-05-14 09:00:00"):
        assert add_to_vals(10) == 20
        assert vals == [10]
        assert add_to_vals(10) == 20
        assert vals == [10]
        assert add_to_vals(15) == 30
        assert vals == [10, 15]

    with freeze_time("2020-05-14 20:00:00"):
        assert add_to_vals(10) == 20
        assert add_to_vals(15) == 30
        assert vals == [10, 15]

def test_memoize_timed():
    vals = []
    @memoize_timed(minutes=10)
    def add_to_vals_timed(x):
        vals.append(x)
        return x * 2

    with freeze_time("2020-05-14 09:00:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10]
        assert add_to_vals_timed(10) == 20
        assert vals == [10]

    with freeze_time("2020-05-14 09:05:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10]

    with freeze_time("2020-05-14 09:11:00"):
        assert add_to_vals_timed(10) == 20
        assert vals == [10, 10]

def test_clear_memoized_values():
    vals = []
    @memoize
    def add_to_vals(x):
        vals.append(x)
        return x * 2

    @memoize_timed(minutes=10)
    def add_to_vals_timed(x):
        vals.append(x)
        return x * 2

    assert add_to_vals(10) == 20
    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20]

    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20]

    clear_memoized_values()

    assert add_to_vals(15) == 30
    assert add_to_vals_timed(20) == 40
    assert vals == [10, 15, 20, 15, 20]
