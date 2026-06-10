from datetime import datetime
from pathlib import Path

import parse_fit


class FakeField:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class FakeMsg:
    def __init__(self, fields):
        self._fields = fields

    def __iter__(self):
        return iter(self._fields)


def make_fake_fitfile(session_fields, hr_samples=()):
    class FakeFitFile:
        def __init__(self, path):
            pass

        def get_messages(self, kind):
            if kind == "session":
                return [FakeMsg([FakeField(n, v) for n, v in session_fields])]
            return [FakeMsg([FakeField("heart_rate", hr)]) for hr in hr_samples]
    return FakeFitFile


SESSION = [
    ("start_time", datetime(2026, 6, 1, 18, 0)),
    ("sport", "walking"),
    ("total_elapsed_time", 1800.0),
    ("total_distance", 3000.0),
    ("avg_heart_rate", 120),
    ("total_calories", 200),
]


def test_session_fields_mapped(monkeypatch):
    monkeypatch.setattr(parse_fit, "FitFile", make_fake_fitfile(SESSION, [135] * 50))
    data = parse_fit.parse_fit(Path("fake.fit"))
    assert data["timestamp"] == datetime(2026, 6, 1, 18, 0)
    assert data["sport"] == "walking"
    assert data["duration_sec"] == 1800.0
    assert data["distance_m"] == 3000.0
    assert data["avg_hr"] == 120
    assert data["kcal"] == 200


def test_zone_minutes_sum_to_duration(monkeypatch):
    monkeypatch.setattr(parse_fit, "FitFile",
                        make_fake_fitfile(SESSION, [130, 140, 150, 160] * 25))
    data = parse_fit.parse_fit(Path("fake.fit"))
    assert abs(sum(data["zone_min"].values()) - 30.0) < 0.5


def test_missing_timestamp_fails(monkeypatch):
    no_ts = [f for f in SESSION if f[0] != "start_time"]
    monkeypatch.setattr(parse_fit, "FitFile", make_fake_fitfile(no_ts))
    assert parse_fit.parse_fit(Path("fake.fit")) is None


def test_out_of_bounds_values_nulled(monkeypatch, capsys):
    bad = [("start_time", datetime(2026, 6, 1)), ("sport", "walking"),
           ("total_elapsed_time", 1800.0), ("avg_heart_rate", 999),
           ("total_distance", 9_999_999.0)]
    monkeypatch.setattr(parse_fit, "FitFile", make_fake_fitfile(bad))
    data = parse_fit.parse_fit(Path("fake.fit"))
    assert data["avg_hr"] is None
    assert data["distance_m"] is None


def test_insert_and_dedup(conn, monkeypatch):
    monkeypatch.setattr(parse_fit, "FitFile", make_fake_fitfile(SESSION, [135] * 50))
    data = parse_fit.parse_fit(Path("fake.fit"))
    added, wid = parse_fit.insert_workout(conn, Path("fake.fit"), data)
    assert added and wid
    again, wid2 = parse_fit.insert_workout(conn, Path("fake.fit"), data)
    assert not again and wid2 == wid
    row = conn.execute("SELECT z2_min, source FROM workouts WHERE id=?", (wid,)).fetchone()
    assert row["source"] == "fit"
    assert row["z2_min"] is not None and row["z2_min"] > 0  # 135 bpm on z2-s (62/179)
