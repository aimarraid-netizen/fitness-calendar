from datetime import datetime

import pytest

import validation as val


@pytest.mark.parametrize("fn,value,ok", [
    (val.valid_reps, None, True),
    (val.valid_reps, 1, True),
    (val.valid_reps, 200, True),
    (val.valid_reps, 0, False),
    (val.valid_reps, -10, False),
    (val.valid_reps, 201, False),
    (val.valid_weight, None, True),
    (val.valid_weight, 0.5, True),
    (val.valid_weight, 400.0, True),
    (val.valid_weight, 0, False),
    (val.valid_weight, 9999, False),
    (val.valid_duration_min, 60, True),
    (val.valid_duration_min, 1441, False),
    (val.valid_hr, 113, True),
    (val.valid_hr, 24, False),
    (val.valid_hr, 251, False),
    (val.valid_kcal, 0, True),
    (val.valid_kcal, 10001, False),
    (val.valid_distance_m, 5000.0, True),
    (val.valid_distance_m, 600_000.0, False),
])
def test_bounds(fn, value, ok):
    assert fn(value) is ok


def test_valid_date():
    now = datetime(2026, 6, 10)
    assert val.valid_date(datetime(2026, 6, 8), now)
    assert val.valid_date(datetime(2026, 6, 11), now)          # +1 päev lubatud
    assert not val.valid_date(datetime(2026, 6, 20), now)      # kaugel tulevikus
    assert not val.valid_date(datetime(2019, 1, 1), now)       # enne DATE_MIN
    assert not val.valid_date(None, now)
