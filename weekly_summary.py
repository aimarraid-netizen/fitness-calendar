#!/home/aimar/trenn/venv/bin/python3
"""
Nädala kokkuvõte pühapäevati.

- Kui täna on pühapäev (või --force), vaatab viimase 7 päeva trenne
  (jõud + kardio) ning kutsub Claude API ühekordse nädala-kokkuvõtte
  genereerimiseks.
- Hindab jõud/kardio tasakaalu, Z2 aega, baseline-progressi, punaseid lippe.
- Salvestab week_summaries.json-i (võti: pühapäeva kuupäev YYYY-MM-DD).
- Kalender võib seda näidata eraldi (TODO).

Kasutus:
  python3 weekly_summary.py           # ainult kui täna on pühapäev
  python3 weekly_summary.py --force   # sõltumata nädalapäevast
  python3 weekly_summary.py 2026-04-12  # konkreetne pühapäev (taasanalüüs)
"""

import argparse
import csv as csv_module
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent
DATA_DIR = ROOT / 'data'
HISTORY_FILE = DATA_DIR / 'workout_history.json'
CSV_DIR = DATA_DIR / 'processed' / 'csv'
SUMMARIES_FILE = DATA_DIR / 'week_summaries.json'
KNOWLEDGE_FILE = ROOT / 'claude_project' / 'fitness_knowledge.md'
INSTRUCTIONS_FILE = ROOT / 'claude_project' / 'TREENER_INSTRUCTIONS.md'

MODEL = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "kokkuvote": {"type": "string", "description": "2-3 lauset nädala üldhinnang"},
        "tasakaal": {"type": "string", "description": "Jõud vs kardio tasakaalu hinnang"},
        "z2_aeg": {"type": "string", "description": "Z2 aeg ja võrdlus eesmärgiga (≥150 min)"},
        "baseline_progress": {"type": "array", "items": {"type": "string"}, "description": "Märkimisväärsed baseline-edusammud (0-3)"},
        "punased_lipud": {"type": "array", "items": {"type": "string"}, "description": "Hoiatused, ülekoormus, regressioon (0-3)"},
        "jargmine_nadal": {"type": "array", "items": {"type": "string"}, "description": "Konkreetsed soovitused järgmiseks nädalaks (1-3)"},
    },
    "required": ["kokkuvote", "tasakaal", "z2_aeg", "baseline_progress", "punased_lipud", "jargmine_nadal"],
    "additionalProperties": False,
}


def load_summaries():
    if SUMMARIES_FILE.exists():
        with open(SUMMARIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_summaries(data):
    SUMMARIES_FILE.parent.mkdir(exist_ok=True)
    with open(SUMMARIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_gymaholic_workouts():
    if not HISTORY_FILE.exists():
        return []
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    workouts = data['workouts'] if isinstance(data, dict) and 'workouts' in data else data
    for w in workouts:
        w['source'] = 'gymaholic'
    return workouts


def load_cardio_workouts():
    workouts = []
    if not CSV_DIR.exists():
        return workouts
    for csv_file in CSV_DIR.glob('*.csv'):
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv_module.DictReader(f)
                for row in reader:
                    filename = csv_file.stem
                    workouts.append({
                        'source': 'workoutdoor',
                        'timestamp': row.get('timestamp', ''),
                        'workout_name': filename.split('_', 2)[2] if '_' in filename else 'Cardio',
                        'workout_type': row.get('activity_type', 'cardio'),
                        'duration_min': int(float(row.get('duration_sec', 0))) // 60,
                        'distance_km': float(row.get('distance_m', 0)) / 1000,
                        'avg_hr': int(float(row.get('avg_hr', 0))),
                        'max_hr': int(float(row.get('max_hr', 0))),
                        'kcal': int(float(row.get('calories', 0))),
                        'z2_min': int(float(row.get('z2_min', 0) or 0)),
                    })
        except Exception as e:
            print(f"Viga CSV lugemisel {csv_file}: {e}", file=sys.stderr)
    return workouts


def workout_date(w):
    ts = w.get('timestamp', '') or w.get('date', '')
    return ts[:10] if ts else ''


def format_week(workouts, week_start, week_end):
    lines = [f"**Nädal:** {week_start} kuni {week_end}\n"]
    strength = [w for w in workouts if w['source'] == 'gymaholic']
    cardio = [w for w in workouts if w['source'] == 'workoutdoor']

    lines.append(f"**Kokku:** {len(strength)} jõutrenni + {len(cardio)} kardiot = {len(workouts)} treeningut\n")

    if strength:
        lines.append("### Jõutrennid:")
        for w in sorted(strength, key=lambda x: x.get('timestamp', '')):
            date = workout_date(w)
            name = w.get('workout_name', '?')
            dur = w.get('duration_min', w.get('duration', 0) // 60)
            vol = w.get('total_volume', 0)
            top = ''
            if w.get('exercises'):
                top_exs = sorted(w['exercises'], key=lambda e: e.get('total_volume', 0), reverse=True)[:3]
                top = ' | ' + ', '.join(f"{e.get('name', '?')} {e.get('sets', 0)}×{e.get('reps', 0)}@{e.get('weight_kg', 0)}kg" for e in top_exs)
            lines.append(f"- {date} {name} ({dur}min, maht {vol:.0f}kg){top}")
        lines.append("")

    if cardio:
        lines.append("### Kardio:")
        total_z2 = 0
        for w in sorted(cardio, key=lambda x: x.get('timestamp', '')):
            date = workout_date(w)
            wtype = w.get('workout_type', 'cardio')
            dur = w.get('duration_min', 0)
            dist = w.get('distance_km', 0)
            hr = w.get('avg_hr', 0)
            z2 = w.get('z2_min', 0)
            total_z2 += z2
            dist_str = f", {dist:.1f}km" if dist > 0 else ""
            hr_str = f", HR {hr}" if hr > 0 else ""
            z2_str = f", Z2 {z2}min" if z2 > 0 else ""
            lines.append(f"- {date} {wtype} ({dur}min{dist_str}{hr_str}{z2_str})")
        lines.append(f"\n**Nädala Z2 kokku:** {total_z2} min (eesmärk ≥150 min)")

    return '\n'.join(lines)


def format_summary_text(parsed):
    parts = [f"📅 **Nädala kokkuvõte**\n\n{parsed['kokkuvote']}"]
    parts.append(f"\n⚖️ **Tasakaal:** {parsed['tasakaal']}")
    parts.append(f"\n❤️ **Z2 aeg:** {parsed['z2_aeg']}")
    if parsed.get('baseline_progress'):
        parts.append("\n📈 **Baseline progress:**\n" + '\n'.join(f"- {p}" for p in parsed['baseline_progress']))
    if parsed.get('punased_lipud'):
        parts.append("\n🚩 **Punased lipud:**\n" + '\n'.join(f"- {p}" for p in parsed['punased_lipud']))
    if parsed.get('jargmine_nadal'):
        parts.append("\n🎯 **Järgmine nädal:**\n" + '\n'.join(f"- {p}" for p in parsed['jargmine_nadal']))
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('sunday', nargs='?', help='Pühapäeva kuupäev (YYYY-MM-DD), vaikimisi täna')
    parser.add_argument('--force', action='store_true', help='Jookse ka kui täna pole pühapäev')
    args = parser.parse_args()

    if args.sunday:
        end = datetime.strptime(args.sunday, '%Y-%m-%d').date()
    else:
        end = datetime.now().date()
        if end.weekday() != 6 and not args.force:
            print(f"Täna pole pühapäev ({end.strftime('%A')}). Kasuta --force kui tahad.", file=sys.stderr)
            return

    start = end - timedelta(days=6)
    week_key = end.strftime('%Y-%m-%d')

    if not os.getenv('ANTHROPIC_API_KEY'):
        print("ERROR: ANTHROPIC_API_KEY puudub .env-ist", file=sys.stderr)
        sys.exit(1)

    if not KNOWLEDGE_FILE.exists() or not INSTRUCTIONS_FILE.exists():
        print(f"ERROR: {KNOWLEDGE_FILE} või {INSTRUCTIONS_FILE} puudub", file=sys.stderr)
        sys.exit(1)

    knowledge = KNOWLEDGE_FILE.read_text(encoding='utf-8')
    instructions = INSTRUCTIONS_FILE.read_text(encoding='utf-8')

    all_workouts = load_gymaholic_workouts() + load_cardio_workouts()
    start_str = start.strftime('%Y-%m-%d')
    end_str = end.strftime('%Y-%m-%d')
    week_workouts = [w for w in all_workouts if start_str <= workout_date(w) <= end_str]

    if not week_workouts:
        print(f"Nädalal {start_str} – {end_str} trenne ei leidnud.")
        return

    print(f"Analüüsin nädalat {start_str} – {end_str} ({len(week_workouts)} trenni, mudel: {MODEL})...")

    user_msg = (
        "Anna ülevaade Aimari möödunud nädalast. Vaata jõud+kardio tasakaalu, "
        "Z2 aega (eesmärk ≥150 min), baseline-progressi harjutustes ja punaseid lippe. "
        "Võrdle eelmiste nädalatega (ajaloos olemas).\n\n"
        + format_week(week_workouts, start_str, end_str)
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=[
            {"type": "text", "text": instructions},
            {
                "type": "text",
                "text": "# Täielik treeninguajalugu\n\n" + knowledge,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_msg}],
        output_config={
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
        },
    )

    text = next(b.text for b in response.content if b.type == "text")
    parsed = json.loads(text)

    usage = response.usage
    print(
        f"Tokens: in={usage.input_tokens} cache_read={usage.cache_read_input_tokens} "
        f"cache_write={usage.cache_creation_input_tokens} out={usage.output_tokens}",
        file=sys.stderr,
    )

    summaries = load_summaries()
    summaries[week_key] = format_summary_text(parsed)
    save_summaries(summaries)

    print(f"✅ Nädala kokkuvõte salvestatud → {SUMMARIES_FILE} (võti: {week_key})")


if __name__ == '__main__':
    main()
