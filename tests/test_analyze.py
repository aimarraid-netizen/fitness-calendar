import analyze


def _sess(date, equipment="barbell", work_weight=None, top_reps=None,
          top_duration=None):
    return {"date": date, "equipment": equipment, "work_weight": work_weight,
            "top_weight": work_weight, "top_reps": top_reps,
            "top_duration": top_duration}


def test_double_progression_is_areneb():
    # kaal tõusis, kordused kukkusid -> areng, MITTE regress
    sessions = [
        _sess("2026-06-01", work_weight=70.0, top_reps=8),
        _sess("2026-06-08", work_weight=72.5, top_reps=6),
    ]
    assert analyze.exercise_status(sessions) == "areneb"


def test_equipment_switch_is_vahetus():
    sessions = [
        _sess("2026-06-01", equipment="trx", top_reps=15),
        _sess("2026-06-08", equipment="machine", work_weight=15.0, top_reps=20),
    ]
    assert analyze.exercise_status(sessions) == "vahetus"


def test_null_to_weight_is_vahetus():
    # NULL-kaal -> päris kaal sama varustusega = de facto vahetus
    sessions = [
        _sess("2026-06-01", equipment="machine", work_weight=None, top_reps=15),
        _sess("2026-06-08", equipment="machine", work_weight=15.0, top_reps=20),
    ]
    assert analyze.exercise_status(sessions) == "vahetus"


def test_plateau_is_seisab():
    sessions = [
        _sess("2026-05-25", work_weight=70.0, top_reps=8),
        _sess("2026-06-01", work_weight=70.0, top_reps=8),
        _sess("2026-06-08", work_weight=70.0, top_reps=8),
    ]
    assert analyze.exercise_status(sessions) == "seisab"


def test_weight_drop_is_regress():
    sessions = [
        _sess("2026-06-01", work_weight=72.5, top_reps=6),
        _sess("2026-06-08", work_weight=70.0, top_reps=6),
    ]
    assert analyze.exercise_status(sessions) == "regress"


def test_long_gap_is_uus():
    sessions = [
        _sess("2026-04-01", work_weight=70.0, top_reps=8),
        _sess("2026-06-08", work_weight=60.0, top_reps=8),
    ]
    assert analyze.exercise_status(sessions) == "uus"


def test_duration_based_progress():
    sessions = [
        _sess("2026-06-01", equipment="bodyweight", top_duration=60.0),
        _sess("2026-06-08", equipment="bodyweight", top_duration=90.0),
    ]
    assert analyze.exercise_status(sessions) == "areneb"


def test_single_session_is_uus():
    assert analyze.exercise_status([_sess("2026-06-08", work_weight=70.0)]) == "uus"


# ---------------------------------------------------------------------------
# 2026-09: trenni-põhine analüüs, PR-sel-hetkel, platoo, kalendrinädalad
# ---------------------------------------------------------------------------
from datetime import datetime  # noqa: E402

import parse_gymaholic_csv as pg  # noqa: E402


def _workout(name, date, exercises):
    return {"meta": {"name": name, "date": date, "duration_min": 60,
                     "kcal": None, "avg_hr": None}, "exercises": exercises}


def _ex(name, sets, rep_range=None):
    return {"name": name, "rep_range": rep_range,
            "sets": [{"reps": r, "weight": w} for w, r in sets]}


def _three_rows(conn):
    ids = []
    for d, w in ((datetime(2026, 5, 21, 16), 70.0), (datetime(2026, 5, 28, 16), 72.5),
                 (datetime(2026, 6, 4, 16), 72.5)):
        wid, _, _ = pg.save_to_db(_workout("B", d, [
            _ex("Bent Over Barbell Row", [(w, 6), (w, 6), (w, 6)]),
            _ex("Rowing With Rowing Ergometer", [(None, None)]),
        ]), conn)
        ids.append(wid)
    return ids


def test_workout_analysis_is_per_workout_not_latest(conn):
    w1, w2, w3 = _three_rows(conn)
    cache = analyze.build_session_cache(conn)
    a1 = analyze.workout_analysis(conn, w1, cache)["per_exercise"]["Bent Over Barbell Row"]
    a2 = analyze.workout_analysis(conn, w2, cache)["per_exercise"]["Bent Over Barbell Row"]
    a3 = analyze.workout_analysis(conn, w3, cache)["per_exercise"]["Bent Over Barbell Row"]
    assert a1 == {"status": "uus", "delta_kg": None, "delta_reps": None, "pr": False, "first": True}
    assert (a2["status"], a2["delta_kg"], a2["delta_reps"], a2["pr"], a2["first"]) == \
        ("areneb", 2.5, 0, True, False)
    # kolmas kord sama 72.5×6: pole PR (ei ületa), delta 0, mitte "areneb"
    assert a3["pr"] is False and a3["delta_kg"] == 0 and a3["status"] != "areneb"
    # kardio ei ole per_exercise-s
    assert "Rowing With Rowing Ergometer" not in analyze.workout_analysis(conn, w2, cache)["per_exercise"]


def test_pr_hits_and_insight_text(conn):
    w1, w2, w3 = _three_rows(conn)
    a2 = analyze.workout_analysis(conn, w2)
    assert a2["pr_hits"] == ["Bent Over Barbell Row"]
    assert "Uus rekord: Bent Over Barbell Row" in analyze.format_insight(a2)
    assert analyze.workout_analysis(conn, w3)["pr_hits"] == []
    assert analyze.workout_analysis(conn, w1)["pr_hits"] == []


def test_pr_at_time_keeps_old_records():
    # märtsi rekord jääb rekordiks ka siis, kui juunis ületatakse
    s = [_sess("2026-03-01", work_weight=60.0, top_reps=8),
         _sess("2026-03-08", work_weight=65.0, top_reps=8),
         _sess("2026-06-01", work_weight=70.0, top_reps=8)]
    for x in s:
        x["sets"] = [{"weight": x["work_weight"], "reps": x["top_reps"]}]
    assert analyze.is_pr_at(s[:2]) is True
    assert analyze.is_pr_at(s[:3]) is True
    assert analyze.is_pr_at(s[:1]) is False
    # sama kaal, rohkem kordusi = PR; vähem = mitte
    s2 = s[:2] + [_sess("2026-03-15", work_weight=65.0, top_reps=9)]
    s2[-1]["sets"] = [{"weight": 65.0, "reps": 9}]
    assert analyze.is_pr_at(s2) is True


def test_weeks_on_plateau_measures_current_plateau():
    same = [_sess("2026-05-04", work_weight=70.0, top_reps=8),
            _sess("2026-05-11", work_weight=70.0, top_reps=8),
            _sess("2026-05-18", work_weight=70.0, top_reps=8)]
    assert analyze.weeks_on_plateau(same) == 2
    # uus harjutus kaks korda sama: 1 nädal, mitte "esimesest sessioonist"
    assert analyze.weeks_on_plateau(same[:2]) == 1
    # viimane kord muutus → platoo 0 nädalat
    changed = same + [_sess("2026-05-25", work_weight=72.5, top_reps=6)]
    assert analyze.weeks_on_plateau(changed) == 0
    # varem 20 nädalat arenguta, aga vahepeal muutus (langus) → mõõdab viimasest muutusest
    hist = [_sess("2026-01-05", work_weight=70.0, top_reps=8),
            _sess("2026-03-02", work_weight=65.0, top_reps=8),
            _sess("2026-05-18", work_weight=65.0, top_reps=8),
            _sess("2026-05-25", work_weight=65.0, top_reps=8)]
    assert analyze.weeks_on_plateau(hist) == 12
    assert analyze.weeks_on_plateau(same[:1]) is None


def test_muscle_balance_uses_calendar_weeks(conn):
    # W20: 1000 kg selga; W25: 500 kg selga. 4 kalendrinädalat (W22–W25) EI sisalda W20.
    pg.save_to_db(_workout("A", datetime(2026, 5, 12, 10), [
        _ex("Bent Over Barbell Row", [(100.0, 10)])]), conn)
    pg.save_to_db(_workout("B", datetime(2026, 6, 16, 10), [
        _ex("Bent Over Barbell Row", [(50.0, 10)])]), conn)
    assert analyze.muscle_balance(conn, weeks_back=4) == {"selg": 500.0}
    assert analyze.balance_window(conn, weeks_back=4) == ["2026-W22", "2026-W25"]
    assert analyze.muscle_balance(conn, weeks_back=6) == {"selg": 1500.0}
    trend, totals = analyze.volume_trend(conn, weeks_back=6)
    assert [t for _, t in totals] == [1000.0, 0.0, 0.0, 0.0, 0.0, 500.0]
    assert trend == "kahaneb"
