"""Trenn 2.0 — SQLite andmebaasi ühendus + skeem.

Põhireegel: weight_kg = NULL tähendab "kaalu pole logitud" (TRX/kehakaal/puuduv).
EI tohi olla 0.0, mida võrreldakse kui tugevuse langust.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "trenn.db"

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
    kcal INTEGER,
    notes TEXT,
    source TEXT,
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


def get_db(db_path=None):
    """Tagasta sqlite3 ühendus foreign_keys=ON ja Row factory'ga."""
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    """Loo tabelid kui puuduvad."""
    conn.executescript(SCHEMA)
    conn.commit()


if __name__ == "__main__":
    conn = get_db()
    init_schema(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
    print("Tabelid loodud:", tables)
    conn.close()
