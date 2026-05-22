"""Analüüsimootor — progressioon-teadlik, varustus-teadlik.

Põhiprintsiibid:
  - Topeltprogressioon: kaal↑ + kordused↓ = areng, MITTE regress
  - Varustus-teadlik: võrdle ainult sama equipment'i sees; vahetus = neutraalne
  - NULL-kaal: võrdle korduste põhjal
  - Tekst ütleb MUSTREID mida kasutaja ise ei näe, EI korda numbreid
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db
import queries as q
import exercise_config as cfg


def exercise_status(sessions):
    """Hinda harjutuse seis viimaste sessioonide põhjal.

    Tagastab: 'areneb' | 'seisab' | 'stabiilne' | 'regress' | 'uus' | 'vahetus'
    sessions = q.exercise_sessions() väljund (vanimast uuemani).
    """
    if len(sessions) < 2:
        return "uus"
    last = sessions[-1]
    prev = sessions[-2]

    # aja-põhine harjutus (Plank): võrdle kestust sekundites
    ld, pd = last.get("top_duration"), prev.get("top_duration")
    if ld is not None and pd is not None:
        if ld > pd:
            return "areneb"
        if ld < pd:
            return "regress"
        return _check_plateau(sessions, key="duration")

    # varustusvahetus -> neutraalne (ei saa võrrelda õunu apelsinidega)
    if last["equipment"] != prev["equipment"]:
        return "vahetus"

    lw, pw = last["work_weight"], prev["work_weight"]
    lr, pr = last["top_reps"], prev["top_reps"]

    # üleminek NULL-kaal (TRX/kehakaal) <-> päris kaal (masin/raskus) = de facto
    # varustusvahetus, ei võrdle (väldib võltsregressi nagu Face Pull TRX->masin)
    if (lw is None) != (pw is None):
        return "vahetus"

    # mõlemad NULL-kaal (TRX/kehakaal/cardio): võrdle kordusi
    if lw is None or pw is None:
        if lr is None or pr is None:
            return "stabiilne"
        if lr > pr:
            return "areneb"
        if lr < pr:
            return "regress"
        return _check_plateau(sessions, key="reps")

    # kaal tõusis -> areng (ka kui kordused kukkusid = topeltprogressioon)
    if lw > pw:
        return "areneb"
    # kaal langes -> regress (sama varustus)
    if lw < pw:
        return "regress"
    # kaal sama: vaata kordusi
    if lr is not None and pr is not None:
        if lr > pr:
            return "areneb"
        if lr < pr:
            return "regress"
    return _check_plateau(sessions, key="weight")


def _check_plateau(sessions, key="weight", n=3):
    """Kas viimased n sessiooni on identsed -> seisab."""
    if len(sessions) < n:
        return "stabiilne"
    recent = sessions[-n:]
    if key == "weight":
        vals = [(s["work_weight"], s["top_reps"]) for s in recent]
    elif key == "duration":
        vals = [s.get("top_duration") for s in recent]
    else:
        vals = [s["top_reps"] for s in recent]
    if len(set(vals)) == 1:
        return "seisab"
    return "stabiilne"


STATUS_EMOJI = {
    "areneb": "🟢", "seisab": "🟡", "regress": "🔴",
    "stabiilne": "⚪", "vahetus": "🔵", "uus": "✨",
}
STATUS_TEXT = {
    "areneb": "areneb", "seisab": "seisab", "regress": "tagasilangus",
    "stabiilne": "stabiilne", "vahetus": "varustus vahetus", "uus": "uus",
}


def weeks_since_progress(sessions):
    """Mitu nädalat tagasi oli viimane areng (kaalu või korduste tõus)."""
    if len(sessions) < 2:
        return None
    last_progress_idx = None
    for i in range(1, len(sessions)):
        cur, prev = sessions[i], sessions[i - 1]
        if cur["equipment"] != prev["equipment"]:
            continue
        cw, pw = cur["work_weight"], prev["work_weight"]
        cr, pr = cur["top_reps"], prev["top_reps"]
        improved = False
        if cw is not None and pw is not None and cw > pw:
            improved = True
        elif cr is not None and pr is not None and cr > pr:
            improved = True
        if improved:
            last_progress_idx = i
    if last_progress_idx is None:
        ref = sessions[0]["date"]
    else:
        ref = sessions[last_progress_idx]["date"]
    d = datetime.strptime(sessions[-1]["date"], "%Y-%m-%d") - \
        datetime.strptime(ref, "%Y-%m-%d")
    return d.days // 7


def analyze_all_exercises(conn):
    """Iga harjutuse staatus + nädalad arenguta."""
    out = {}
    for name in q.all_exercise_names(conn):
        if cfg.is_cardio(name):
            continue
        sess = q.exercise_sessions(conn, name)
        if not sess:
            continue
        out[name] = {
            "status": exercise_status(sess),
            "sessions": len(sess),
            "weeks_stuck": weeks_since_progress(sess),
            "last_date": sess[-1]["date"],
            "equipment": sess[-1]["equipment"],
            "muscle": cfg.muscle_for(name),
        }
    return out


def muscle_balance(conn, weeks_back=4):
    """Lihasgrupi maht viimase N nädala jooksul."""
    wv = q.weekly_volume(conn)
    recent_weeks = list(wv.keys())[-weeks_back:]
    balance = {}
    for wk in recent_weeks:
        for mg, vol in wv[wk].items():
            if mg == "kardio":
                continue
            balance[mg] = balance.get(mg, 0.0) + vol
    return dict(sorted(balance.items(), key=lambda x: -x[1]))


def volume_trend(conn, weeks_back=6):
    """Kogumahu trend viimaste nädalate lõikes (kasvab/kahaneb/stabiilne)."""
    wv = q.weekly_volume(conn)
    weeks = list(wv.keys())[-weeks_back:]
    totals = []
    for wk in weeks:
        t = sum(v for mg, v in wv[wk].items() if mg != "kardio")
        totals.append((wk, t))
    if len(totals) < 3:
        return "vähe andmeid", totals
    first_half = sum(t for _, t in totals[:len(totals)//2])
    second_half = sum(t for _, t in totals[len(totals)//2:])
    if second_half > first_half * 1.1:
        trend = "kasvab"
    elif second_half < first_half * 0.9:
        trend = "kahaneb"
    else:
        trend = "stabiilne"
    return trend, totals


def workout_insight(conn, workout_id):
    """Mustripõhine tekst ühe trenni kohta — mida kasutaja ise ei näe.

    EI korda numbreid (kaal/kordused on tabelis). Toob esile:
    - PR-id, varustusvahetused, topeltprogressiooni edusammud
    - mis harjutus seisab
    """
    sets = q.workout_sets(conn, workout_id)
    if not sets:
        return ""
    prs = q.compute_prs(conn)
    wrow = conn.execute("SELECT * FROM workouts WHERE id=?", (workout_id,)).fetchone()
    wdate = wrow["date"]

    exercises = {}
    for s in sets:
        exercises.setdefault(s["exercise_name"], []).append(s)

    insights = []
    pr_hits = []
    switches = []
    progress = []
    stuck = []

    for name, ex_sets in exercises.items():
        if cfg.is_cardio(name):
            continue
        sess = q.exercise_sessions(conn, name)
        if len(sess) < 2:
            continue
        status = exercise_status(sess)
        # PR sel kuupäeval?
        pr = prs.get(name)
        if pr and pr.get("date") == wdate:
            pr_hits.append(name)
        if status == "vahetus":
            switches.append((name, sess[-2]["equipment"], sess[-1]["equipment"]))
        elif status == "areneb":
            # topeltprogressioon: kaal tõusis aga kordused kukkusid?
            if sess[-1]["work_weight"] and sess[-2]["work_weight"] and \
               sess[-1]["work_weight"] > sess[-2]["work_weight"] and \
               (sess[-1]["top_reps"] or 0) < (sess[-2]["top_reps"] or 0):
                progress.append((name, "raskus tõusis — kordused taastuvad järk-järgult, plaanipärane"))
            else:
                progress.append((name, "areng"))
        elif status == "seisab":
            wk = weeks_since_progress(sess)
            stuck.append((name, wk))

    # Koosta tekst
    if pr_hits:
        if len(pr_hits) >= 3:
            insights.append(f"🏆 Tugev päev — {len(pr_hits)} uut rekordit ühes trennis.")
        else:
            insights.append(f"🏆 Uus rekord: {', '.join(pr_hits)}.")
    for name, frm, to in switches:
        frm_t = _equip_name(frm)
        to_t = _equip_name(to)
        insights.append(f"🔵 {name}: varustus vahetus ({frm_t} → {to_t}) — "
                        f"otsest võrdlust eelmisega ei tee, sest koormus on eri tüüpi.")
    dp = [p for p in progress if "plaanipärane" in p[1]]
    for name, msg in dp:
        insights.append(f"📈 {name}: {msg}.")
    if stuck:
        for name, wk in stuck:
            if wk and wk >= 2:
                insights.append(f"🟡 {name} on püsinud samal tasemel ~{wk} nädalat — "
                                f"aeg kaalu või korduseid lükata.")
    if not insights:
        insights.append("Korralik sessioon — andmed jätkavad ühtlast joont.")
    return "\n".join(insights)


def _equip_name(e):
    return {"trx": "TRX", "machine": "masin", "cable": "kaabel",
            "barbell": "kang", "dumbbell": "hantlid",
            "bodyweight": "kehakaal", "cardio": "kardio"}.get(e, e or "?")


if __name__ == "__main__":
    conn = get_db()
    print("=== Harjutuste staatus ===")
    statuses = analyze_all_exercises(conn)
    for name, info in sorted(statuses.items(), key=lambda x: x[1]["muscle"]):
        em = STATUS_EMOJI.get(info["status"], "")
        print(f"  {em} {name} [{info['muscle']}]: {info['status']} "
              f"({info['sessions']} sessiooni, {info['equipment']})")
    print("\n=== Lihasgrupi tasakaal (4 näd) ===")
    for mg, vol in muscle_balance(conn).items():
        print(f"  {mg}: {vol:.0f} kg")
    print("\n=== Mahu trend ===")
    trend, totals = volume_trend(conn)
    print(f"  {trend}")
    # viimase trenni insight
    last = conn.execute("SELECT id, date, workout_name FROM workouts ORDER BY timestamp DESC LIMIT 1").fetchone()
    print(f"\n=== Insight: {last['date']} {last['workout_name']} ===")
    print(workout_insight(conn, last["id"]))
    conn.close()
