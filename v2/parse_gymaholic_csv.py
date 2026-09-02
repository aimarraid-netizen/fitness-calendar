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
    - rep-vahemikud inline (N;6-10 reps) -> exercises tabel; ESIMENE rep-mustrile
      vastav N;-rida võidab, ülejäänud N;-read on kasutaja märkused -> sets.note
    - kaal võib olla komaga ("12,5 kg") -> 12.5; "0 kg" -> NULL (kaalu pole logitud)
    - TIME-veerg ("5:00", "1:30") -> sets.duration_sec
    - aasta puudub kuupäevast -> tuleta jooksvast
"""
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import exercise_config as cfg
from db import get_db, init_schema
from validation import ValidationError, valid_duration_sec, valid_reps, valid_weight

ROOT = Path(__file__).parent.parent
FAILED = ROOT / "data" / "failed"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# "70 kg x 6"  /  "17.5 kg x 10"  /  "12,5 kg x 15"  /  "" (cardio)
SET_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\s*x\s*(\d+)", re.IGNORECASE)
# "6-10 reps" / "20 reps" — peab algama rep-mustriga, muidu on N;-rida märkus
REP_RANGE_RE = re.compile(r"(\d+)(?:\s*-\s*(\d+))?\s*reps?\b", re.IGNORECASE)


def _parse_date(raw: str, now: datetime | None = None) -> datetime | None:
    """'May 21., 15:55' -> datetime. Aasta tuletatakse jooksvast.

    Trenn ei saa olla tulevikus: kui kuupäev jooksva aastaga oleks rohkem kui
    2 päeva ees, on tegu eelmise aasta trenniga (nt detsembri eksport jaanuaris).
    Parseerimatu kuupäev -> None (kutsuja otsustab, mitte vaikselt vale kuupäev).
    """
    now = now or datetime.now()
    raw = raw.strip()
    m = re.match(r"([A-Za-z]+)\s+(\d+)\.?,?\s*(\d+):(\d+)", raw)
    if not m:
        return None
    mon = MONTHS.get(m.group(1)[:3].lower())
    if mon is None:
        return None
    day = int(m.group(2))
    hh, mm = int(m.group(3)), int(m.group(4))
    for year in (now.year, now.year - 1):
        try:
            candidate = datetime(year, mon, day, hh, mm)
        except ValueError:  # nt 29. veebruar mitteliigaastal
            continue
        if candidate <= now + timedelta(days=2):
            return candidate
    return None


def _parse_duration(raw: str) -> int | None:
    """'0h:58m' -> minutid."""
    m = re.match(r"(\d+)h:(\d+)m", raw.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def _parse_time_cell(raw: str | None) -> int | None:
    """TIME-veerg sekunditeks: '5:00' -> 300, '1:05:00' -> 3900, ''/'0:00' -> None."""
    parts = [x.strip() for x in (raw or "").strip().split(":")]
    if not parts or not all(x.isdigit() for x in parts):
        return None
    secs = 0
    for x in parts:
        secs = secs * 60 + int(x)
    return secs or None


def _workout_type(name):
    n = (name or "").lower()
    if "trenn a" in n or "workout a" in n:
        return "jalad"
    if "trenn b" in n or "workout b" in n:
        return "selg"
    if "trenn c" in n or "workout c" in n or "kodu" in n:
        return "kodune"
    return "jõusaal"


def parse_csv(path) -> dict:
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
            current = {"name": parts[1].strip(), "rep_range": None,
                       "notes": [], "sets": []}
            exercises.append(current)
            continue
        # N;-rida: esimene rep-mustrile vastav = rep-vahemik, kõik muu = märkus
        # (nt "N;1 kaaluvihk = 2,5kg" või "N;Pulss 90-110")
        if line.startswith("N;") and current is not None:
            txt = parts[1].strip() if len(parts) > 1 else ""
            if current["rep_range"] is None and _rep_range(txt) != (None, None):
                current["rep_range"] = txt
            elif txt:
                current["notes"].append(txt)
            continue
        # seeria (algab numbriga): nr;;"70 kg x 6";TIME;REST
        if parts and parts[0].strip().isdigit() and current is not None:
            cell = parts[2] if len(parts) > 2 else ""
            duration = _parse_time_cell(parts[3] if len(parts) > 3 else "")
            sm = SET_RE.search(cell)
            if sm:
                # "0 kg" = kaalu pole logitud -> NULL, kordused jäävad alles
                weight = float(sm.group(1).replace(",", ".")) or None
                reps = int(sm.group(2))
            else:
                # cardio/aja-põhine: kaalu ega kordusi pole, ainult TIME
                weight, reps = None, None
            current["sets"].append({"reps": reps, "weight": weight,
                                    "duration": duration})
            continue

    return {"meta": meta, "exercises": exercises}


def _rep_range(raw):
    """'6-10 reps' -> (6,10); '20 reps' -> (20,20); märkus/muu -> (None,None).

    Nõuab sõna "reps" — "1 kaaluvihk = 2,5kg" EI ole rep-vahemik (1,1).
    """
    if not raw:
        return None, None
    m = REP_RANGE_RE.match(raw.strip())
    if not m:
        return None, None
    lo = int(m.group(1))
    hi = int(m.group(2) or lo)
    return lo, hi


def save_to_db(parsed: dict, conn) -> tuple[int, str, str]:
    """Kirjuta parsitud trenn SQLite-i. Idempotentne (INSERT OR IGNORE)."""
    meta = parsed["meta"]
    if meta["date"] is None:
        raise ValidationError("kuupäev puudub või on parseerimatu")
    if not parsed["exercises"]:
        raise ValidationError("ühtegi harjutust ei leitud")
    dt = meta["date"]
    timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    date = dt.strftime("%Y-%m-%d")
    wtype = _workout_type(meta["name"] or "")

    # arvuta total_volume
    total_vol = 0.0
    for ex in parsed["exercises"]:
        for s in ex["sets"]:
            if s.get("weight") and s.get("reps"):
                total_vol += s["weight"] * s["reps"]

    # Kogu kirjutus ühe transaktsioonina: viga keskel (nt pärast DELETE FROM sets)
    # ei tohi jääda avatuks, muidu commitib järgmine fail pooliku seisu.
    try:
        workout_id = _write_workout(parsed, conn, timestamp, date, wtype, total_vol)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return workout_id, date, meta["name"]


def _write_workout(parsed: dict, conn, timestamp: str, date: str,
                   wtype: str, total_vol: float) -> int:
    meta = parsed["meta"]
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
        note = "; ".join(ex.get("notes") or []) or None
        for i, s in enumerate(ex["sets"], 1):
            w = s.get("weight")
            reps = s.get("reps")
            dur = s.get("duration")
            if not valid_reps(reps) or not valid_weight(w):
                print(f"  HOIATUS: {name} seeria {i} vigane (reps={reps}, kaal={w}), "
                      "jätan vahele", file=sys.stderr)
                continue
            if not valid_duration_sec(dur):
                print(f"  HOIATUS: {name} seeria {i} kestus {dur}s ebausutav, "
                      "jätan kestuse tühjaks", file=sys.stderr)
                dur = None
            if dur is not None and cfg.is_time_based(name):
                reps = None  # hoid mõõdetakse sekundites, mitte kordustes
            vol = (w * reps) if (w and reps) else 0.0
            conn.execute(
                """INSERT INTO sets
                   (workout_id, exercise_name, set_number, reps, weight_kg,
                    equipment, total_volume, duration_sec, note)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (workout_id, name, i, reps, w, equip, vol, dur, note),
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
    return workout_id


def main():
    if len(sys.argv) < 2:
        print("Kasutamine: python parse_gymaholic_csv.py <fail.csv> [fail2.csv ...]")
        sys.exit(1)
    conn = get_db()
    init_schema(conn)
    ok = 0
    db_error = False
    for path in sys.argv[1:]:
        src = Path(path)
        try:
            parsed = parse_csv(path)
            wid, date, name = save_to_db(parsed, conn)
        except sqlite3.Error as e:
            # DB lukus / ketas täis: sisendfail on korras, ÄRA vii seda failed/-i
            print(f"✗ {src.name}: andmebaasi viga ({e}) — fail jääb kohale", file=sys.stderr)
            db_error = True
            continue
        except Exception as e:
            FAILED.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.move(str(src), str(FAILED / src.name))
            print(f"✗ {src.name}: {e} — liigutatud failed/", file=sys.stderr)
            continue
        ok += 1
        nsets = sum(len(e["sets"]) for e in parsed["exercises"])
        print(f"✓ {date} {name}: {len(parsed['exercises'])} harjutust, {nsets} seeriat (id={wid})")
    conn.close()
    if db_error:
        sys.exit(2)
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
