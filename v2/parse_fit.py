"""Trenn 2.0 — FIT-faili parser → SQLite.

Toetab: kõndimine, rattasõit, ujumine, matk (walking/cycling/swimming/hiking).
Idempotentsus: sama timestamp + workout_name ei lisa duplikaati.
Kasutus:
    python3 v2/parse_fit.py <fail.fit> [--all-incoming] [--also-processed]
"""
import sys
import shutil
import os
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, init_schema

try:
    from fitparse import FitFile
except ImportError:
    print("ERROR: fitparse puudub. Käivita: pip install fitparse", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).parent.parent
INCOMING = ROOT / "data" / "incoming"
PROCESSED_FIT = ROOT / "data" / "processed" / "fit"
FAILED = ROOT / "data" / "failed"

SPORT_MAP = {
    "walking": "kõndimine",
    "cycling": "rattasõit",
    "swimming": "ujumine",
    "hiking": "matk",
    "running": "jooksmine",
    "generic": "kardio",
    "other": "kardio",
}

# Pulsitsoonid Karvonen valemiga
RESTING_HR = int(os.getenv("RESTING_HR", 62))
MAX_HR = int(os.getenv("MAX_HR", 179))


def _hr_zones():
    hrr = MAX_HR - RESTING_HR
    return {
        "z1": (RESTING_HR + int(hrr * 0.50), RESTING_HR + int(hrr * 0.60)),
        "z2": (RESTING_HR + int(hrr * 0.60), RESTING_HR + int(hrr * 0.70)),
        "z3": (RESTING_HR + int(hrr * 0.70), RESTING_HR + int(hrr * 0.80)),
        "z4": (RESTING_HR + int(hrr * 0.80), RESTING_HR + int(hrr * 0.90)),
        "z5": (RESTING_HR + int(hrr * 0.90), MAX_HR),
    }


def _get_zone(hr, zones):
    for name, (lo, hi) in zones.items():
        if lo <= hr <= hi:
            return name
    return "z1" if hr < zones["z1"][0] else "z5"


def parse_fit(fit_path: Path) -> dict | None:
    """Parsi FIT fail, tagasta dict workouts-tabeli jaoks + zone_min."""
    try:
        ff = FitFile(str(fit_path))
    except Exception as e:
        print(f"  ERROR: FIT lugemine ebaõnnestus — {e}", file=sys.stderr)
        return None

    zones = _hr_zones()
    data = {
        "timestamp": None,
        "sport": "generic",
        "duration_sec": None,
        "distance_m": None,
        "avg_hr": None,
        "max_hr_val": None,
        "kcal": None,
        "ascent_m": None,
        "avg_speed": None,
    }
    hr_samples = []

    for msg in ff.get_messages("session"):
        for f in msg:
            n, v = f.name, f.value
            if v is None:
                continue
            if n == "start_time":
                data["timestamp"] = v
            elif n == "sport":
                data["sport"] = str(v).lower()
            elif n == "total_elapsed_time":
                data["duration_sec"] = float(v)
            elif n == "total_distance":
                data["distance_m"] = float(v)
            elif n == "avg_heart_rate":
                data["avg_hr"] = int(v)
            elif n == "max_heart_rate":
                data["max_hr_val"] = int(v)
            elif n == "total_calories":
                data["kcal"] = int(v)
            elif n == "total_ascent":
                data["ascent_m"] = int(v)
            elif n == "avg_speed":
                data["avg_speed"] = float(v)

    for msg in ff.get_messages("record"):
        for f in msg:
            if f.name == "heart_rate" and f.value:
                hr_samples.append(int(f.value))

    if data["timestamp"] is None:
        data["timestamp"] = datetime.now()

    # Arvuta tsoonid
    zone_min = {z: 0.0 for z in ("z1", "z2", "z3", "z4", "z5")}
    if hr_samples and data["duration_sec"]:
        counts = {z: 0 for z in zone_min}
        for hr in hr_samples:
            counts[_get_zone(hr, zones)] += 1
        total = len(hr_samples)
        for z in counts:
            zone_min[z] = round((counts[z] / total) * (data["duration_sec"] / 60), 1)

    data["zone_min"] = zone_min
    return data


def insert_workout(conn, fit_path: Path, data: dict) -> tuple[bool, int | None]:
    """Lisa kardio-treening workouts tabelisse. Tagasta (lisati, workout_id)."""
    ts = data["timestamp"]
    if isinstance(ts, datetime):
        ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
    else:
        ts_str = str(ts)

    date_str = ts_str[:10]
    sport_et = SPORT_MAP.get(data["sport"], data["sport"])
    workout_name = fit_path.stem  # faili nimi ilma laiendita

    duration_min = int(data["duration_sec"] / 60) if data["duration_sec"] else None

    # Kontrolli duplikaati
    existing = conn.execute(
        "SELECT id FROM workouts WHERE timestamp=? AND workout_name=?",
        (ts_str, workout_name),
    ).fetchone()
    if existing:
        return False, existing["id"]

    cur = conn.execute(
        """INSERT INTO workouts
           (timestamp, date, workout_name, workout_type,
            duration_min, distance_m, avg_hr, kcal, source)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            ts_str, date_str, workout_name, sport_et,
            duration_min, data.get("distance_m"), data.get("avg_hr"),
            data.get("kcal"), "fit",
        ),
    )
    conn.commit()
    return True, cur.lastrowid


def archive_fit(fit_path: Path, ts: datetime) -> Path:
    """Liiguta FIT fail processed/fit/ alla timestamp-prefiksiga."""
    PROCESSED_FIT.mkdir(parents=True, exist_ok=True)
    ts_pfx = ts.strftime("%Y%m%d_%H%M%S") if isinstance(ts, datetime) else "unknown"
    dest = PROCESSED_FIT / f"{ts_pfx}_{fit_path.name}"
    if dest.exists():
        dest = PROCESSED_FIT / f"{ts_pfx}_{fit_path.stem}_2{fit_path.suffix}"
    shutil.move(str(fit_path), str(dest))
    return dest


def process_file(fit_path: Path, conn, archive: bool = True) -> str:
    """Parsi + impordi üks FIT fail. Tagastab: added|duplicate|failed."""
    print(f"\n📂 {fit_path.name}")
    data = parse_fit(fit_path)
    if data is None:
        FAILED.mkdir(parents=True, exist_ok=True)
        shutil.move(str(fit_path), str(FAILED / fit_path.name))
        print(f"  ✗ Parsimisveaga — liigutatud failed/")
        return "failed"

    added, wid = insert_workout(conn, fit_path, data)
    sport_et = SPORT_MAP.get(data["sport"], data["sport"])
    dist = f"{data['distance_m']/1000:.1f} km" if data.get("distance_m") else "?"
    if data.get("duration_sec"):
        mins = int(data["duration_sec"] // 60)
        dur = f"{mins//60:02d}:{mins%60:02d}" if mins >= 60 else f"{mins} min"
    else:
        dur = "?"

    if added:
        print(f"  ✓ Lisatud (id={wid}): {sport_et} | {dist} | {dur} | {data.get('avg_hr','?')} bpm")
    else:
        print(f"  ↩ Juba olemas (id={wid}), vahele jäetud")

    if archive and fit_path.exists():
        ts = data["timestamp"]
        dest = archive_fit(fit_path, ts)
        print(f"  📦 Arhiveeritud → {dest.name}")

    return "added" if added else "duplicate"


def ensure_distance_column(conn):
    """Lisa distance_m veerg workouts tabelisse kui puudub."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(workouts)")]
    if "distance_m" not in cols:
        conn.execute("ALTER TABLE workouts ADD COLUMN distance_m REAL")
        conn.commit()
        print("  ✓ Lisatud veerg: workouts.distance_m")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="FIT-failide importer Trenn 2.0 SQLite-sse")
    parser.add_argument("files", nargs="*", help="FIT failid")
    parser.add_argument("--all-incoming", action="store_true", help="Impordi kõik data/incoming/*.fit")
    parser.add_argument("--also-processed", action="store_true",
                        help="Impordi ka data/processed/fit/*.fit (ei arhiveeri)")
    args = parser.parse_args()

    conn = get_db()
    init_schema(conn)
    ensure_distance_column(conn)

    files = []
    if args.all_incoming:
        files += sorted(INCOMING.glob("*.fit"))
    if args.also_processed:
        files += sorted(PROCESSED_FIT.glob("*.fit"))
    if args.files:
        files += [Path(f) for f in args.files]

    if not files:
        parser.print_help()
        sys.exit(1)

    added = 0
    skipped = 0
    failed = 0

    for fp in files:
        archive = fp.parent != PROCESSED_FIT  # processed faile ei arhiveeri uuesti
        status = process_file(fp, conn, archive=archive)
        if status == "added":
            added += 1
        elif status == "duplicate":
            skipped += 1
        else:
            failed += 1

    print(f"\n✅ Kõik tehtud: {added} lisatud, {skipped} duplikaati, {failed} viga")
    conn.close()


if __name__ == "__main__":
    main()
