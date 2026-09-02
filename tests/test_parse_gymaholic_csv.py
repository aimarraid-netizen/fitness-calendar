from datetime import datetime

import parse_gymaholic_csv as pg
import pytest
from conftest import FIXTURES

from validation import ValidationError

SAMPLE = FIXTURES / "sample_single_workout.csv"
EDGE = FIXTURES / "edge_cases.csv"
INVALID = FIXTURES / "invalid.csv"


def test_meta_parsed():
    parsed = pg.parse_csv(SAMPLE)
    meta = parsed["meta"]
    assert meta["name"] == "3. Selg & biitseps"
    assert meta["duration_min"] == 58
    assert meta["kcal"] == 380
    assert meta["avg_hr"] == 113
    assert meta["date"].month == 5 and meta["date"].day == 21


def test_sets_and_weights():
    parsed = pg.parse_csv(SAMPLE)
    by_name = {e["name"]: e for e in parsed["exercises"]}
    row = by_name["Bent Over Barbell Row"]
    assert len(row["sets"]) == 3
    assert all(s["weight"] == 70.0 and s["reps"] == 6 for s in row["sets"])
    hammer = by_name["Seated Hammer Curls"]
    assert hammer["sets"][0]["weight"] == 17.5


def test_rep_range():
    assert pg._rep_range("6-10 reps") == (6, 10)
    assert pg._rep_range("20 reps") == (20, 20)
    assert pg._rep_range("Pulss 90-110") == (None, None)
    assert pg._rep_range(None) == (None, None)


def test_rep_range_saved_to_exercises(loaded_conn):
    row = loaded_conn.execute(
        "SELECT target_reps_min, target_reps_max FROM exercises WHERE name=?",
        ("Bent Over Barbell Row",),
    ).fetchone()
    assert (row["target_reps_min"], row["target_reps_max"]) == (6, 10)


def test_null_weight_not_zero(loaded_conn):
    rows = loaded_conn.execute(
        "SELECT weight_kg FROM sets WHERE exercise_name=?",
        ("Rowing With Rowing Ergometer",),
    ).fetchall()
    assert rows
    assert all(r["weight_kg"] is None for r in rows)


def test_year_inference_normal():
    dt = pg._parse_date("May 21., 15:55", now=datetime(2026, 6, 10))
    assert dt == datetime(2026, 5, 21, 15, 55)


def test_year_boundary_dec_imported_january():
    dt = pg._parse_date("Dec 31., 23:50", now=datetime(2026, 1, 1, 10, 0))
    assert dt == datetime(2025, 12, 31, 23, 50)


def test_year_inference_near_future_kept():
    # eksport järgmisel päeval pärast keskööd: trenn "homme" suhtes ei hüppa aastat
    dt = pg._parse_date("Jun 10., 23:30", now=datetime(2026, 6, 10, 8, 0))
    assert dt == datetime(2026, 6, 10, 23, 30)


def test_unparseable_date_returns_none():
    assert pg._parse_date("garbage") is None
    assert pg._parse_date("Xyz 99., 25:99") is None


def test_save_idempotent_reimport(conn):
    parsed = pg.parse_csv(SAMPLE)
    wid1, _, _ = pg.save_to_db(parsed, conn)
    wid2, _, _ = pg.save_to_db(parsed, conn)
    assert wid1 == wid2
    assert conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0] == 1
    n_sets = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert n_sets == sum(len(e["sets"]) for e in parsed["exercises"])


def test_edge_cases_imported(conn):
    parsed = pg.parse_csv(EDGE)
    pg.save_to_db(parsed, conn)
    # üksik-väärtusega rep-range
    row = conn.execute(
        "SELECT target_reps_min, target_reps_max FROM exercises WHERE name='Plank'"
    ).fetchone()
    assert (row["target_reps_min"], row["target_reps_max"]) == (20, 20)
    # NULL-kaal Face Pull
    fp = conn.execute(
        "SELECT weight_kg FROM sets WHERE exercise_name='Face Pull'"
    ).fetchall()
    assert len(fp) == 2 and all(r["weight_kg"] is None for r in fp)
    # katkine set-rida ei tekita seeriat
    bc = conn.execute(
        "SELECT COUNT(*) FROM sets WHERE exercise_name='Barbell Curl'"
    ).fetchone()[0]
    assert bc == 2


def test_invalid_sets_skipped(conn, capsys):
    parsed = pg.parse_csv(INVALID)
    parsed["meta"]["date"] = datetime(2026, 6, 1, 10, 0)  # kuupäev puudub failist
    pg.save_to_db(parsed, conn)
    n = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert n == 0  # 9999 kg ja 0 kordust mõlemad vahele jäetud


def test_missing_date_raises(conn):
    parsed = pg.parse_csv(INVALID)
    assert parsed["meta"]["date"] is None
    with pytest.raises(ValidationError):
        pg.save_to_db(parsed, conn)


def test_no_exercises_raises(conn):
    parsed = {"meta": {"name": "X", "date": datetime(2026, 6, 1), "duration_min": 30,
                       "kcal": None, "avg_hr": None}, "exercises": []}
    with pytest.raises(ValidationError):
        pg.save_to_db(parsed, conn)


# ---------------------------------------------------------------------------
# 2026-09 parandused: N;-märkused, koma, 0 kg, TIME-veerg, rollback
# ---------------------------------------------------------------------------

HEADER = (
    "\n;-----------------\n;{name}\n;-----------------\n"
    ";Date;{date}\n;Duration;1h:00m\n;KCAL;400\n;Heart rate;115 bpm\n\n"
)


def _csv(tmp_path, body, name="Trenn T", date="Jun 15., 15:54"):
    p = tmp_path / "t.csv"
    p.write_text(HEADER.format(name=name, date=date) + body, encoding="utf-8")
    return p


def test_rep_range_note_is_not_range():
    # tootmisviga: "N;1 kaaluvihk = 2,5kg" loeti rep-vahemikuks (1,1)
    assert pg._rep_range("1 kaaluvihk = 2,5kg") == (None, None)
    assert pg._rep_range("6-10 reps (kerge)") == (6, 10)
    assert pg._rep_range("12 REPS") == (12, 12)


def test_second_n_line_becomes_note(conn, tmp_path):
    body = ("#;Triceps Pushdown with Rope;REPS;TIME;REST\n"
            "N;10-15 reps\nN;1 kaaluvihk = 2,5kg\n"
            "1;;22.5 kg x 15;;0:00\n2;;22.5 kg x 15;;0:00\n")
    pg.save_to_db(pg.parse_csv(_csv(tmp_path, body)), conn)
    row = conn.execute(
        "SELECT target_reps_min, target_reps_max FROM exercises WHERE name=?",
        ("Triceps Pushdown with Rope",)).fetchone()
    assert (row[0], row[1]) == (10, 15)
    notes = [r[0] for r in conn.execute(
        "SELECT note FROM sets WHERE exercise_name=? ORDER BY set_number",
        ("Triceps Pushdown with Rope",))]
    assert notes == ["1 kaaluvihk = 2,5kg"] * 2


def test_note_before_range_still_finds_range(conn, tmp_path):
    body = ("#;Barbell Curl;REPS;TIME;REST\nN;kerge päev\nN;8-12 reps\n"
            "1;;35 kg x 8;;0:00\n")
    pg.save_to_db(pg.parse_csv(_csv(tmp_path, body)), conn)
    row = conn.execute(
        "SELECT target_reps_min, target_reps_max FROM exercises WHERE name='Barbell Curl'"
    ).fetchone()
    assert (row[0], row[1]) == (8, 12)
    assert conn.execute("SELECT note FROM sets").fetchone()[0] == "kerge päev"


def test_comma_decimal_weight(tmp_path):
    body = ("#;Shoulder Press;REPS;TIME;REST\nN;8-12 reps\n"
            "1;;12,5 kg x 15;;0:00\n2;;17.5 kg x 10;;0:00\n")
    sets = pg.parse_csv(_csv(tmp_path, body))["exercises"][0]["sets"]
    assert sets[0]["weight"] == 12.5 and sets[0]["reps"] == 15
    assert sets[1]["weight"] == 17.5


def test_zero_weight_becomes_null_keeps_reps(conn, tmp_path):
    body = "#;Triceps Dips;REPS;TIME;REST\nN;6-10 reps\n1;;0 kg x 12;;0:00\n"
    pg.save_to_db(pg.parse_csv(_csv(tmp_path, body)), conn)
    row = conn.execute("SELECT reps, weight_kg FROM sets").fetchone()
    assert row["reps"] == 12 and row["weight_kg"] is None


def test_parse_time_cell():
    assert pg._parse_time_cell("5:00") == 300
    assert pg._parse_time_cell("1:05:00") == 3900
    assert pg._parse_time_cell("1:30") == 90
    assert pg._parse_time_cell("0:00") is None
    assert pg._parse_time_cell("") is None
    assert pg._parse_time_cell(None) is None
    assert pg._parse_time_cell("abc") is None


def test_time_column_saved_as_duration(loaded_conn):
    row = loaded_conn.execute(
        "SELECT duration_sec, note, reps, weight_kg FROM sets WHERE exercise_name=?",
        ("Rowing With Rowing Ergometer",)).fetchone()
    assert row["duration_sec"] == 300
    assert row["note"] == "Pulss 90-110"
    assert row["reps"] is None and row["weight_kg"] is None
    bor = loaded_conn.execute(
        "SELECT duration_sec, note FROM sets WHERE exercise_name='Bent Over Barbell Row'"
    ).fetchone()
    assert bor["duration_sec"] is None and bor["note"] is None


def test_edge_plank_duration_from_time(conn):
    pg.save_to_db(pg.parse_csv(EDGE), conn)
    row = conn.execute(
        "SELECT duration_sec, reps FROM sets WHERE exercise_name='Plank'").fetchone()
    assert row["duration_sec"] == 90 and row["reps"] is None


def test_save_rolls_back_on_error(loaded_conn, monkeypatch):
    # reimport: INSERT OR IGNORE -> DELETE FROM sets -> viga -> vanad seeriad peavad alles jääma
    before = loaded_conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    assert before > 0

    def boom(name):
        raise RuntimeError("simuleeritud viga pärast DELETE-i")

    monkeypatch.setattr(pg.cfg, "equipment_for", boom)
    with pytest.raises(RuntimeError):
        pg.save_to_db(pg.parse_csv(SAMPLE), loaded_conn)
    assert loaded_conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0] == before
    assert not loaded_conn.in_transaction
