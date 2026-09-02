"""Genereeri mobile-first HTML üks-fail (kalender -> trenn -> harjutus, Chart.js).

Kogu andmestik embeditakse JSON-ina, JS hoolitseb navigatsiooni eest.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import analyze as a
import exercise_config as cfg
import queries as q
from db import get_db

OUT = Path(__file__).parent.parent / "site" / "index.html"
TEMPLATE = Path(__file__).parent / "template.html"


def group_sets(sets):
    """Grupeeri järjestikused sama (kaal,kordused) seeriad: N × reps · kaal."""
    groups = []
    for s in sets:
        key = (s["reps"], s["weight_kg"], s["duration_sec"])
        if groups and groups[-1]["key"] == key:
            groups[-1]["count"] += 1
        else:
            groups.append({"key": key, "count": 1, "reps": s["reps"],
                           "weight": s["weight_kg"], "duration": s["duration_sec"],
                           "equipment": s["equipment"]})
    return groups


def build_payload(conn):
    workouts = q.all_workouts(conn)
    sess_cache = a.build_session_cache(conn)      # üks kord, mitte iga trenn × harjutus
    statuses = a.analyze_all_exercises(conn, sess_cache)
    prs = q.compute_prs(conn)

    # Trennid + grupeeritud seeriad + analüüs SELLE trenni hetkeseisuga
    wlist = []
    for w in workouts:
        sets = q.workout_sets(conn, w["id"])
        ex_order = []
        ex_sets = {}
        for s in sets:
            if s["exercise_name"] not in ex_sets:
                ex_sets[s["exercise_name"]] = []
                ex_order.append(s["exercise_name"])
            ex_sets[s["exercise_name"]].append(s)
        analysis = a.workout_analysis(conn, w["id"], sess_cache)
        exercises = []
        for name in ex_order:
            grouped = group_sets(ex_sets[name])
            pe = analysis["per_exercise"].get(name, {})
            exercises.append({
                "name": name,
                "muscle": cfg.muscle_for(name),
                "is_cardio": cfg.is_cardio(name),
                "is_time": cfg.is_time_based(name),
                "status": pe.get("status"),
                "delta_kg": pe.get("delta_kg"),
                "delta_reps": pe.get("delta_reps"),
                "pr": pe.get("pr", False),
                "first": pe.get("first", False),
                "groups": [{"count": g["count"], "reps": g["reps"],
                            "weight": g["weight"], "duration": g["duration"],
                            "equipment": g["equipment"]}
                           for g in grouped],
            })
        dist_km = w["distance_m"] / 1000 if w.get("distance_m") else None
        wlist.append({
            "id": w["id"],
            "date": w["date"],
            "timestamp": w["timestamp"],
            "name": w["workout_name"],
            "type": w["workout_type"],
            "duration": w["duration_min"],
            "volume": round(w["total_volume"] or 0),
            "distance_km": round(dist_km, 1) if dist_km else None,
            "avg_speed_kmh": (round(dist_km / (w["duration_min"] / 60), 1)
                              if dist_km and w.get("duration_min") else None),
            "avg_hr": w["avg_hr"],
            "kcal": w["kcal"],
            "exercises": exercises,
            "pr_count": len(analysis["pr_hits"]),
            "prs": analysis["pr_hits"],
            "insight": a.format_insight(analysis),
        })

    # Harjutused + ajalugu graafiku jaoks
    ex_targets = {}
    for row in conn.execute("SELECT name, target_sets, target_reps_min, target_reps_max FROM exercises"):
        ex_targets[row["name"]] = {
            "sets": row["target_sets"],
            "reps_min": row["target_reps_min"],
            "reps_max": row["target_reps_max"],
        }

    exlist = {}
    for name, sess in sess_cache.items():
        info = statuses.get(name, {})
        tgt = ex_targets.get(name, {})
        # fail = sama varustus + sama kaal mis eelmine kord, aga kordused kukkusid
        history_with_fail = []
        for i, s in enumerate(sess):
            fail = False
            if i > 0:
                prev_s = sess[i - 1]
                same_equip = s["equipment"] == prev_s["equipment"]
                try:
                    days_gap = (datetime.strptime(s["date"], "%Y-%m-%d") -
                                datetime.strptime(prev_s["date"], "%Y-%m-%d")).days
                except ValueError:
                    days_gap = 0
                if same_equip and days_gap <= a.PAUSE_DAYS:
                    pw, cw = prev_s["work_weight"], s["work_weight"]
                    pr, cr = prev_s["top_reps"], s["top_reps"]
                    if pw is not None and cw is not None and cw == pw:
                        if pr is not None and cr is not None and cr < pr:
                            fail = True
            history_with_fail.append({
                "date": s["date"],
                "weight": s["work_weight"],
                "reps": s["top_reps"],
                "sets": s["work_sets"],           # seeriad TÖÖKAALUL (ramp: 90 kg × 1, mitte 3)
                "duration": s.get("top_duration"),
                "equipment": s["equipment"],
                "fail": fail,
            })
        exlist[name] = {
            "name": name,
            "muscle": cfg.muscle_for(name),
            "equipment": (sess[-1]["equipment"] if sess else None),
            "is_cardio": cfg.is_cardio(name),
            "is_time": cfg.is_time_based(name),
            "status": info.get("status", "uus"),
            "weeks_stuck": info.get("weeks_stuck"),
            "pr": prs.get(name),
            "target": tgt,
            "history": history_with_fail,
        }

    # Ülevaade / mustrid (kalendrinädalad, ankur = viimane treenitud nädal)
    balance = a.muscle_balance(conn)
    window = a.balance_window(conn)
    trend, totals = a.volume_trend(conn)

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
    krat_notes.append(f"📊 Kogumahu trend ({len(totals)} näd): {trend}.")
    growing = [n for n, i in statuses.items() if i["status"] == "areneb"]
    krat_notes.append(f"🟢 Arengus {len(growing)} harjutust {len(statuses)}-st.")

    return {
        "generated": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "workouts": wlist,
        "exercises": exlist,
        "balance": balance,
        "balance_window": window,
        "trend": trend,
        "weekly_volume": q.weekly_volume(conn),
        "krat_notes": krat_notes,
        "stats": {
            "total_workouts": len(wlist),
            "total_exercises": len(exlist),
            "date_range": [workouts[-1]["date"], workouts[0]["date"]] if workouts else [],
        },
    }


def render(conn, out: Path = OUT) -> Path:
    """Genereeri HTML antud ühendusest ja kirjuta `out`-i. Tagastab kirjutatud tee.

    Eraldi funktsioon, et testid saaksid renderdada tmp-kausta ilma
    projekti site/ kausta puutumata.
    """
    payload = build_payload(conn)
    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False))
    html = html.replace("{{ generated }}", payload["generated"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def main():
    conn = get_db()
    out = render(conn)
    n_workouts = conn.execute("SELECT COUNT(*) FROM workouts").fetchone()[0]
    n_exercises = conn.execute("SELECT COUNT(DISTINCT exercise_name) FROM sets").fetchone()[0]
    print(f"✓ HTML genereeritud: {out} ({out.stat().st_size} baiti)")
    print(f"  {n_workouts} trenni, {n_exercises} harjutust")
    conn.close()


if __name__ == "__main__":
    main()
