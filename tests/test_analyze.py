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
