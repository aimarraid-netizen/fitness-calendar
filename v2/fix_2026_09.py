"""Ühekordne andmeparandus 2026-09 auditi järel. Idempotentne, --dry-run töötab DB koopial.

Sammud:
  a) exercises: Triceps Pushdown with Rope target 1–1 → 10–15 (teine N;-rida rikkus)
  b) exercise_config.sync_to_db: 'muu' → õige lihasgrupp, puuduvad harjutused sisse
  c) sets.duration_sec = 0 → NULL (NULL-doktriin kehtib ka kestusele; ~613 legacy rida)
  d) workouts.workout_type jalad/selg (gymaholic_csv) → jõusaal
  e) kardio timestamp 'YYYY-MM-DDTHH:MM:SS' (UTC) → lokaalne 'YYYY-MM-DD HH:MM:SS'
  f) --backfill-cardio: z1–z5 / ascent_m / max_hr arhiveeritud FIT+GPX failidest
     (ainult NULL-veerud, KUNAGI ei INSERT-i; vaste = lokaalne algushetk + source)
  g) kontroll

Kasutus:
    venv/bin/python v2/fix_2026_09.py --dry-run [--backfill-cardio]
    venv/bin/python v2/fix_2026_09.py [--backfill-cardio]
"""
import argparse
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import exercise_config as cfg
from cardio_common import CARDIO_SOURCES, find_existing_cardio
from db import CARDIO_COLS, DB_PATH, get_db, init_schema, to_local_iso

ROOT = Path(__file__).parent.parent
FIT_DIRS = (ROOT / "data" / "processed" / "fit", ROOT / "data" / "incoming")
GPX_DIRS = (ROOT / "data" / "processed" / "gpx", ROOT / "data" / "incoming")


def step(title):
    print(f"\n── {title}")


def fix_rep_range(conn):
    step("a) Triceps Pushdown with Rope target 1–1 → 10–15")
    cur = conn.execute(
        """UPDATE exercises SET target_reps_min=10, target_reps_max=15
           WHERE name='Triceps Pushdown with Rope' AND target_reps_max=1""")
    print(f"   {cur.rowcount} rida")


def fix_muscle_groups(conn):
    step("b) exercise_config.sync_to_db ('muu' → lihasgrupp, puuduvad sisse)")
    before = conn.execute(
        "SELECT name FROM exercises WHERE muscle_group='muu' OR muscle_group IS NULL").fetchall()
    missing = [n for n in cfg.MUSCLE_GROUP
               if not conn.execute("SELECT 1 FROM exercises WHERE name=?", (n,)).fetchone()]
    n = cfg.sync_to_db(conn)
    print(f"   'muu' oli: {[r[0] for r in before]}; puudusid: {missing}; muudetud {n} rida")
    # sets.equipment NULL → vaikevarustus configist (Flyes/Reverse Flyes/Leg Curls)
    cur = conn.execute("SELECT DISTINCT exercise_name FROM sets WHERE equipment IS NULL")
    fixed = 0
    for (name,) in cur.fetchall():
        eq = cfg.equipment_for(name)
        if eq:
            fixed += conn.execute(
                "UPDATE sets SET equipment=? WHERE exercise_name=? AND equipment IS NULL",
                (eq, name)).rowcount
    print(f"   sets.equipment NULL → vaikevarustus: {fixed} rida")


def fix_zero_duration(conn):
    step("c) sets.duration_sec = 0 → NULL")
    cur = conn.execute("UPDATE sets SET duration_sec=NULL WHERE duration_sec=0")
    print(f"   {cur.rowcount} rida")


def fix_workout_type(conn):
    step("d) workout_type jalad/selg (gymaholic_csv) → jõusaal")
    cur = conn.execute(
        """UPDATE workouts SET workout_type='jõusaal'
           WHERE source='gymaholic_csv' AND workout_type IN ('jalad','selg')""")
    print(f"   {cur.rowcount} rida")


def fix_cardio_timestamps(conn):
    step("e) kardio timestamp UTC 'T' → lokaalne 'YYYY-MM-DD HH:MM:SS'")
    rows = conn.execute(
        "SELECT id, timestamp, date, workout_name FROM workouts WHERE timestamp LIKE '%T%'"
    ).fetchall()
    for r in rows:
        new_ts = to_local_iso(datetime.fromisoformat(r["timestamp"]))
        new_date = new_ts[:10]
        flag = "" if new_date == r["date"] else f"  ⚠ kuupäev {r['date']} → {new_date}"
        print(f"   #{r['id']:>3} {r['timestamp']} → {new_ts}  {r['workout_name']}{flag}")
        conn.execute("UPDATE workouts SET timestamp=?, date=? WHERE id=?",
                     (new_ts, new_date, r["id"]))
    print(f"   {len(rows)} rida")


def backfill_cardio(conn):
    step("f) kardio backfill (z1–z5, ascent_m, max_hr) FIT/GPX failidest")
    import parse_fit
    import parse_gpx
    seen = set()
    matched = unmatched = 0
    files = [(p, parse_fit.parse_fit) for d in FIT_DIRS for p in sorted(d.glob("*.fit"))]
    files += [(p, parse_gpx.parse_gpx) for d in GPX_DIRS
              for ext in ("*.gpx", "*.xml") for p in sorted(d.glob(ext))]
    cols = list(CARDIO_COLS)
    for path, parser in files:
        data = parser(path)
        if not data or not data.get("timestamp"):
            print(f"   ✗ ei parsi: {path.name}")
            continue
        ts_str = to_local_iso(data["timestamp"])
        row = find_existing_cardio(conn, ts_str)
        if not row:
            unmatched += 1
            print(f"   ? vasteta: {path.name} ({ts_str})")
            continue
        if row["id"] in seen:
            continue  # sama trenn teisest failist (UTC/lokaal duplikaat arhiivis)
        seen.add(row["id"])
        zm = data.get("zone_min") or {}
        vals = {"z1_min": zm.get("z1"), "z2_min": zm.get("z2"), "z3_min": zm.get("z3"),
                "z4_min": zm.get("z4"), "z5_min": zm.get("z5"),
                "ascent_m": data.get("ascent_m"), "max_hr": data.get("max_hr_val")}
        sets_sql = ", ".join(f"{c}=COALESCE({c}, ?)" for c in cols)
        conn.execute(f"UPDATE workouts SET {sets_sql} WHERE id=?",
                     (*[vals[c] for c in cols], row["id"]))
        matched += 1
        print(f"   ✓ #{row['id']:>3} {ts_str}  z2={vals['z2_min']} max_hr={vals['max_hr']} "
              f"↑{vals['ascent_m']}  ← {path.name}")
    print(f"   {matched} trenni täidetud, {unmatched} faili vasteta")


def verify(conn):
    step("g) kontroll")
    checks = {
        "exercises muscle_group='muu'": "SELECT COUNT(*) FROM exercises WHERE muscle_group='muu'",
        "sets harjutused configist puudu": None,
        "workouts timestamp LIKE '%T%'": "SELECT COUNT(*) FROM workouts WHERE timestamp LIKE '%T%'",
        "kardio z2_min IS NULL":
            f"SELECT COUNT(*) FROM workouts WHERE z2_min IS NULL AND source IN {CARDIO_SOURCES}",
        "sets duration_sec=0": "SELECT COUNT(*) FROM sets WHERE duration_sec=0",
        "sets equipment IS NULL": "SELECT COUNT(*) FROM sets WHERE equipment IS NULL",
        "Triceps Pushdown target_max=1":
            "SELECT COUNT(*) FROM exercises WHERE name='Triceps Pushdown with Rope' AND target_reps_max=1",
        "gymaholic_csv type jalad/selg":
            "SELECT COUNT(*) FROM workouts WHERE source='gymaholic_csv' AND workout_type IN ('jalad','selg')",
    }
    ok = True
    for label, sql in checks.items():
        n = len(cfg.orphan_exercises(conn)) if sql is None else conn.execute(sql).fetchone()[0]
        mark = "✓" if n == 0 else "✗"
        ok &= n == 0
        print(f"   {mark} {label}: {n}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="töötab DB koopial, päris baasi ei puutu")
    ap.add_argument("--backfill-cardio", action="store_true", help="samm f (vajab fitparse't)")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    args = ap.parse_args()

    db_path = args.db
    if args.dry_run:
        tmp = Path(tempfile.mkdtemp()) / "dry.db"
        shutil.copy(db_path, tmp)
        db_path = tmp
        print(f"DRY-RUN: töötan koopial {tmp}")
    else:
        baks = sorted(db_path.parent.glob(f"{db_path.name}.bak-*"))
        if not baks:
            sys.exit(f"ABORT: varukoopiat pole ({db_path}.bak-YYYY-MM-DD). Tee: cp {db_path} {db_path}.bak-$(date +%F)")
        print(f"Varukoopia olemas: {baks[-1].name}")

    conn = get_db(db_path)
    init_schema(conn)  # lisab puuduvad kardio-veerud
    try:
        fix_rep_range(conn)
        fix_muscle_groups(conn)
        fix_zero_duration(conn)
        fix_workout_type(conn)
        fix_cardio_timestamps(conn)
        if args.backfill_cardio:
            backfill_cardio(conn)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    ok = verify(conn)
    conn.close()
    print("\n" + ("✅ kõik kontrollid läbitud" if ok else "⚠ mõni kontroll ei läbinud (vt üleval)"))
    if args.dry_run:
        print("(dry-run — päris baas puutumata)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
