"""Harjutuste metaandmed: vaikevarustus, lihasgrupp, rep-vahemikud.

Need on alglaadimiseks. CSV-st tulevad rep-vahemikud kirjutavad hiljem üle
(CSV = uusim tõde). default_equipment on Kratti lives-muudatuste lähtepunkt.
"""

# Vaikevarustus harjutuse kohta.
# trx = TRX-rihmad/kehakaal, machine = masin, cable = kaabel,
# barbell = kang, dumbbell = hantlid, bodyweight = puhas kehakaal
DEFAULT_EQUIPMENT = {
    "Barbell Bench Press": "barbell",
    "Barbell Curl": "barbell",
    "Barbell Squat": "barbell",
    "Bent Over Barbell Row": "barbell",
    "Romanian Deadlift": "barbell",
    "Incline Dumbbell Press": "dumbbell",
    "One-Arm Dumbbell Row": "dumbbell",
    "Seated Hammer Curls": "dumbbell",
    "Side Lateral Raise": "dumbbell",
    "Shoulder Press": "dumbbell",
    "Seated Triceps Press": "dumbbell",
    "Lying Triceps Press": "barbell",
    "Wide-Grip Lat Pulldown": "cable",
    "Seated Cable Rows": "cable",
    "Triceps Pushdown with Rope": "cable",
    "Face Pull": "trx",          # kasutaja tegelik vaikevarustus (vahel masin)
    "Triceps Dips": "bodyweight",
    "Lying Leg Raise": "bodyweight",
    "Plank": "bodyweight",
    "Lunge": "bodyweight",
    "Single-Leg Press": "machine",
    "Standing Calf Raise": "machine",
    "Lying Leg Curls": "machine",
    "Dumbbell Flyes": "dumbbell",
    "Reverse Flyes": "dumbbell",
    "Rowing With Rowing Ergometer": "cardio",
    "Walking On Treadmill": "cardio",
    "Running": "cardio",
}

# Lihasgrupp harjutuse kohta
MUSCLE_GROUP = {
    "Barbell Bench Press": "rind",
    "Incline Dumbbell Press": "rind",
    "Dumbbell Flyes": "rind",
    "Barbell Curl": "biitseps",
    "Seated Hammer Curls": "biitseps",
    "Bent Over Barbell Row": "selg",
    "One-Arm Dumbbell Row": "selg",
    "Wide-Grip Lat Pulldown": "selg",
    "Seated Cable Rows": "selg",
    "Face Pull": "õlad",
    "Side Lateral Raise": "õlad",
    "Shoulder Press": "õlad",
    "Reverse Flyes": "õlad",
    "Lying Triceps Press": "triitseps",
    "Seated Triceps Press": "triitseps",
    "Triceps Pushdown with Rope": "triitseps",
    "Triceps Dips": "triitseps",
    "Barbell Squat": "jalad",
    "Romanian Deadlift": "jalad",
    "Lunge": "jalad",
    "Single-Leg Press": "jalad",
    "Lying Leg Curls": "jalad",
    "Standing Calf Raise": "sääred",
    "Lying Leg Raise": "kõht",
    "Plank": "kõht",
    "Rowing With Rowing Ergometer": "kardio",
    "Walking On Treadmill": "kardio",
    "Running": "kardio",
}

# Cardio/kehakaal-harjutused, kus weight_kg=0 EI ole viga (jätta NULL-iks,
# võrdlus käib korduste/aja põhjal).
NO_WEIGHT_EXPECTED = {
    "Rowing With Rowing Ergometer",
    "Walking On Treadmill",
    "Running",
    "Plank",
    "Lying Leg Raise",
    "Triceps Dips",
    "Lunge",
    "Face Pull",          # vahel TRX/kehakaal
}

CARDIO_EXERCISES = {
    "Rowing With Rowing Ergometer",
    "Walking On Treadmill",
    "Running",
}

# Aja-põhised harjutused: mõõdetakse sekundites (hoid), mitte kordustes/kaalus.
# Gymaholic ekspordib need valesti (reps=1, dur=0), seega kestus tuleb logida
# käsitsi Kratti kaudu või CSV TIME-veerust.
TIME_BASED = {
    "Plank",
}


def equipment_for(name: str) -> str | None:
    return DEFAULT_EQUIPMENT.get(name)


def muscle_for(name: str) -> str:
    return MUSCLE_GROUP.get(name, "muu")


def is_cardio(name: str) -> bool:
    return name in CARDIO_EXERCISES


def is_time_based(name: str) -> bool:
    return name in TIME_BASED


def orphan_exercises(conn) -> list[str]:
    """Harjutused, mis on baasis (sets), aga configis puuduvad.

    Puuduv config = lihasgrupp "muu" + equipment NULL -> bilanss ja
    varustusloogika on nende jaoks vaikselt katki. Kutsu impordil hoiatuseks.
    """
    rows = conn.execute("SELECT DISTINCT exercise_name FROM sets ORDER BY 1")
    return [r[0] for r in rows if r[0] not in MUSCLE_GROUP]


def sync_to_db(conn) -> int:
    """Kirjuta configi lihasgrupp/vaikevarustus exercises tabelisse.

    - muscle_group uuendatakse ainult kui NULL või "muu" (käsitsi määratut ei puututa)
    - default_equipment ainult kui NULL (Kratt `default` võib olla muutnud)
    - CSV-st tulnud rep-vahemikke EI puututa
    Tagastab muudetud/lisatud ridade arvu.
    """
    before = conn.total_changes
    for name, mg in MUSCLE_GROUP.items():
        conn.execute(
            """INSERT INTO exercises (name, default_equipment, muscle_group)
               VALUES (?,?,?)
               ON CONFLICT(name) DO UPDATE SET
                   muscle_group = CASE
                       WHEN exercises.muscle_group IS NULL OR exercises.muscle_group='muu'
                       THEN excluded.muscle_group ELSE exercises.muscle_group END,
                   default_equipment = COALESCE(exercises.default_equipment,
                                                excluded.default_equipment)
               WHERE exercises.muscle_group IS NULL OR exercises.muscle_group='muu'
                  OR exercises.default_equipment IS NULL""",
            (name, DEFAULT_EQUIPMENT.get(name), mg),
        )
    conn.commit()
    return conn.total_changes - before
