"""Päringud andmebaasi vastu — taaskasutatav kiht analüüsile, HTML-ile, Krattile."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db
import exercise_config as cfg


def all_workouts(conn):
    """Kõik trennid uuemast vanimani."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM workouts ORDER BY timestamp DESC"
    )]


def workout_sets(conn, workout_id):
    """Ühe trenni seeriad järjekorras."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM sets WHERE workout_id=? ORDER BY id", (workout_id,)
    )]


def exercise_sessions(conn, exercise_name):
    """Harjutuse ajalugu sessioonide kaupa (vanimast uuemani).

    Tagastab listi: [{date, timestamp, equipment, sets:[{reps,weight}],
                      top_weight, top_reps, total_volume}]
    """
    rows = conn.execute(
        """SELECT w.date, w.timestamp, s.set_number, s.reps, s.weight_kg,
                  s.equipment, s.total_volume, s.duration_sec
           FROM sets s JOIN workouts w ON s.workout_id=w.id
           WHERE s.exercise_name=?
           ORDER BY w.timestamp, s.set_number""",
        (exercise_name,),
    ).fetchall()
    sessions = {}
    for r in rows:
        key = r["timestamp"]
        if key not in sessions:
            sessions[key] = {"date": r["date"], "timestamp": r["timestamp"],
                             "equipment": r["equipment"], "sets": [],
                             "total_volume": 0.0}
        sessions[key]["sets"].append({"reps": r["reps"], "weight": r["weight_kg"],
                                       "duration": r["duration_sec"]})
        sessions[key]["total_volume"] += r["total_volume"] or 0.0
    result = []
    for s in sessions.values():
        weights = [x["weight"] for x in s["sets"] if x["weight"]]
        repvals = [x["reps"] for x in s["sets"] if x["reps"]]
        durs = [x["duration"] for x in s["sets"] if x["duration"]]
        s["top_weight"] = max(weights) if weights else None
        s["top_reps"] = max(repvals) if repvals else None
        s["top_duration"] = max(durs) if durs else None
        # "töökaal" = enim korratud kaal (mode), muidu max
        s["work_weight"] = max(set(weights), key=weights.count) if weights else None
        result.append(s)
    result.sort(key=lambda x: x["timestamp"])
    return result


def all_exercise_names(conn):
    return [r["exercise_name"] for r in conn.execute(
        "SELECT DISTINCT exercise_name FROM sets ORDER BY exercise_name"
    )]


def exercise_meta(conn, name):
    r = conn.execute("SELECT * FROM exercises WHERE name=?", (name,)).fetchone()
    return dict(r) if r else None


def compute_prs(conn):
    """Arvuta rekordid baasist (üks tõeallikas).

    PR = suurim kaal harjutuse kohta; sama kaalu puhul enim kordusi.
    Cardio ja NULL-kaal harjutused: PR korduste/aja järgi.
    """
    prs = {}
    for name in all_exercise_names(conn):
        if cfg.is_cardio(name):
            continue
        rows = conn.execute(
            """SELECT w.date, s.reps, s.weight_kg
               FROM sets s JOIN workouts w ON s.workout_id=w.id
               WHERE s.exercise_name=? AND s.weight_kg IS NOT NULL
               ORDER BY s.weight_kg DESC, s.reps DESC LIMIT 1""",
            (name,),
        ).fetchone()
        if rows:
            prs[name] = {"weight": rows["weight_kg"], "reps": rows["reps"],
                         "date": rows["date"]}
        else:
            # NULL-kaal: PR = enim kordusi
            r2 = conn.execute(
                """SELECT w.date, s.reps FROM sets s JOIN workouts w ON s.workout_id=w.id
                   WHERE s.exercise_name=? AND s.reps IS NOT NULL
                   ORDER BY s.reps DESC LIMIT 1""",
                (name,),
            ).fetchone()
            if r2:
                prs[name] = {"weight": None, "reps": r2["reps"], "date": r2["date"]}
    return prs


def weekly_volume(conn):
    """Maht nädalate kaupa (ISO nädal) lihasgrupi lõikes."""
    rows = conn.execute(
        """SELECT w.date, s.exercise_name, s.total_volume, s.reps
           FROM sets s JOIN workouts w ON s.workout_id=w.id"""
    ).fetchall()
    from datetime import datetime
    weeks = {}
    for r in rows:
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        wk = d.strftime("%G-W%V")
        mg = cfg.muscle_for(r["exercise_name"])
        weeks.setdefault(wk, {}).setdefault(mg, 0.0)
        weeks[wk][mg] += r["total_volume"] or 0.0
    return dict(sorted(weeks.items()))


if __name__ == "__main__":
    conn = get_db()
    print("Trenne:", len(all_workouts(conn)))
    print("Harjutusi:", len(all_exercise_names(conn)))
    prs = compute_prs(conn)
    print("\nRekordid (näide):")
    for n in ["Bent Over Barbell Row", "Barbell Bench Press", "Face Pull"]:
        print(" ", n, prs.get(n))
    conn.close()
