import exercise_config as cfg


def test_equipment_and_muscle_keys_consistent():
    # kaks paralleelset dicti peavad katma täpselt samad harjutused
    assert set(cfg.DEFAULT_EQUIPMENT) == set(cfg.MUSCLE_GROUP)


def test_previously_missing_exercises_are_configured():
    # 2026-09 audit: need kolm olid baasis, aga configis puudu -> "muu 3452 kg"
    assert cfg.muscle_for("Dumbbell Flyes") == "rind"
    assert cfg.muscle_for("Reverse Flyes") == "õlad"
    assert cfg.muscle_for("Lying Leg Curls") == "jalad"
    assert cfg.equipment_for("Lying Leg Curls") == "machine"


def test_orphan_exercises(loaded_conn):
    assert cfg.orphan_exercises(loaded_conn) == []
    loaded_conn.execute(
        "INSERT INTO sets (workout_id, exercise_name, set_number, reps) VALUES (1,'Mystery Curl',1,10)"
    )
    assert cfg.orphan_exercises(loaded_conn) == ["Mystery Curl"]


def test_sync_to_db_fixes_muu_inserts_missing_keeps_manual(conn):
    conn.execute("INSERT INTO exercises (name, muscle_group) VALUES ('Dumbbell Flyes','muu')")
    changed = cfg.sync_to_db(conn)
    assert changed > 0
    row = conn.execute(
        "SELECT muscle_group, default_equipment FROM exercises WHERE name='Dumbbell Flyes'"
    ).fetchone()
    assert (row[0], row[1]) == ("rind", "dumbbell")
    # puuduv harjutus lisatakse
    assert conn.execute(
        "SELECT muscle_group FROM exercises WHERE name='Lying Leg Curls'"
    ).fetchone()[0] == "jalad"
    # CSV rep-vahemikku ei puututa
    conn.execute(
        "UPDATE exercises SET target_reps_min=6, target_reps_max=10 WHERE name='Dumbbell Flyes'")
    cfg.sync_to_db(conn)
    r = conn.execute(
        "SELECT target_reps_min, target_reps_max FROM exercises WHERE name='Dumbbell Flyes'"
    ).fetchone()
    assert (r[0], r[1]) == (6, 10)
    # käsitsi määratud lihasgruppi ja varustust ei kirjutata üle
    conn.execute(
        "UPDATE exercises SET muscle_group='käed', default_equipment='cable' WHERE name='Dumbbell Flyes'")
    cfg.sync_to_db(conn)
    r = conn.execute(
        "SELECT muscle_group, default_equipment FROM exercises WHERE name='Dumbbell Flyes'"
    ).fetchone()
    assert (r[0], r[1]) == ("käed", "cable")
    # teine jooks on idempotentne
    assert cfg.sync_to_db(conn) == 0
