"""Parsi Gymaholicu üksik-trenni CSV (semikooloniga eraldatud).

Formaat:
    ;-----------------
    ;3. Selg & biitseps
    ;-----------------
    ;Date;May 21., 15:55
    ;Duration;0h:58m
    ;KCAL;380
    ;Heart rate;113 bpm

    #;Bent Over Barbell Row;REPS;TIME;REST
    N;6-10 reps
    1;;70 kg x 6;;0:00
    2;;70 kg x 6;;0:00

Reeglid:
    - kaal JUBA kilodes (ei jaga 100-ga)
    - per-seeria pulss/kalorid puuduvad -> NULL (jõutrennis müra)
    - rep-vahemikud inline (N;6-10 reps) -> exercises tabel
    - aasta puudub kuupäevast -> tuleta jooksvast
"""
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, init_schema
import exercise_config as cfg

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "70 kg x 6"  /  "17.5 kg x 10"  /  "" (cardio)
SET_RE = re.compile(r"([\d.]+)\s*kg\s*x\s*(\d+)", re.IGNORECASE)


def _parse_date(raw, now=None):
    """'May 21., 15:55' -> datetime. Aasta tuletatakse jooksvast."""
    now = now or datetime.now()
    raw = raw.strip()
    m = re.match(r"([A-Za-z]+)\s+(\d+)\.?,?\s*(\d+):(\d+)", raw)
    if not m:
        return now
    mon = MONTHS.get(m.group(1)[:3].lower(), now.month)
    day = int(m.group(2))
    hh, mm = int(m.group(3)), int(m.group(4))
    year = now.year
    # kui kuu on tulevikus jooksva kuu suhtes -> eelmine aasta
    if mon > now.month + 1:
        year -= 1
    return datetime(year, mon, day, hh, mm)


def _parse_duration(raw):
    """'0h:58m' -> minutid."""
    m = re.match(r"(\d+)h:(\d+)m", raw.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _workout_type(name):
    n = (name or "").lower()
    if "trenn c" in n or "workout c" in n or "kodu" in n:
        return "kodune"
    return "jõusaal"


def parse_csv(path):
    """Parsi CSV -> dict (workout meta + exercises list)."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    meta = {"name": None, "date": None, "duration_min": None,
            "kcal": None, "avg_hr": None}
    exercises = []  # list of {name, rep_range, sets:[{reps,weight}]}
    current = None

    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        parts = line.split(";")

        if line.startswith(";---"):
            continue
        # trenni nimi: rida ";<nimi>" ilma teadaoleva võtmeta
        if line.startswith(";") and len(parts) == 2 and parts[1] and meta["name"] is None \
                and not parts[1].startswith("-"):
            meta["name"] = parts[1].strip()
            continue
        if line.startswith(";Date;"):
            meta["date"] = _parse_date(parts[2] if len(parts) > 2 else "")
            continue
        if line.startswith(";Duration;"):
            meta["duration_min"] = _parse_duration(parts[2] if len(parts) > 2 else "")
            continue
        if line.startswith(";KCAL;"):
            try:
                meta["kcal"] = int(parts[2])
            except (ValueError, IndexError):
                pass
            continue
        if line.startswith(";Heart rate;"):
            m = re.search(r"(\d+)", parts[2] if len(parts) > 2 else "")
            if m:
                meta["avg_hr"] = int(m.group(1))
            continue
        # uus harjutus
        if line.startswith("#;"):
            current = {"name": parts[1].strip(), "rep_range": None, "sets": []}
            exercises.append(current)
            continue
        # rep-vahemik
        if line.startswith("N;") and current is not None:
            current["rep_range"] = parts[1].strip() if len(parts) > 1 else None
            continue
        # seeria (algab numbriga)
        if parts and parts[0].strip().isdigit() and current is not None:
            # väli 3 (indeks 2) = "70 kg x 6"
            cell = parts[2] if len(parts) > 2 else ""
            sm = SET_RE.search(cell)
            if sm:
                weight = float(sm.group(1))
                reps = int(sm.group(2))
                current["sets"].append({"reps": reps, "weight": weight})
            else:
                # cardio: kaal puudub, võib olla aeg väljas 4
                time_cell = parts[3] if len(parts) > 3 else ""
                current["sets"].append({"reps": None, "weight": None,
                                        "time": time_cell.strip()})
            continue

    return {"meta": meta, "exercises": exercises}


def _rep_range(raw):
    """'6-10 reps' -> (6,10); '20 reps' -> (20,20); muu -> (None,None)."""
    if not raw:
        return None, None
    m = re.match(r"(\d+)\s*-\s*(\d+)", raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"(\d+)", raw)
    if m:
        return int(m.group(1)), int(m.group(1))
    return None, None


def save_to_db(parsed, conn):
    """Kirjuta parsitud trenn SQLite-i. Idempotentne (INSERT OR IGNORE)."""
    meta = parsed["meta"]
    dt = meta["date"] or datetime.now()
    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    date = dt.strftime("%Y-%m-%d")
    wtype = _workout_type(meta["name"] or "")

    # arvuta total_volume
    total_vol = 0.0
    for ex in parsed["exercises"]:
        for s in ex["sets"]:
            if s.get("weight") and s.get("reps"):
                total_vol += s["weight"] * s["reps"]

    cur = conn.execute(
        """INSERT OR IGNORE INTO workouts
           (timestamp, date, workout_name, workout_type, duration_min,
            total_volume, avg_hr, kcal, source)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (timestamp, date, meta["name"], wtype, meta["duration_min"],
         total_vol, meta["avg_hr"], meta["kcal"], "gymaholic_csv"),
    )
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT id FROM workouts WHERE timestamp=? AND workout_name=?",
            (timestamp, meta["name"]),
        ).fetchone()
        workout_id = row["id"]
        # juba olemas -> kustuta vanad seeriad ja kirjuta uuesti (värskeim tõde)
        conn.execute("DELETE FROM sets WHERE workout_id=?", (workout_id,))
    else:
        workout_id = cur.lastrowid

    for ex in parsed["exercises"]:
        name = ex["name"]
        equip = cfg.equipment_for(name)
        for i, s in enumerate(ex["sets"], 1):
            w = s.get("weight")
            reps = s.get("reps")
            vol = (w * reps) if (w and reps) else 0.0
            conn.execute(
                """INSERT INTO sets
                   (workout_id, exercise_name, set_number, reps, weight_kg,
                    equipment, total_volume)
                   VALUES (?,?,?,?,?,?,?)""",
                (workout_id, name, i, reps, w, equip, vol),
            )
        # sünkro rep-vahemik exercises tabelisse (CSV = uusim tõde)
        rmin, rmax = _rep_range(ex.get("rep_range"))
        if rmin is not None:
            conn.execute(
                """INSERT INTO exercises (name, default_equipment, target_reps_min,
                       target_reps_max, muscle_group)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                       target_reps_min=excluded.target_reps_min,
                       target_reps_max=excluded.target_reps_max""",
                (name, equip, rmin, rmax, cfg.muscle_for(name)),
            )
    conn.commit()
    return workout_id, date, meta["name"]


def main():
    if len(sys.argv) < 2:
        print("Kasutamine: python parse_gymaholic_csv.py <fail.csv> [fail2.csv ...]")
        sys.exit(1)
    conn = get_db()
    init_schema(conn)
    for path in sys.argv[1:]:
        parsed = parse_csv(path)
        wid, date, name = save_to_db(parsed, conn)
        nsets = sum(len(e["sets"]) for e in parsed["exercises"])
        print(f"✓ {date} {name}: {len(parsed['exercises'])} harjutust, {nsets} seeriat (id={wid})")
    conn.close()


if __name__ == "__main__":
    main()
