#!/home/aimar/trenn/venv/bin/python3
"""
FIT faili konverter CSV formaati.
Kasutab fitparse teeki ja arvutab südametsoonid Karvonen valemiga.
"""

import sys
import os
import shutil
from datetime import datetime
from pathlib import Path

try:
    from fitparse import FitFile
    import pandas as pd
    from dotenv import load_dotenv
except ImportError as e:
    print(f"ERROR: Puuduvad sõltuvused: {e}", file=sys.stderr)
    print("Käivita: pip3 install --user -r requirements.txt", file=sys.stderr)
    sys.exit(2)


def calculate_hr_zones(resting_hr, max_hr):
    """Arvuta südametsoonid Karvonen valemiga."""
    hrr = max_hr - resting_hr  # Heart Rate Reserve

    zones = {
        'z1': (resting_hr + int(hrr * 0.50), resting_hr + int(hrr * 0.60)),
        'z2': (resting_hr + int(hrr * 0.60), resting_hr + int(hrr * 0.70)),
        'z3': (resting_hr + int(hrr * 0.70), resting_hr + int(hrr * 0.80)),
        'z4': (resting_hr + int(hrr * 0.80), resting_hr + int(hrr * 0.90)),
        'z5': (resting_hr + int(hrr * 0.90), max_hr)
    }

    return zones


def get_zone(hr, zones):
    """Määra pulssi tsoon."""
    if hr is None:
        return None

    for zone_name, (lower, upper) in zones.items():
        if lower <= hr <= upper:
            return zone_name

    if hr < zones['z1'][0]:
        return 'z1'
    return 'z5'


def parse_fit_file(fit_path, resting_hr, max_hr):
    """
    Parsi FIT fail ja ekstraheeri treeninguandmed.

    Returns:
        dict: Treeningu andmed
    """
    try:
        fitfile = FitFile(str(fit_path))
    except Exception as e:
        print(f"ERROR: FIT faili lugemine ebaõnnestus: {e}", file=sys.stderr)
        return None

    zones = calculate_hr_zones(resting_hr, max_hr)

    # Kogume andmeid
    session_data = {
        'timestamp': None,
        'activity_type': 'unknown',
        'duration_sec': 0,
        'distance_m': 0,
        'avg_hr': None,
        'max_hr': None,
        'calories': 0,
        'steps': 0,
        'hr_z1_min': 0,
        'hr_z2_min': 0,
        'hr_z3_min': 0,
        'hr_z4_min': 0,
        'hr_z5_min': 0
    }

    hr_samples = []

    # Parsi session andmed
    for record in fitfile.get_messages('session'):
        for field in record:
            if field.name == 'start_time':
                session_data['timestamp'] = field.value
            elif field.name == 'sport':
                session_data['activity_type'] = str(field.value).lower()
            elif field.name == 'total_elapsed_time':
                session_data['duration_sec'] = int(field.value)
            elif field.name == 'total_distance':
                session_data['distance_m'] = int(field.value)
            elif field.name == 'avg_heart_rate':
                session_data['avg_hr'] = int(field.value)
            elif field.name == 'max_heart_rate':
                session_data['max_hr'] = int(field.value)
            elif field.name == 'total_calories':
                session_data['calories'] = int(field.value)
            elif field.name == 'total_steps':
                session_data['steps'] = int(field.value)

    # Parsi record andmed (aegridade andmed)
    for record in fitfile.get_messages('record'):
        for field in record:
            if field.name == 'heart_rate' and field.value:
                hr_samples.append(int(field.value))

    # Arvuta tsoonide jaotus
    if hr_samples:
        zone_counts = {'z1': 0, 'z2': 0, 'z3': 0, 'z4': 0, 'z5': 0}

        for hr in hr_samples:
            zone = get_zone(hr, zones)
            if zone:
                zone_counts[zone] += 1

        # Konverteeri sekunditeks (eeldus: 1 sample = 1 sekund)
        total_samples = len(hr_samples)
        if total_samples > 0:
            for zone in zone_counts:
                session_data[f'hr_{zone}_min'] = round((zone_counts[zone] / total_samples) * (session_data['duration_sec'] / 60), 1)

    # Kui timestamp puudub, kasuta praegust aega
    if session_data['timestamp'] is None:
        session_data['timestamp'] = datetime.now()

    return session_data


def save_to_csv(data, output_path):
    """Salvesta andmed CSV faili."""
    df = pd.DataFrame([data])
    df.to_csv(output_path, index=False)
    return True


def main():
    if len(sys.argv) != 2:
        print("Kasutamine: python3 convert_fit.py <fit_fail>", file=sys.stderr)
        sys.exit(1)

    fit_path = Path(sys.argv[1])

    if not fit_path.exists():
        print(f"ERROR: Faili ei leitud: {fit_path}", file=sys.stderr)
        sys.exit(4)

    if not fit_path.suffix.lower() == '.fit':
        print(f"ERROR: Fail ei ole FIT formaat: {fit_path}", file=sys.stderr)
        sys.exit(1)

    # Laadi keskkonnamuutujad
    load_dotenv(Path(__file__).parent / '.env')

    try:
        resting_hr = int(os.getenv('RESTING_HR', 62))
        max_hr = int(os.getenv('MAX_HR', 179))
    except ValueError:
        print("ERROR: RESTING_HR või MAX_HR ei ole korrektne number", file=sys.stderr)
        sys.exit(1)

    print(f"Konverdin FIT faili: {fit_path.name}")

    # Parsi FIT fail
    data = parse_fit_file(fit_path, resting_hr, max_hr)

    if data is None:
        print("ERROR: FIT faili parsimine ebaõnnestus", file=sys.stderr)
        sys.exit(1)

    # Genereeri väljundi failinimi
    timestamp = data['timestamp'].strftime('%Y%m%d_%H%M%S')
    output_filename = f"{timestamp}_{fit_path.stem}.csv"

    # Väljundi kaustad
    script_dir = Path(__file__).parent
    csv_dir = script_dir / 'data' / 'processed' / 'csv'
    fit_archive_dir = script_dir / 'data' / 'processed' / 'fit'

    csv_dir.mkdir(parents=True, exist_ok=True)
    fit_archive_dir.mkdir(parents=True, exist_ok=True)

    output_path = csv_dir / output_filename

    # Salvesta CSV
    if save_to_csv(data, output_path):
        print(f"✓ CSV salvestatud: {output_path}")

        # Liiguta algne FIT fail arhiivi
        archive_path = fit_archive_dir / f"{timestamp}_{fit_path.name}"
        shutil.move(str(fit_path), str(archive_path))
        print(f"✓ FIT fail arhiveeritud: {archive_path}")

        print(f"Kestus: {data['duration_sec']}s, Keskmine pulss: {data['avg_hr']}, Tüüp: {data['activity_type']}")

        sys.exit(0)
    else:
        print("ERROR: CSV salvestamine ebaõnnestus", file=sys.stderr)
        sys.exit(4)


if __name__ == '__main__':
    main()
