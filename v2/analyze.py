"""Analüüsimootor — progressioon-teadlik, varustus-teadlik.

Põhiprintsiibid:
  - Topeltprogressioon: kaal↑ + kordused↓ = areng, MITTE regress
  - Varustus-teadlik: võrdle ainult sama equipment'i sees; vahetus = neutraalne
  - NULL-kaal: võrdle korduste põhjal
  - Tekst ütleb MUSTREID mida kasutaja ise ei näe, EI korda numbreid
  - Trenni analüüs arvutatakse SELLE trenni hetkeseisuga (sessioonid kuni trennini),
    mitte harjutuse tänase seisuga — vanad trennid ei muutu tagantjärele
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import exercise_config as cfg
import queries as q
from db import get_db

PAUSE_DAYS = 28          # pikem paus = uus tsükkel, eelmisega ei võrdle
PLATEAU_SESSIONS = 3     # nii mitu identset sessiooni järjest = "seisab"


def _days_between(a: str, b: str) -> int:
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def exercise_status(sessions: list[dict]) -> str:
    """Hinda harjutuse seis viimaste sessioonide põhjal.

    Tagastab: 'areneb' | 'seisab' | 'stabiilne' | 'regress' | 'uus' | 'vahetus'
    sessions = q.exercise_sessions() väljund (vanimast uuemani).
    """
    if len(sessions) < 2:
        return "uus"
    last = sessions[-1]
    prev = sessions[-2]

    # Pikk paus = uus tsükkel, ei saa võrrelda eelmisega
    try:
        if _days_between(prev["date"], last["date"]) > PAUSE_DAYS:
            return "uus"
    except (ValueError, TypeError, KeyError):
        pass

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


def _check_plateau(sessions, key="weight", n=PLATEAU_SESSIONS):
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


def _level_key(s: dict) -> tuple:
    """Sessiooni 'tase' platoo tuvastuseks: mis tahes muutus katkestab platoo."""
    return (s.get("work_weight"), s.get("top_reps"), s.get("equipment"), s.get("top_duration"))


def weeks_on_plateau(sessions: list[dict]) -> int | None:
    """Mitu nädalat on (töökaal, kordused, varustus, kestus) püsinud muutumatuna.

    Mõõdab PRAEGUSE platoo algusest, mitte "viimasest arengust": kahel korral
    tehtud uus harjutus ei ole "20 nädalat seisnud", vaid seisab alates 1. korrast.
    """
    if len(sessions) < 2:
        return None
    cur = _level_key(sessions[-1])
    start = len(sessions) - 1
    while start > 0 and _level_key(sessions[start - 1]) == cur:
        start -= 1
    return _days_between(sessions[start]["date"], sessions[-1]["date"]) // 7


def _pr_key(s: dict) -> tuple:
    """Rekordi võrdlusvõti: (tippkaal, kordused tippkaalul, kestus). Suurem = parem."""
    top_w = s.get("top_weight")
    if top_w is not None:
        reps_at_top = max((x["reps"] or 0 for x in s.get("sets", []) if x.get("weight") == top_w),
                          default=s.get("top_reps") or 0)
        return (top_w, reps_at_top, 0)
    return (0, s.get("top_reps") or 0, s.get("top_duration") or 0)


def is_pr_at(sessions_upto: list[dict]) -> bool:
    """Kas viimane sessioon ületab KÕIKI varasemaid (PR sel hetkel, mitte all-time)."""
    if len(sessions_upto) < 2:
        return False
    cur = _pr_key(sessions_upto[-1])
    if cur == (0, 0, 0):
        return False
    return cur > max(_pr_key(s) for s in sessions_upto[:-1])


def build_session_cache(conn) -> dict[str, list[dict]]:
    """Kõigi harjutuste sessioonid ühe korraga (väldib O(trennid × harjutused) päringuid)."""
    return {name: q.exercise_sessions(conn, name) for name in q.all_exercise_names(conn)}


def analyze_all_exercises(conn, sess_cache: dict | None = None) -> dict[str, dict]:
    """Iga harjutuse staatus + nädalad platool (tänase seisuga)."""
    sess_cache = sess_cache or build_session_cache(conn)
    out = {}
    for name, sess in sess_cache.items():
        if cfg.is_cardio(name) or not sess:
            continue
        out[name] = {
            "status": exercise_status(sess),
            "sessions": len(sess),
            "weeks_stuck": weeks_on_plateau(sess),
            "last_date": sess[-1]["date"],
            "equipment": sess[-1]["equipment"],
            "muscle": cfg.muscle_for(name),
        }
    return out


def recent_weeks(conn, weeks_back: int) -> tuple[list[str], dict]:
    """Viimased N KALENDRINÄDALAT (lünkadeta), ankurdatud viimase treenitud nädala külge."""
    wv = q.weekly_volume(conn)          # fill_gaps=True → järjestikused ISO-nädalad
    weeks = list(wv)[-weeks_back:]
    return weeks, wv


def muscle_balance(conn, weeks_back: int = 4) -> dict[str, float]:
    """Lihasgrupi maht viimase N kalendrinädala jooksul (puuduv nädal = 0)."""
    weeks, wv = recent_weeks(conn, weeks_back)
    balance = {}
    for wk in weeks:
        for mg, vol in wv[wk].items():
            if mg == "kardio":
                continue
            balance[mg] = balance.get(mg, 0.0) + vol
    return dict(sorted(balance.items(), key=lambda x: -x[1]))


def balance_window(conn, weeks_back: int = 4) -> list[str]:
    """[esimene, viimane] ISO-nädal, mida muscle_balance katab — HTML pealkirja jaoks."""
    weeks, _ = recent_weeks(conn, weeks_back)
    return [weeks[0], weeks[-1]] if weeks else []


def volume_trend(conn, weeks_back: int = 6) -> tuple[str, list]:
    """Kogumahu trend viimaste kalendrinädalate lõikes (kasvab/kahaneb/stabiilne)."""
    weeks, wv = recent_weeks(conn, weeks_back)
    totals = [(wk, sum(v for mg, v in wv[wk].items() if mg != "kardio")) for wk in weeks]
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


def workout_analysis(conn, workout_id: int, sess_cache: dict | None = None) -> dict:
    """Struktureeritud analüüs ühe trenni kohta SELLE trenni hetkeseisuga.

    Tagastab: {pr_hits, switches, progress, stuck, per_exercise{name: {status,
    delta_kg, delta_reps, pr, first}}}. Tekst: format_insight(). HTML kuvab
    per_exercise otse (JS ei arvuta enam ise deltat).
    """
    result = {"pr_hits": [], "switches": [], "progress": [], "stuck": [], "per_exercise": {}}
    sets = q.workout_sets(conn, workout_id)
    if not sets:
        return result
    wrow = conn.execute("SELECT timestamp FROM workouts WHERE id=?", (workout_id,)).fetchone()
    wts = wrow["timestamp"]

    names = []
    for s in sets:
        if s["exercise_name"] not in names:
            names.append(s["exercise_name"])

    for name in names:
        if cfg.is_cardio(name):
            continue
        sess = (sess_cache or {}).get(name) or q.exercise_sessions(conn, name)
        idx = next((i for i, s in enumerate(sess) if s["timestamp"] == wts), None)
        if idx is None:
            continue
        upto = sess[:idx + 1]
        cur = upto[-1]
        prev = upto[-2] if len(upto) >= 2 else None
        status = exercise_status(upto)
        pr = is_pr_at(upto)

        delta_kg = delta_reps = None
        if prev is not None and status not in ("vahetus", "uus"):
            if cur["work_weight"] is not None and prev["work_weight"] is not None:
                delta_kg = round(cur["work_weight"] - prev["work_weight"], 2)
            if cur["top_reps"] is not None and prev["top_reps"] is not None:
                delta_reps = cur["top_reps"] - prev["top_reps"]

        result["per_exercise"][name] = {
            "status": status, "delta_kg": delta_kg, "delta_reps": delta_reps,
            "pr": pr, "first": idx == 0,
        }
        if pr:
            result["pr_hits"].append(name)
        if status == "vahetus":
            result["switches"].append((name, prev["equipment"], cur["equipment"]))
        elif status == "areneb":
            double = (delta_kg or 0) > 0 and (delta_reps or 0) < 0
            result["progress"].append(
                (name, "raskus tõusis — kordused taastuvad järk-järgult, plaanipärane"
                 if double else "areng"))
        elif status == "seisab":
            result["stuck"].append((name, weeks_on_plateau(upto)))
    return result


def format_insight(analysis: dict) -> str:
    """Mustripõhine eestikeelne tekst — EI korda numbreid, mis on tabelis."""
    insights = []
    pr_hits = analysis["pr_hits"]
    if pr_hits:
        if len(pr_hits) >= 3:
            insights.append(f"🏆 Tugev päev — {len(pr_hits)} uut rekordit ühes trennis.")
        else:
            insights.append(f"🏆 Uus rekord: {', '.join(pr_hits)}.")
    for name, frm, to in analysis["switches"]:
        insights.append(f"🔵 {name}: varustus vahetus ({_equip_name(frm)} → {_equip_name(to)}) — "
                        f"otsest võrdlust eelmisega ei tee, sest koormus on eri tüüpi.")
    for name, msg in analysis["progress"]:
        if "plaanipärane" in msg:
            insights.append(f"📈 {name}: {msg}.")
    for name, wk in analysis["stuck"]:
        if wk and wk >= 2:
            insights.append(f"🟡 {name} on püsinud samal tasemel ~{wk} nädalat — "
                            f"aeg kaalu või korduseid lükata.")
    if not insights:
        insights.append("Korralik sessioon — andmed jätkavad ühtlast joont.")
    return "\n".join(insights)


def workout_insight(conn, workout_id: int, sess_cache: dict | None = None) -> str:
    """Tekstiline insight ühe trenni kohta (workout_analysis + format_insight)."""
    return format_insight(workout_analysis(conn, workout_id, sess_cache))


def _equip_name(e):
    return {"trx": "TRX", "machine": "masin", "cable": "kaabel",
            "barbell": "kang", "dumbbell": "hantlid",
            "bodyweight": "kehakaal", "cardio": "kardio"}.get(e, e or "?")


if __name__ == "__main__":
    conn = get_db()
    cache = build_session_cache(conn)
    print("=== Harjutuste staatus ===")
    statuses = analyze_all_exercises(conn, cache)
    for name, info in sorted(statuses.items(), key=lambda x: x[1]["muscle"]):
        em = STATUS_EMOJI.get(info["status"], "")
        print(f"  {em} {name} [{info['muscle']}]: {info['status']} "
              f"({info['sessions']} sessiooni, {info['equipment']})")
    print(f"\n=== Lihasgrupi tasakaal ({'–'.join(balance_window(conn))}) ===")
    for mg, vol in muscle_balance(conn).items():
        print(f"  {mg}: {vol:.0f} kg")
    print("\n=== Mahu trend ===")
    trend, totals = volume_trend(conn)
    print(f"  {trend}")
    last = conn.execute(
        "SELECT id, date, workout_name FROM workouts ORDER BY timestamp DESC LIMIT 1").fetchone()
    print(f"\n=== Insight: {last['date']} {last['workout_name']} ===")
    print(workout_insight(conn, last["id"], cache))
    conn.close()
