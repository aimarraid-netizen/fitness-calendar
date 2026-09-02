"""Trenn 2.0 — SQLite andmebaasi ühendus + skeem.

Põhireegel: weight_kg = NULL tähendab "kaalu pole logitud" (TRX/kehakaal/puuduv).
EI tohi olla 0.0, mida võrreldakse kui tugevuse langust.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DB_PATH = Path(__file__).parent.parent / "data" / "trenn.db"

# Kõik ajatemplid baasis on LOKAALSED ja ühes formaadis. FIT/GPX annavad UTC
# (naive), CSV lokaalaja — enne salvestust käivad kõik läbi to_local_iso().
TZ = ZoneInfo(os.getenv("TRENN_TZ", "Europe/Tallinn"))
TS_FMT = "%Y-%m-%d %H:%M:%S"

# Kardio-veerud, mis lisandusid pärast algskeemi (ensure_columns migreerib vanad baasid)
CARDIO_COLS = {
    "z1_min": "REAL", "z2_min": "REAL", "z3_min": "REAL", "z4_min": "REAL", "z5_min": "REAL",
    "ascent_m": "REAL",
    "max_hr": "INTEGER",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    workout_name TEXT,
    workout_type TEXT,
    duration_min INTEGER,
    distance_m REAL,
    total_volume REAL,
    avg_hr INTEGER,
    max_hr INTEGER,
    kcal INTEGER,
    notes TEXT,
    source TEXT,
    z1_min REAL, z2_min REAL, z3_min REAL, z4_min REAL, z5_min REAL,  -- Karvoneni tsoonid (min)
    ascent_m REAL,
    UNIQUE(timestamp, workout_name)
);

CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY,
    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
    exercise_name TEXT NOT NULL,
    set_number INTEGER,
    reps INTEGER,
    weight_kg REAL,           -- NULL kui kaalu pole logitud (EI 0.0!)
    equipment TEXT,           -- trx/machine/barbell/dumbbell/bodyweight/cable; NULL=peri vaikest
    total_volume REAL,
    duration_sec REAL,
    max_hr INTEGER,
    avg_hr INTEGER,
    kcal INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS exercises (
    name TEXT PRIMARY KEY,
    default_equipment TEXT,
    target_sets INTEGER,
    target_reps_min INTEGER,
    target_reps_max INTEGER,  -- NULL kui "max" (Plank, Leg Raise)
    muscle_group TEXT
);

CREATE INDEX IF NOT EXISTS idx_sets_workout ON sets(workout_id);
CREATE INDEX IF NOT EXISTS idx_sets_exercise ON sets(exercise_name);
CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
"""


def get_db(db_path=None) -> "sqlite3.Connection":
    """Tagasta sqlite3 ühendus foreign_keys=ON ja Row factory'ga."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn) -> None:
    """Loo tabelid kui puuduvad + migreeri vana baasi puuduvad veerud."""
    conn.executescript(SCHEMA)
    conn.commit()
    ensure_columns(conn)


def ensure_columns(conn) -> None:
    """Lisa hiljem lisandunud workouts-veerud kui puuduvad (vana DB migratsioon)."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(workouts)")}
    wanted = {"distance_m": "REAL", **CARDIO_COLS}
    added = []
    for name, typ in wanted.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE workouts ADD COLUMN {name} {typ}")
            added.append(name)
    if added:
        conn.commit()
        for c in added:
            print(f"  ✓ Lisatud veerg: workouts.{c}")


def to_local_iso(dt: datetime) -> str:
    """Ajatempel baasi jaoks: lokaalne aeg (TRENN_TZ), formaat 'YYYY-MM-DD HH:MM:SS'.

    Naive datetime loetakse UTC-ks — fitparse ja GPX <time>…Z annavad UTC ilma
    tzinfo-ta. Aware datetime teisendatakse. CSV-parser annab juba lokaalaja
    ja kutsub seda ainult formaadi ühtlustamiseks (vt local_naive_iso).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ).strftime(TS_FMT)


def local_naive_iso(dt: datetime) -> str:
    """Juba lokaalajas oleva naive datetime'i formaat (CSV-parser)."""
    return dt.strftime(TS_FMT)


if __name__ == "__main__":
    conn = get_db()
    init_schema(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    print("Tabelid loodud:", tables)
    conn.close()
