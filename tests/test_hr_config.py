import importlib

import hr_config


def test_zone_boundaries():
    zones = hr_config.hr_zones(resting=60, max_hr=180)  # hrr=120
    assert zones["z1"] == (120, 132)
    assert zones["z2"] == (132, 144)
    assert zones["z5"] == (168, 180)


def test_zone_for():
    zones = hr_config.hr_zones(resting=60, max_hr=180)
    assert hr_config.zone_for(100, zones) == "z1"   # alla z1 -> z1
    assert hr_config.zone_for(135, zones) == "z2"
    assert hr_config.zone_for(190, zones) == "z5"   # üle z5 -> z5


def test_zone_minutes_sums_to_duration():
    mins = hr_config.zone_minutes([130, 140, 150, 160, 170] * 20, 1800)
    assert abs(sum(mins.values()) - 30.0) < 0.5


def test_zone_minutes_empty():
    assert sum(hr_config.zone_minutes([], 600).values()) == 0.0
    assert sum(hr_config.zone_minutes([130], None).values()) == 0.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("RESTING_HR", "50")
    monkeypatch.setenv("MAX_HR", "190")
    try:
        importlib.reload(hr_config)
        assert hr_config.RESTING_HR == 50
        assert hr_config.MAX_HR == 190
    finally:
        monkeypatch.undo()
        importlib.reload(hr_config)
