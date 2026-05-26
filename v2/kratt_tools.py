"""Kratti tööriistad — read/write API trenni andmebaasi vastu.

Kratt kasutab neid Telegrami vestluses:
  - lives trenni ajal: get_last(), get_history() ("mis oli eelmine bench?")
  - kohe peale seeriat: set_equipment() ("Face Pull täna masin"), add_note()
  - trenni järel: import_csv() (jaga fail -> baasi -> HTML)

CLI:
  python kratt_tools.py last "Bench Press"
  python kratt_tools.py history "Face Pull" 5
  python kratt_tools.py equip "Face Pull" machine 2026-05-21
  python kratt_tools.py import fail.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db
import queries as q
import exercise_config as cfg


def get_last(conn, exercise):
    """Viimane sessioon: 'Bench Press: 67.5kg × 7 (18. mai)'."""
    sess = q.exercise_sessions(conn, exercise)
    if not sess:
        return f"{exercise}: pole andmeid"
    s = sess[-1]
    if s["work_weight"] is not None:
        val = f"{s['work_weight']}kg × {s['top_reps']}"
    else:
        val = f"{s['top_reps']} kordust" if s["top_reps"] else "—"
    eq = s.get("equipment") or cfg.DEFAULT_EQUIPMENT.get(exercise, "")
    return f"{exercise}: {val} ({s['date']}, {eq})"


def get_history(conn, exercise, n=5):
    """Viimased N sessiooni reana."""
    sess = q.exercise_sessions(conn, exercise)
    if not sess:
        return f"{exercise}: pole andmeid"
    out = [f"{exercise} (viimased {min(n,len(sess))}):"]
    for s in sess[-n:][::-1]:
        if s["work_weight"] is not None:
            val = f"{s['work_weight']}kg × {s['top_reps']}"
        else:
            val = f"{s['top_reps']} kordust" if s["top_reps"] else "—"
        out.append(f"  {s['date']}: {val} ({s['equipment']})")
    return "\n".join(out)


def set_equipment(conn, exercise, equipment, date=None):
    """Määra harjutuse varustus konkreetsel kuupäeval (või uusim sessioon).

    'Face Pull täna masin' -> set_equipment(c,'Face Pull','machine')
    """
    if date:
        n = conn.execute(
            """UPDATE sets SET equipment=? WHERE exercise_name=? AND workout_id IN
               (SELECT id FROM workouts WHERE date=?)""",
            (equipment, exercise, date),
        ).rowcount
    else:
        # uusim sessioon
        row = conn.execute(
            """SELECT w.id FROM workouts w JOIN sets s ON s.workout_id=w.id
               WHERE s.exercise_name=? ORDER BY w.timestamp DESC LIMIT 1""",
            (exercise,),
        ).fetchone()
        if not row:
            return f"{exercise}: pole andmeid"
        n = conn.execute(
            "UPDATE sets SET equipment=? WHERE exercise_name=? AND workout_id=?",
            (equipment, exercise, row["id"]),
        ).rowcount
    conn.commit()
    return f"✓ {exercise}: varustus → {equipment} ({n} seeriat uuendatud)"


def set_default_equipment(conn, exercise, equipment):
    """Püsiv vaikevarustus harjutusele (kõik tulevased + tagasiulatuvalt config)."""
    conn.execute(
        """INSERT INTO exercises (name, default_equipment, muscle_group)
           VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET default_equipment=excluded.default_equipment""",
        (exercise, equipment, cfg.muscle_for(exercise)),
    )
    conn.commit()
    return f"✓ {exercise}: püsiv vaikevarustus → {equipment}"


def set_duration(conn, exercise, seconds, date=None, sets=None):
    """Määra aja-põhise harjutuse (Plank) kestus sekundites.

    'Plank 3×1min' -> set_duration(c, 'Plank', 60) (kõik selle päeva seeriad 60s).
    sets=N -> kirjuta täpselt N seeriat (kui logimisel puudusid).
    """
    # leia sihtsessioon
    if date:
        wrow = conn.execute("SELECT id FROM workouts WHERE date=? LIMIT 1", (date,)).fetchone()
    else:
        wrow = conn.execute(
            """SELECT w.id FROM workouts w JOIN sets s ON s.workout_id=w.id
               WHERE s.exercise_name=? ORDER BY w.timestamp DESC LIMIT 1""",
            (exercise,),
        ).fetchone()
    if not wrow:
        return f"{exercise}: pole andmeid ({date or 'uusim'})"
    wid = wrow["id"]
    existing = conn.execute(
        "SELECT id FROM sets WHERE exercise_name=? AND workout_id=? ORDER BY set_number",
        (exercise, wid),
    ).fetchall()
    if sets is not None:
        # taasta täpne seeriate arv
        conn.execute("DELETE FROM sets WHERE exercise_name=? AND workout_id=?", (exercise, wid))
        for i in range(1, sets + 1):
            conn.execute(
                """INSERT INTO sets (workout_id, exercise_name, set_number, reps,
                       weight_kg, equipment, duration_sec)
                   VALUES (?,?,?,?,?,?,?)""",
                (wid, exercise, i, None, None, cfg.equipment_for(exercise), seconds),
            )
        n = sets
    else:
        n = conn.execute(
            "UPDATE sets SET duration_sec=?, reps=NULL WHERE exercise_name=? AND workout_id=?",
            (seconds, exercise, wid),
        ).rowcount
    conn.commit()
    return f"✓ {exercise}: {n}×{seconds}s kestus salvestatud"


def add_note(conn, exercise, note, date=None):
    """Lisa märkus harjutuse seeriatele (lives kontekst)."""
    if date:
        wid_clause = "(SELECT id FROM workouts WHERE date=?)"
        params = (note, exercise, date)
    else:
        row = conn.execute(
            """SELECT w.id FROM workouts w JOIN sets s ON s.workout_id=w.id
               WHERE s.exercise_name=? ORDER BY w.timestamp DESC LIMIT 1""",
            (exercise,),
        ).fetchone()
        if not row:
            return f"{exercise}: pole andmeid"
        wid_clause = "?"
        params = (note, exercise, row["id"])
    n = conn.execute(
        f"UPDATE sets SET note=? WHERE exercise_name=? AND workout_id IN ({wid_clause})"
        if date else
        "UPDATE sets SET note=? WHERE exercise_name=? AND workout_id=?",
        params,
    ).rowcount
    conn.commit()
    return f"✓ {exercise}: märkus lisatud ({n} seeriat)"


def import_csv(conn, csv_path):
    """Impordi üksik-trenni CSV ja regenereeri HTML."""
    import parse_gymaholic_csv as pc
    parsed = pc.parse_csv(csv_path)
    wid, date, name = pc.save_to_db(parsed, conn)
    return f"✓ Imporditud: {date} {name} (id={wid})"


def import_fit(conn, fit_path):
    """Impordi FIT-fail (kardio) ja regenereeri HTML."""
    import parse_fit as pf
    status = pf.process_file(Path(fit_path), conn, archive=True)
    if status == "added":
        return "✓ FIT imporditud"
    if status == "duplicate":
        return "↩ Juba olemas, vahele jäetud"
    return "❌ FIT import ebaõnnestus"


def import_gpx(conn, gpx_path):
    """Impordi GPX/XML-fail (kardio) ja regenereeri HTML."""
    import parse_gpx as pg
    status = pg.process_file(Path(gpx_path), conn, archive=True)
    if status == "added":
        return "✓ GPX imporditud"
    if status == "duplicate":
        return "↩ Juba olemas, vahele jäetud"
    return "❌ GPX import ebaõnnestus"


def import_zip(conn, zip_path):
    """Pakib ZIP lahti, impordib seest leitud .fit, .gpx ja .csv failid."""
    import zipfile, tempfile
    results = []
    with zipfile.ZipFile(zip_path) as zf:
        with tempfile.TemporaryDirectory() as tmp:
            zf.extractall(tmp)
            tmp = Path(tmp)
            fit_files = list(tmp.rglob("*.fit"))
            gpx_files = list(tmp.rglob("*.gpx"))
            xml_files = list(tmp.rglob("*.xml"))
            csv_files = list(tmp.rglob("*.csv"))
            if not any([fit_files, gpx_files, xml_files, csv_files]):
                return "❌ ZIP-is ei leitud ühtegi .fit/.gpx/.xml/.csv faili"
            for fp in fit_files:
                results.append(import_fit(conn, fp))
            for fp in gpx_files + xml_files:
                results.append(import_gpx(conn, fp))
            for fp in csv_files:
                results.append(import_csv(conn, fp))
    return "\n".join(results)


def regen_html():
    import render_html
    render_html.main()


if __name__ == "__main__":
    conn = get_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "last":
        print(get_last(conn, sys.argv[2]))
    elif cmd == "history":
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        print(get_history(conn, sys.argv[2], n))
    elif cmd == "equip":
        date = sys.argv[4] if len(sys.argv) > 4 else None
        print(set_equipment(conn, sys.argv[2], sys.argv[3], date))
    elif cmd == "default":
        print(set_default_equipment(conn, sys.argv[2], sys.argv[3]))
    elif cmd == "note":
        date = sys.argv[4] if len(sys.argv) > 4 else None
        print(add_note(conn, sys.argv[2], sys.argv[3], date))
    elif cmd == "duration":
        # duration <harjutus> <sekundid> [kuupäev] [seeriad]
        secs = int(sys.argv[3])
        date = sys.argv[4] if len(sys.argv) > 4 else None
        sets = int(sys.argv[5]) if len(sys.argv) > 5 else None
        print(set_duration(conn, sys.argv[2], secs, date, sets))
    elif cmd == "import":
        p = Path(sys.argv[2])
        if p.suffix.lower() == ".zip":
            print(import_zip(conn, p))
        elif p.suffix.lower() == ".fit":
            print(import_fit(conn, p))
        elif p.suffix.lower() in (".gpx", ".xml"):
            print(import_gpx(conn, p))
        else:
            print(import_csv(conn, p))
        regen_html()
    else:
        print(__doc__)
    conn.close()
