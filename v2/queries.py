"""Päringud andmebaasi vastu — taaskasutatav kiht analüüsile, HTML-ile, Krattile."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import exercise_config as cfg
from db import get_db


def all_workouts(conn) -> list[dict]:
    """Kõik trennid uuemast vanimani."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM workouts ORDER BY timestamp DESC"
    )]


def workout_sets(conn, workout_id: int) -> list[dict]:
    """Ühe trenni seeriad järjekorras."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM sets WHERE workout_id=? ORDER BY id", (workout_id,)
    )]


def exercise_sessions(conn, exercise_name: str) -> list[dict]:
    """Harjutuse ajalugu sessioonide kaupa (vanimast uuemani).

    Tagastab listi: [{date, timestamp, equipment, sets:[{reps,weight,duration}],
                      top_weight, top_duration, work_weight, top_reps, work_sets,
                      total_volume}]
    work_weight = enim korratud kaal; top_reps ja work_sets käivad SELLE kaalu
    seeriate kohta (ramp 70×12, 80×8, 90×8 → 90 kg, 8 kordust, 1 seeria).
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
        s["top_duration"] = max(durs) if durs else None
        if weights:
            # "töökaal" = enim korratud kaal; viigi korral suurim kaal.
            # Graafiku kaal ja kordused peavad tulema samast päris seeriast
            # (nt ramp 70×12, 80×8, 90×8 ei tohi muutuda võltsiks 80×12).
            s["work_weight"] = max(set(weights), key=lambda w: (weights.count(w), w))
            reps_at_work_weight = [
                x["reps"] for x in s["sets"]
                if x["weight"] == s["work_weight"] and x["reps"] is not None
            ]
            s["top_reps"] = max(reps_at_work_weight) if reps_at_work_weight else None
            s["work_sets"] = sum(1 for x in s["sets"] if x["weight"] == s["work_weight"])
        else:
            s["work_weight"] = None
            s["top_reps"] = max(repvals) if repvals else None
            s["work_sets"] = len(s["sets"])
        result.append(s)
    result.sort(key=lambda x: x["timestamp"])
    return result


def all_exercise_names(conn) -> list[str]:
    return [r["exercise_name"] for r in conn.execute(
        "SELECT DISTINCT exercise_name FROM sets ORDER BY exercise_name"
    )]


def exercise_meta(conn, name: str) -> dict | None:
    r = conn.execute("SELECT * FROM exercises WHERE name=?", (name,)).fetchone()
    return dict(r) if r else None


def compute_prs(conn) -> dict[str, dict]:
    """Arvuta rekordid baasist (üks tõeallikas).

    PR = suurim kaal harjutuse kohta; sama kaalu puhul enim kordusi; viigi
    korral ESIMENE saavutamise kuupäev (deterministlik).
    Cardio ja NULL-kaal harjutused: PR korduste järgi.
    """
    prs = {}
    for name in all_exercise_names(conn):
        if cfg.is_cardio(name):
            continue
        rows = conn.execute(
            """SELECT w.date, s.reps, s.weight_kg
               FROM sets s JOIN workouts w ON s.workout_id=w.id
               WHERE s.exercise_name=? AND s.weight_kg IS NOT NULL
               ORDER BY s.weight_kg DESC, s.reps DESC, w.date ASC LIMIT 1""",
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
                   ORDER BY s.reps DESC, w.date ASC LIMIT 1""",
                (name,),
            ).fetchone()
            if r2:
                prs[name] = {"weight": None, "reps": r2["reps"], "date": r2["date"]}
    return prs


def iso_week(date_str: str) -> str:
    """'2026-05-21' -> '2026-W21'."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%G-W%V")


def iso_weeks_between(first: str, last: str) -> list[str]:
    """Kõik ISO-nädalad 'YYYY-Www' vahemikus (kaasa arvatud), järjest."""
    y1, w1 = (int(x) for x in first.split("-W"))
    y2, w2 = (int(x) for x in last.split("-W"))
    d = datetime.fromisocalendar(y1, w1, 1)
    end = datetime.fromisocalendar(y2, w2, 1)
    out = []
    while d <= end:
        out.append(d.strftime("%G-W%V"))
        d += timedelta(days=7)
    return out


def weekly_volume(conn, fill_gaps: bool = True) -> dict[str, dict[str, float]]:
    """Maht nädalate kaupa (ISO nädal) lihasgrupi lõikes.

    fill_gaps=True: ka treeninguta nädalad on võtmena ({}), et "viimased N nädalat"
    tähendaks kalendrinädalaid, mitte "N viimast treenitud nädalat".
    """
    rows = conn.execute(
        """SELECT w.date, s.exercise_name, s.total_volume, s.reps
           FROM sets s JOIN workouts w ON s.workout_id=w.id"""
    ).fetchall()
    weeks = {}
    for r in rows:
        wk = iso_week(r["date"])
        mg = cfg.muscle_for(r["exercise_name"])
        weeks.setdefault(wk, {}).setdefault(mg, 0.0)
        weeks[wk][mg] += r["total_volume"] or 0.0
    if fill_gaps and weeks:
        for wk in iso_weeks_between(min(weeks), max(weeks)):
            weeks.setdefault(wk, {})
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
