from datetime import datetime, timedelta, timezone

import cardio_common
import db


def test_to_local_iso_naive_is_utc():
    assert db.to_local_iso(datetime(2026, 6, 1, 18, 0)) == "2026-06-01 21:00:00"    # EEST +3
    assert db.to_local_iso(datetime(2026, 1, 15, 18, 0)) == "2026-01-15 20:00:00"   # EET +2


def test_to_local_iso_aware_converted():
    dt = datetime(2026, 6, 1, 20, 0, tzinfo=timezone(timedelta(hours=2)))
    assert db.to_local_iso(dt) == "2026-06-01 21:00:00"


def test_local_naive_iso_format_matches():
    assert db.local_naive_iso(datetime(2026, 6, 15, 15, 54)) == "2026-06-15 15:54:00"


def test_schema_has_cardio_cols(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)")}
    assert set(db.CARDIO_COLS) <= cols
    assert "distance_m" in cols


def test_ensure_columns_migrates_old_db(tmp_path):
    import sqlite3
    c = sqlite3.connect(tmp_path / "old.db")
    c.execute("CREATE TABLE workouts (id INTEGER PRIMARY KEY, timestamp TEXT, date TEXT)")
    db.ensure_columns(c)
    cols = {r[1] for r in c.execute("PRAGMA table_info(workouts)")}
    assert set(db.CARDIO_COLS) <= cols and "distance_m" in cols
    db.ensure_columns(c)   # idempotentne


def test_clean_cardio_name():
    assert cardio_common.clean_cardio_name("20260323_153243_Monday Evening Walk_2") == "Monday Evening Walk"
    assert cardio_common.clean_cardio_name("Monday Evening Walk") == "Monday Evening Walk"
    assert cardio_common.clean_cardio_name("12042026") == "12042026"
    assert cardio_common.clean_cardio_name("20260412_131331_12042026") == "12042026"


def test_sport_et_merged_map():
    assert cardio_common.sport_et("biking") == "rattasõit"
    assert cardio_common.sport_et("cycling") == "rattasõit"
    assert cardio_common.sport_et(None) == "kardio"
    assert cardio_common.sport_et("yoga") == "yoga"
