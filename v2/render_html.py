"""Genereeri mobile-first HTML üks-fail (kalender -> trenn -> harjutus, Chart.js).

Kogu andmestik embeditakse JSON-ina, JS hoolitseb navigatsiooni eest.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db
import queries as q
import analyze as a
import exercise_config as cfg

OUT = Path(__file__).parent.parent / "index.html"
TEMPLATE = Path(__file__).parent / "template.html"


def group_sets(sets):
    """Grupeeri järjestikused sama (kaal,kordused) seeriad: N × reps · kaal."""
    groups = []
    for s in sets:
        key = (s["reps"], s["weight_kg"])
        if groups and groups[-1]["key"] == key:
            groups[-1]["count"] += 1
        else:
            groups.append({"key": key, "count": 1, "reps": s["reps"],
                           "weight": s["weight_kg"], "equipment": s["equipment"]})
    return groups


def build_payload(conn):
    workouts = q.all_workouts(conn)
    statuses = a.analyze_all_exercises(conn)
    prs = q.compute_prs(conn)

    # Trennid + grupeeritud seeriad + insight
    wlist = []
    for w in workouts:
        sets = q.workout_sets(conn, w["id"])
        # grupeeri harjutuse kaupa, säilitades järjekorra
        ex_order = []
        ex_sets = {}
        for s in sets:
            if s["exercise_name"] not in ex_sets:
                ex_sets[s["exercise_name"]] = []
                ex_order.append(s["exercise_name"])
            ex_sets[s["exercise_name"]].append(s)
        exercises = []
        for name in ex_order:
            grouped = group_sets(ex_sets[name])
            exercises.append({
                "name": name,
                "muscle": cfg.muscle_for(name),
                "is_cardio": cfg.is_cardio(name),
                "groups": [{"count": g["count"], "reps": g["reps"],
                            "weight": g["weight"], "equipment": g["equipment"]}
                           for g in grouped],
            })
        wlist.append({
            "id": w["id"],
            "date": w["date"],
            "timestamp": w["timestamp"],
            "name": w["workout_name"],
            "type": w["workout_type"],
            "duration": w["duration_min"],
            "volume": round(w["total_volume"] or 0),
            "avg_hr": w["avg_hr"],
            "kcal": w["kcal"],
            "exercises": exercises,
            "insight": a.workout_insight(conn, w["id"]),
        })

    # Harjutused + ajalugu graafiku jaoks
    exlist = {}
    for name in q.all_exercise_names(conn):
        sess = q.exercise_sessions(conn, name)
        info = statuses.get(name, {})
        exlist[name] = {
            "name": name,
            "muscle": cfg.muscle_for(name),
            "equipment": (sess[-1]["equipment"] if sess else None),
            "is_cardio": cfg.is_cardio(name),
            "status": info.get("status", "uus"),
            "weeks_stuck": info.get("weeks_stuck"),
            "pr": prs.get(name),
            "history": [
                {"date": s["date"], "weight": s["work_weight"],
                 "top_weight": s["top_weight"], "reps": s["top_reps"],
                 "volume": round(s["total_volume"]), "equipment": s["equipment"]}
                for s in sess
            ],
        }

    # Ülevaade / mustrid
    balance = a.muscle_balance(conn)
    trend, totals = a.volume_trend(conn)
    weekly = q.weekly_volume(conn)

    # globaalsed mustrid (Kratt märkab)
    krat_notes = []
    stuck = [(n, i["weeks_stuck"]) for n, i in statuses.items()
             if i["status"] == "seisab" and i.get("weeks_stuck") and i["weeks_stuck"] >= 2]
    stuck.sort(key=lambda x: -(x[1] or 0))
    if stuck:
        items = ", ".join(f"{n} (~{w} näd)" for n, w in stuck[:3])
        krat_notes.append(f"🟡 Seisab kohal: {items} — aeg koormust lükata.")
    if balance:
        mgs = list(balance.items())
        top, low = mgs[0], mgs[-1]
        krat_notes.append(f"⚖️ Mahu fookus: {top[0]} on kõige treenitud, {low[0]} kõige vähem.")
    krat_notes.append(f"📊 Kogumahu trend (6 näd): {trend}.")
    growing = [n for n, i in statuses.items() if i["status"] == "areneb"]
    krat_notes.append(f"🟢 Arengus {len(growing)} harjutust {len(statuses)}-st.")

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "workouts": wlist,
        "exercises": exlist,
        "balance": balance,
        "trend": trend,
        "weekly_volume": weekly,
        "krat_notes": krat_notes,
        "stats": {
            "total_workouts": len(wlist),
            "total_exercises": len(exlist),
            "date_range": [workouts[-1]["date"], workouts[0]["date"]] if workouts else [],
        },
    }


def main():
    conn = get_db()
    payload = build_payload(conn)
    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    # calendar.html = alias
    (OUT.parent / "calendar.html").write_text(html, encoding="utf-8")
    print(f"✓ HTML genereeritud: {OUT} ({len(html)} baiti)")
    print(f"  {payload['stats']['total_workouts']} trenni, "
          f"{payload['stats']['total_exercises']} harjutust")
    conn.close()


if __name__ == "__main__":
    main()
