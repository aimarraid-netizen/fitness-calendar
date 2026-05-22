"""Migreeri vanad JSON-andmed SQLite-i.

Kriitiline teisendus: weight_kg == 0.0 jõuharjutusel -> NULL (mitte 0.0).
Cardio jätab nagu on. Strateegia -> exercises tabel.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, init_schema
import exercise_config as cfg

DATA = Path(__file__).parent.parent / "data"


def migrate_workouts(conn):
    hist = json.load(open(DATA / "workout_history.json"))["workouts"]
    n_workouts = 0
    n_sets = 0
    for wk in hist:
        cur = conn.execute(
            """INSERT OR IGNORE INTO workouts
               (timestamp, date, workout_name, workout_type, duration_min,
                total_volume, avg_hr, notes, source)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                wk["timestamp"], wk["date"], wk.get("workout_name"),
                wk.get("workout_type"), wk.get("duration_min"),
                wk.get("total_volume"), wk.get("avg_hr") or None,
                wk.get("notes") or None, wk.get("source", "gymaholic"),
            ),
        )
        if cur.rowcount == 0:
            # juba olemas (dedup) -> leia id
            row = conn.execute(
                "SELECT id FROM workouts WHERE timestamp=? AND workout_name=?",
                (wk["timestamp"], wk.get("workout_name")),
            ).fetchone()
            workout_id = row["id"]
        else:
            workout_id = cur.lastrowid
            n_workouts += 1

        exercise_seen = {}
        for i, e in enumerate(wk["exercises"], 1):
            name = e["name"]
            raw_weight = e.get("weight_kg", 0.0)
            # KRIITILINE: 0kg -> NULL (kaalu pole logitud), v.a kui tegelikult cardio
            if raw_weight and raw_weight > 0:
                weight = raw_weight
            else:
                weight = None
            equip = cfg.equipment_for(name)
            # iga Gymaholic kirje = üks seeria (sets=1). set_number = mitmes kord
            # seda harjutust selles trennis.
            exercise_seen[name] = exercise_seen.get(name, 0) + 1
            sets_count = e.get("sets", 1) or 1
            reps = e.get("reps")
            vol_per = (e.get("total_volume", 0) or 0) / sets_count if sets_count else 0
            for s in range(sets_count):
                if s > 0:
                    exercise_seen[name] += 1
                conn.execute(
                    """INSERT INTO sets
                       (workout_id, exercise_name, set_number, reps, weight_kg,
                        equipment, total_volume, duration_sec, max_hr, avg_hr, kcal)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        workout_id, name, exercise_seen[name], reps, weight, equip,
                        vol_per, e.get("duration_sec"),
                        e.get("max_hr") or None, e.get("avg_hr") or None,
                        e.get("kcal") or None,
                    ),
                )
                n_sets += 1
    conn.commit()
    return n_workouts, n_sets


def migrate_exercises(conn):
    """Lae exercises tabel: strateegia rep-vahemikud + config varustus/lihasgrupp."""
    strat = json.load(open(DATA / "training_strategy.json"))["exercises"]
    # kõik nimed mis baasis esinevad VÕI strateegias
    names = set(strat.keys())
    for r in conn.execute("SELECT DISTINCT exercise_name FROM sets"):
        names.add(r["exercise_name"])

    for name in sorted(names):
        s = strat.get(name, {})
        reps = s.get("reps", "")
        rmin = rmax = None
        if isinstance(reps, str) and "-" in reps:
            try:
                rmin, rmax = [int(x) for x in reps.split("-")]
            except ValueError:
                pass
        elif isinstance(reps, str) and reps.isdigit():
            rmin = rmax = int(reps)
        # "max" jääb NULL
        conn.execute(
            """INSERT OR REPLACE INTO exercises
               (name, default_equipment, target_sets, target_reps_min,
                target_reps_max, muscle_group)
               VALUES (?,?,?,?,?,?)""",
            (
                name, cfg.equipment_for(name), s.get("sets"),
                rmin, rmax, cfg.muscle_for(name),
            ),
        )
    conn.commit()
    return len(names)


def main():
    conn = get_db()
    init_schema(conn)
    # puhas migratsioon: tühjenda enne (idempotentne re-run)
    conn.executescript("DELETE FROM sets; DELETE FROM workouts; DELETE FROM exercises;")
    conn.commit()
    nw, ns = migrate_workouts(conn)
    ne = migrate_exercises(conn)
    print(f"Migreeritud: {nw} trenni, {ns} seeriat, {ne} harjutust")
    # kontroll: Face Pull NULL-kaalud
    fp_null = conn.execute(
        "SELECT COUNT(*) c FROM sets WHERE exercise_name='Face Pull' AND weight_kg IS NULL"
    ).fetchone()["c"]
    fp_total = conn.execute(
        "SELECT COUNT(*) c FROM sets WHERE exercise_name='Face Pull'"
    ).fetchone()["c"]
    print(f"Face Pull NULL-kaaluga seeriaid: {fp_null}/{fp_total}")
    conn.close()


if __name__ == "__main__":
    main()
