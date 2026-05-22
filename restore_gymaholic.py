#!/home/aimar/trenn/venv/bin/python3
"""
Taasta Gymaholic andmed ilma Discord postitamiseta.
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / 'data'
HISTORY_FILE = DATA_DIR / 'workout_history.json'

def parse_gymaholic_export(export_dir):
    """Parsi Gymaholic ekspordi kataloog"""
    export_path = Path(export_dir)

    history_file = export_path / 'history.csv'
    sets_file = export_path / 'history_sets.csv'

    if not history_file.exists() or not sets_file.exists():
        print(f"ERROR: Failid puuduvad: {export_path}")
        return []

    # Lae failid
    history_df = pd.read_csv(history_file, sep='\t')
    sets_df = pd.read_csv(sets_file, sep='\t')

    sessions = []

    for idx, hist_row in history_df.iterrows():
        session_id = hist_row['id']

        # Parsi kuupäev
        date_str = str(hist_row['date'])
        try:
            workout_datetime = datetime.strptime(date_str, '%d.%m.%Y, %H:%M')
        except:
            workout_datetime = datetime.now()

        # Leia harjutused
        session_sets = sets_df[sets_df['history'] == session_id]

        exercises = []
        total_volume = 0

        for _, set_row in session_sets.iterrows():
            exercise_name = str(set_row['exercise'])
            sets = int(set_row['sets'])
            reps = int(set_row['reps'])

            # DEKAGRAMMID -> KG (jaga 100-ga)
            weight_decagrams = int(set_row['quantity']) if pd.notna(set_row['quantity']) else 0
            weight_kg = weight_decagrams / 100.0

            # Kestus (sentisekundid/10ms ühikud -> sekundid, jaga 100-ga!)
            time_centisec = int(set_row['time']) if pd.notna(set_row['time']) else 0
            duration_sec = time_centisec / 100.0

            # Pulss
            max_hr = int(set_row['max bpm']) if pd.notna(set_row['max bpm']) else 0
            avg_hr = int(set_row['avg bpm']) if pd.notna(set_row['avg bpm']) else 0

            # Kalorid
            kcal = int(set_row['kcal']) if pd.notna(set_row['kcal']) else 0

            volume = sets * reps * weight_kg
            total_volume += volume

            exercises.append({
                'name': exercise_name,
                'sets': sets,
                'reps': reps,
                'weight_kg': weight_kg,
                'total_volume': volume,
                'duration_sec': duration_sec,
                'max_hr': max_hr,
                'avg_hr': avg_hr,
                'kcal': kcal
            })

        # Määra workout type nime järgi
        workout_name = str(hist_row.get('name', 'Treening'))
        if 'jalad' in workout_name.lower() or 'kõht' in workout_name.lower():
            workout_type = 'jalad'
        elif 'rind' in workout_name.lower() or 'triitseps' in workout_name.lower():
            workout_type = 'rind'
        elif 'selg' in workout_name.lower() or 'biitseps' in workout_name.lower():
            workout_type = 'selg'
        else:
            workout_type = 'strength'

        session = {
            'timestamp': workout_datetime.isoformat().replace('T', ' '),
            'date': workout_datetime.strftime('%Y-%m-%d'),
            'workout_name': workout_name,
            'workout_type': workout_type,
            'duration_min': int(hist_row.get('duration', 0)) // 60,  # Sekundid -> minutid
            'total_volume': total_volume,
            'exercises': exercises,
            'notes': str(hist_row.get('note', '')) if pd.notna(hist_row.get('note')) else '',
            'avg_hr': int(hist_row.get('avgHeartRate', 0)) if pd.notna(hist_row.get('avgHeartRate')) else 0,
            'source': 'gymaholic'
        }

        sessions.append(session)

    return sessions


def main():
    import sys

    if len(sys.argv) < 2:
        print("Kasutamine: python restore_gymaholic.py <gymexport_dir1> [gymexport_dir2] ...")
        sys.exit(1)

    # workout_history.json sisaldab AINULT Gymaholic jõusaalitrenne.
    # Kardio (FIT/GPX) elab eraldi data/processed/csv/ all.
    history = {'workouts': []}

    all_gym_sessions = []

    # Töötlen kõiki kaustasid
    for export_dir in sys.argv[1:]:
        print(f"\nTöötlen: {export_dir}")
        sessions = parse_gymaholic_export(export_dir)
        print(f"  Leitud: {len(sessions)} sessiooni")
        all_gym_sessions.extend(sessions)

    # Eemalda duplikaadid (võrdlen timestamp ja workout_name järgi)
    unique_sessions = []
    seen = set()

    for session in all_gym_sessions:
        key = (session['timestamp'], session['workout_name'])
        if key not in seen:
            seen.add(key)
            unique_sessions.append(session)

    print(f"\n✓ Unikaalseid sessioone: {len(unique_sessions)}")

    history['workouts'] = unique_sessions
    history['last_updated'] = datetime.now().isoformat()

    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Salvestatud workout_history.json")
    print(f"   Jõusaal: {len(unique_sessions)}")


if __name__ == '__main__':
    main()
