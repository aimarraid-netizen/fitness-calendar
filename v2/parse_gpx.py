"""Trenn 2.0 — GPX/XML-faili parser → SQLite.

Toetab Strava GPX eksporti (ja GPX 1.1 üldiselt).
Tunneb ka .xml laiendiga faile (Telegram ei luba .gpx, aga .xml läheb läbi).

Kasutus:
    python3 v2/parse_gpx.py <fail.gpx|fail.xml> [--all-incoming]
"""
import sys
import shutil
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, init_schema

ROOT = Path(__file__).parent.parent
INCOMING = ROOT / "data" / "incoming"
PROCESSED_GPX = ROOT / "data" / "processed" / "gpx"
FAILED = ROOT / "data" / "failed"

GPX_NS = "http://www.topografix.com/GPX/1/1"
EXT_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"

SPORT_MAP = {
    "walking": "kõndimine",
    "cycling": "rattasõit",
    "swimming": "ujumine",
    "hiking": "matk",
    "running": "jooksmine",
    "biking": "rattasõit",
    "generic": "kardio",
    "other": "kardio",
}

RESTING_HR = 62
MAX_HR = 179


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _parse_time(s):
    """ISO8601 → datetime (UTC)."""
    if not s:
        return None
    s = s.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def parse_gpx(gpx_path: Path) -> dict | None:
    """Parsi GPX fail. Tagasta dict workouts-tabeli jaoks."""
    try:
        tree = ET.parse(str(gpx_path))
    except ET.ParseError as e:
        print(f"  ERROR: XML parsimisveaga — {e}", file=sys.stderr)
        return None

    root = tree.getroot()
    ns = {"g": GPX_NS}

    trk = root.find("g:trk", ns)
    if trk is None:
        print("  ERROR: GPX-is puudub <trk> element", file=sys.stderr)
        return None

    name_el = trk.find("g:name", ns)
    type_el = trk.find("g:type", ns)
    track_name = name_el.text.strip() if name_el is not None and name_el.text else gpx_path.stem
    sport_raw = type_el.text.strip().lower() if type_el is not None and type_el.text else "generic"

    pts = root.findall(".//g:trkpt", ns)
    if not pts:
        print("  ERROR: GPX-is pole ühtegi trkpt punkti", file=sys.stderr)
        return None

    # Distants Haversine'iga
    coords = [(float(p.get("lat") or 0), float(p.get("lon") or 0)) for p in pts if p.get("lat") and p.get("lon")]
    distance_m = sum(
        _haversine(coords[i][0], coords[i][1], coords[i+1][0], coords[i+1][1])
        for i in range(len(coords) - 1)
    )

    # Aeg
    times = []
    for p in pts:
        t = p.find("g:time", ns)
        if t is not None and t.text:
            parsed = _parse_time(t.text)
            if parsed:
                times.append(parsed)

    start_time = times[0] if times else None
    end_time = times[-1] if times else None
    duration_sec = (end_time - start_time).total_seconds() if start_time and end_time else None

    # Kõrgus (tõus)
    eles = []
    for p in pts:
        e = p.find("g:ele", ns)
        if e is not None and e.text:
            try:
                eles.append(float(e.text))
            except ValueError:
                pass
    ascent_m = None
    if eles:
        ascent_m = sum(max(0, eles[i+1] - eles[i]) for i in range(len(eles)-1))

    # HR Garmin TrackPointExtension-ist
    hr_samples = []
    for p in pts:
        ext = p.find("g:extensions", ns)
        if ext is None:
            continue

        point_hr = None

        # Garmin namespace
        tpe = ext.find(f"{{{EXT_NS}}}TrackPointExtension")
        if tpe is not None:
            hr_el = tpe.find(f"{{{EXT_NS}}}hr")
            if hr_el is not None and hr_el.text:
                try:
                    point_hr = int(hr_el.text)
                except ValueError:
                    pass

        # Fallback: otsi hr tag ilma namespaceta
        if point_hr is None:
            for child in ext.iter():
                if child.tag.split("}")[-1] == "hr" and child.text:
                    try:
                        point_hr = int(child.text)
                        break
                    except ValueError:
                        pass

        if point_hr is not None:
            hr_samples.append(point_hr)

    avg_hr = round(sum(hr_samples) / len(hr_samples)) if hr_samples else None
    max_hr_val = max(hr_samples) if hr_samples else None

    return {
        "timestamp": start_time or datetime.now(),
        "sport": sport_raw,
        "track_name": track_name,
        "duration_sec": duration_sec,
        "distance_m": distance_m,
        "avg_hr": avg_hr,
        "max_hr_val": max_hr_val,
        "kcal": None,           # GPX ei kanna kaloreid
        "ascent_m": int(ascent_m) if ascent_m else None,
    }


def insert_workout(conn, gpx_path: Path, data: dict) -> tuple[bool, int | None]:
    """Lisa kardio-treening workouts tabelisse."""
    ts = data["timestamp"]
    ts_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
    date_str = ts_str[:10]
    sport_et = SPORT_MAP.get(data["sport"], data["sport"])
    workout_name = data["track_name"]
    duration_min = int(data["duration_sec"] / 60) if data.get("duration_sec") else None

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
            data.get("kcal"), "gpx",
        ),
    )
    conn.commit()
    return True, cur.lastrowid


def archive_gpx(gpx_path: Path, ts: datetime) -> Path:
    PROCESSED_GPX.mkdir(parents=True, exist_ok=True)
    ts_pfx = ts.strftime("%Y%m%d_%H%M%S")
    dest = PROCESSED_GPX / f"{ts_pfx}_{gpx_path.stem}.gpx"
    if dest.exists():
        dest = PROCESSED_GPX / f"{ts_pfx}_{gpx_path.stem}_2.gpx"
    shutil.move(str(gpx_path), str(dest))
    return dest


def process_file(gpx_path: Path, conn, archive: bool = True) -> str:
    print(f"\n📂 {gpx_path.name}")
    data = parse_gpx(gpx_path)
    if data is None:
        FAILED.mkdir(parents=True, exist_ok=True)
        shutil.move(str(gpx_path), str(FAILED / gpx_path.name))
        print("  ✗ Parsimisveaga — liigutatud failed/")
        return "failed"

    added, wid = insert_workout(conn, gpx_path, data)
    sport_et = SPORT_MAP.get(data["sport"], data["sport"])
    dist = f"{data['distance_m']/1000:.1f} km" if data.get("distance_m") else "?"
    dur = f"{int(data['duration_sec']//60)} min" if data.get("duration_sec") else "?"

    if added:
        print(f"  ✓ Lisatud (id={wid}): {sport_et} | {dist} | {dur} | {data.get('avg_hr', '?')} bpm")
    else:
        print(f"  ↩ Juba olemas (id={wid}), vahele jäetud")

    if archive and gpx_path.exists():
        dest = archive_gpx(gpx_path, data["timestamp"])
        print(f"  📦 Arhiveeritud → {dest.name}")

    return "added" if added else "duplicate"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GPX/XML-failide importer Trenn 2.0 SQLite-sse")
    parser.add_argument("files", nargs="*", help="GPX/XML failid")
    parser.add_argument("--all-incoming", action="store_true",
                        help="Impordi kõik data/incoming/*.gpx ja *.xml")
    args = parser.parse_args()

    conn = get_db()
    init_schema(conn)

    # Veendu et distance_m veerg on olemas
    cols = [r[1] for r in conn.execute("PRAGMA table_info(workouts)")]
    if "distance_m" not in cols:
        conn.execute("ALTER TABLE workouts ADD COLUMN distance_m REAL")
        conn.commit()

    files = []
    if args.all_incoming:
        files += sorted(INCOMING.glob("*.gpx"))
        files += sorted(INCOMING.glob("*.xml"))
    if args.files:
        files += [Path(f) for f in args.files]

    if not files:
        parser.print_help()
        sys.exit(1)

    added = skipped = failed = 0
    for fp in files:
        status = process_file(fp, conn)
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
