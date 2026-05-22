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
    eq = cfg.DEFAULT_EQUIPMENT.get(exercise, "")
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
    elif cmd == "import":
        print(import_csv(conn, sys.argv[2]))
        regen_html()
    else:
        print(__doc__)
    conn.close()
