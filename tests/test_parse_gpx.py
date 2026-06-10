from datetime import datetime

import parse_gpx
from conftest import FIXTURES

SAMPLE = FIXTURES / "sample.gpx"


def test_distance_time_hr():
    data = parse_gpx.parse_gpx(SAMPLE)
    assert data is not None
    assert data["timestamp"] == datetime(2026, 6, 1, 18, 0)
    assert data["duration_sec"] == 600.0
    assert 500 < data["distance_m"] < 1000   # 6 punkti ~125m vahedega
    assert data["avg_hr"] == round((135 + 136 + 138 + 140 + 137 + 139) / 6)
    assert data["ascent_m"] == 8             # 2+3+1+2 tõusu
    assert data["sport"] == "walking"
    assert data["track_name"] == "Õhtune kõnd"


def test_z2_minutes_computed():
    data = parse_gpx.parse_gpx(SAMPLE)
    # kõik sämplid 135-140 bpm = z2 (62/179 puhul z2 = 132..143)
    assert data["zone_min"]["z2"] == 10.0


def test_missing_trk_returns_none(tmp_path):
    p = tmp_path / "empty.gpx"
    p.write_text('<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"></gpx>')
    assert parse_gpx.parse_gpx(p) is None


def test_missing_times_returns_none(tmp_path):
    p = tmp_path / "notime.gpx"
    p.write_text(
        '<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1">'
        '<trk><name>x</name><trkseg><trkpt lat="59.0" lon="24.0"></trkpt>'
        "</trkseg></trk></gpx>"
    )
    assert parse_gpx.parse_gpx(p) is None


def test_insert_dedup_and_z2_persisted(conn):
    data = parse_gpx.parse_gpx(SAMPLE)
    added, wid = parse_gpx.insert_workout(conn, SAMPLE, data)
    assert added
    again, wid2 = parse_gpx.insert_workout(conn, SAMPLE, data)
    assert not again and wid2 == wid
    row = conn.execute("SELECT z2_min, workout_type FROM workouts WHERE id=?", (wid,)).fetchone()
    assert row["z2_min"] == 10.0
    assert row["workout_type"] == "kõndimine"
