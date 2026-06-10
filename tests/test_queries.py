from datetime import datetime

import parse_gymaholic_csv as pg

import queries as q


def _workout(name, date, exercises):
    """Abifunktsioon: ehita save_to_db sisend."""
    return {
        "meta": {"name": name, "date": date, "duration_min": 60,
                 "kcal": None, "avg_hr": None},
        "exercises": exercises,
    }


def _ex(name, sets, rep_range=None):
    return {"name": name, "rep_range": rep_range,
            "sets": [{"reps": r, "weight": w} for w, r in sets]}


def test_exercise_sessions_work_weight_mode(loaded_conn):
    # teine sessioon: 72.5 kg x2 seeriat + 70 kg x1 -> work_weight = mode = 72.5
    pg.save_to_db(_workout("3. Selg & biitseps", datetime(2026, 5, 28, 16, 0), [
        _ex("Bent Over Barbell Row", [(72.5, 6), (72.5, 6), (70.0, 8)]),
    ]), loaded_conn)
    sess = q.exercise_sessions(loaded_conn, "Bent Over Barbell Row")
    assert len(sess) == 2
    assert sess[0]["work_weight"] == 70.0
    assert sess[1]["work_weight"] == 72.5
    assert sess[1]["top_weight"] == 72.5
    assert sess[1]["top_reps"] == 8


def test_compute_prs_weighted(loaded_conn):
    prs = q.compute_prs(loaded_conn)
    assert prs["Bent Over Barbell Row"] == {"weight": 70.0, "reps": 6, "date": "2026-05-21"}
    # cardio harjutusel PR-i ei arvutata
    assert "Rowing With Rowing Ergometer" not in prs


def test_compute_prs_null_weight(conn):
    pg.save_to_db(_workout("Trenn X", datetime(2026, 5, 21, 10, 0), [
        _ex("Triceps Dips", [(None, 10), (None, 12)]),
    ]), conn)
    prs = q.compute_prs(conn)
    assert prs["Triceps Dips"] == {"weight": None, "reps": 12, "date": "2026-05-21"}


def test_weekly_volume_iso_weeks(loaded_conn):
    wv = q.weekly_volume(loaded_conn)
    assert "2026-W21" in wv          # 21. mai 2026 = ISO nädal 21
    assert wv["2026-W21"]["selg"] > 0
