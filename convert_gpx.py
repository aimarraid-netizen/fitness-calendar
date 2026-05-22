#!/home/aimar/trenn/venv/bin/python3
"""
GPX faili konverter CSV formaati (sama skeem nagu convert_fit.py väljund).
Kasutab stdlib xml.etree.ElementTree-i (ei vaja täiendavaid sõltuvusi).
HR tsoonid arvutatakse Karvonen valemiga, kui GPX sisaldab HR extensioni.
"""

import argparse
import math
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
    from dotenv import load_dotenv
except ImportError as e:
    print(f"ERROR: Puuduvad sõltuvused: {e}", file=sys.stderr)
    sys.exit(2)


NS = {
    'gpx': 'http://www.topografix.com/GPX/1/1',
    'gpx10': 'http://www.topografix.com/GPX/1/0',
    'tpx': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v1',
    'tpx2': 'http://www.garmin.com/xmlschemas/TrackPointExtension/v2',
}


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def calculate_hr_zones(resting_hr, max_hr):
    hrr = max_hr - resting_hr
    return {
        'z1': (resting_hr + int(hrr * 0.50), resting_hr + int(hrr * 0.60)),
        'z2': (resting_hr + int(hrr * 0.60), resting_hr + int(hrr * 0.70)),
        'z3': (resting_hr + int(hrr * 0.70), resting_hr + int(hrr * 0.80)),
        'z4': (resting_hr + int(hrr * 0.80), resting_hr + int(hrr * 0.90)),
        'z5': (resting_hr + int(hrr * 0.90), max_hr),
    }


def get_zone(hr, zones):
    for name, (lo, hi) in zones.items():
        if lo <= hr <= hi:
            return name
    return 'z1' if hr < zones['z1'][0] else 'z5'


def local_name(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


def guess_activity_type(root, filename):
    """Tuvasta activity_type GPX <type> elemendist või failinime järgi."""
    for elem in root.iter():
        if local_name(elem.tag) == 'type' and elem.text:
            t = elem.text.strip().lower()
            if t:
                return t
    n = filename.lower()
    if 'hike' in n or 'matk' in n:
        return 'hiking'
    if 'run' in n or 'jook' in n:
        return 'running'
    if 'cycle' in n or 'bike' in n or 'ride' in n or 'ratas' in n:
        return 'cycling'
    if 'swim' in n or 'uju' in n:
        return 'swimming'
    return 'walking'


def parse_time(s):
    s = s.strip()
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt


def find_hr(trkpt):
    for elem in trkpt.iter():
        if local_name(elem.tag) == 'hr' and elem.text:
            try:
                return int(elem.text)
            except ValueError:
                return None
    return None


def parse_gpx(gpx_path, resting_hr, max_hr, include_hr=True,
              override_start=None, override_duration=None, override_activity=None):
    tree = ET.parse(str(gpx_path))
    root = tree.getroot()

    points = []
    for trkpt in root.iter():
        if local_name(trkpt.tag) != 'trkpt':
            continue
        try:
            lat = float(trkpt.attrib['lat'])
            lon = float(trkpt.attrib['lon'])
        except (KeyError, ValueError):
            continue
        ts = None
        for child in trkpt:
            if local_name(child.tag) == 'time' and child.text:
                try:
                    ts = parse_time(child.text)
                except ValueError:
                    ts = None
                break
        hr = find_hr(trkpt) if include_hr else None
        points.append((lat, lon, ts, hr))

    if not points:
        print("ERROR: GPX-is pole trkpt kirjeid", file=sys.stderr)
        return None

    # Kestus ja algusaeg
    times = [p[2] for p in points if p[2] is not None]
    if times:
        duration_sec = int((times[-1] - times[0]).total_seconds())
        start_ts = times[0]
    else:
        duration_sec = 0
        start_ts = datetime.now()
    if override_start is not None:
        start_ts = override_start
    if override_duration is not None:
        duration_sec = override_duration

    # Distants
    distance_m = 0.0
    for i in range(1, len(points)):
        lat1, lon1, _, _ = points[i - 1]
        lat2, lon2, _, _ = points[i]
        distance_m += haversine_m(lat1, lon1, lat2, lon2)

    # HR
    hrs = [p[3] for p in points if p[3] is not None]
    avg_hr = int(sum(hrs) / len(hrs)) if hrs else 0
    max_hr_rec = max(hrs) if hrs else 0

    zones = calculate_hr_zones(resting_hr, max_hr)
    zone_minutes = {'z1': 0.0, 'z2': 0.0, 'z3': 0.0, 'z4': 0.0, 'z5': 0.0}
    if hrs and duration_sec > 0:
        zc = {k: 0 for k in zone_minutes}
        for hr in hrs:
            zc[get_zone(hr, zones)] += 1
        total = len(hrs)
        for z in zc:
            zone_minutes[z] = round((zc[z] / total) * (duration_sec / 60), 1)

    activity = override_activity or guess_activity_type(root, gpx_path.name)
    return {
        'timestamp': start_ts,
        'activity_type': activity,
        'duration_sec': duration_sec,
        'distance_m': int(distance_m),
        'avg_hr': avg_hr,
        'max_hr': max_hr_rec,
        'calories': 0,
        'steps': 0,
        'hr_z1_min': zone_minutes['z1'],
        'hr_z2_min': zone_minutes['z2'],
        'hr_z3_min': zone_minutes['z3'],
        'hr_z4_min': zone_minutes['z4'],
        'hr_z5_min': zone_minutes['z5'],
    }


def main():
    parser = argparse.ArgumentParser(description='Konverdi GPX → CSV')
    parser.add_argument('gpx_file', help='GPX fail')
    parser.add_argument('--no-hr', action='store_true',
                        help='Ignoreeri GPX-is olevaid pulsiandmeid (nt võõra kellalt)')
    parser.add_argument('--start-time', help='Jõusta algusaeg "YYYY-MM-DD HH:MM:SS" (kui GPX-is pole <time>)')
    parser.add_argument('--duration-sec', type=int, help='Jõusta kestus sekundites (kui GPX-is pole <time>)')
    parser.add_argument('--activity-type', help='Jõusta tegevuse tüüp (hiking, walking, running, cycling, swimming)')
    args = parser.parse_args()

    gpx_path = Path(args.gpx_file)
    override_start = datetime.strptime(args.start_time, '%Y-%m-%d %H:%M:%S') if args.start_time else None
    if not gpx_path.exists():
        print(f"ERROR: Faili ei leitud: {gpx_path}", file=sys.stderr)
        sys.exit(4)
    if gpx_path.suffix.lower() != '.gpx':
        print(f"ERROR: Fail ei ole GPX formaat: {gpx_path}", file=sys.stderr)
        sys.exit(1)

    load_dotenv(Path(__file__).parent / '.env')
    try:
        resting_hr = int(os.getenv('RESTING_HR', 62))
        max_hr = int(os.getenv('MAX_HR', 179))
    except ValueError:
        print("ERROR: RESTING_HR või MAX_HR ei ole korrektne number", file=sys.stderr)
        sys.exit(1)

    print(f"Konverdin GPX faili: {gpx_path.name}" + (" (ilma HR-ita)" if args.no_hr else ""))
    data = parse_gpx(gpx_path, resting_hr, max_hr,
                     include_hr=not args.no_hr,
                     override_start=override_start,
                     override_duration=args.duration_sec,
                     override_activity=args.activity_type)
    if data is None:
        sys.exit(1)

    ts_str = data['timestamp'].strftime('%Y%m%d_%H%M%S')
    output_filename = f"{ts_str}_{gpx_path.stem}.csv"

    script_dir = Path(__file__).parent
    csv_dir = script_dir / 'data' / 'processed' / 'csv'
    gpx_archive_dir = script_dir / 'data' / 'processed' / 'gpx'
    csv_dir.mkdir(parents=True, exist_ok=True)
    gpx_archive_dir.mkdir(parents=True, exist_ok=True)

    output_path = csv_dir / output_filename
    pd.DataFrame([data]).to_csv(output_path, index=False)
    print(f"✓ CSV salvestatud: {output_path}")

    archive_path = gpx_archive_dir / f"{ts_str}_{gpx_path.name}"
    shutil.move(str(gpx_path), str(archive_path))
    print(f"✓ GPX fail arhiveeritud: {archive_path}")

    print(f"Kestus: {data['duration_sec']}s, Distants: {data['distance_m']}m, "
          f"Keskmine pulss: {data['avg_hr']}, Tüüp: {data['activity_type']}")


if __name__ == '__main__':
    main()
