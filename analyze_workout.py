#!/home/aimar/trenn/venv/bin/python3
"""
Analüüsi iga uus treening Claude API-ga.

- Leiab trennid workout_history.json-ist + kardio CSV-dest, mille kohta
  puudub analüüs analyses.json-is, ja kutsub Claude API.
- Kogu ajalugu (fitness_knowledge.md + TREENER_INSTRUCTIONS.md) cached
  system promptis - iga järgnev trenn on odav.
- Väljund struktureeritud JSON: kokkuvõte, plusid, miinused, soovitused.
- Salvestab analyses.json-i (kalender loeb seda automaatselt).

Kasutus:
  python3 analyze_workout.py              # analüüsib kõiki uusi trenne
  python3 analyze_workout.py 2026-04-11   # ainult antud päev (taasanalüüs)
  python3 analyze_workout.py --limit 3    # analüüsib max N trenni (kulu piir)
"""

import argparse
import csv as csv_module
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent
DATA_DIR = ROOT / 'data'
HISTORY_FILE = DATA_DIR / 'workout_history.json'
CSV_DIR = DATA_DIR / 'processed' / 'csv'
ANALYSES_FILE = DATA_DIR / 'analyses.json'
KNOWLEDGE_FILE = ROOT / 'claude_project' / 'fitness_knowledge.md'
INSTRUCTIONS_FILE = ROOT / 'claude_project' / 'TREENER_INSTRUCTIONS.md'

MODEL = os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-6')

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "kokkuvote": {"type": "string", "description": "1-2 lauset treeningu kohta"},
        "plusid": {"type": "array", "items": {"type": "string"}, "description": "Mis läks hästi (0-3 punkti)"},
        "miinused": {"type": "array", "items": {"type": "string"}, "description": "Punased lipud või probleemid (0-3 punkti)"},
        "soovitused": {"type": "array", "items": {"type": "string"}, "description": "Konkreetsed soovitused järgmiseks trenniks (1-3 punkti)"},
    },
    "required": ["kokkuvote", "plusid", "miinused", "soovitused"],
    "additionalProperties": False,
}


def load_analyses():
    if ANALYSES_FILE.exists():
        with open(ANALYSES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_analyses(data):
    ANALYSES_FILE.parent.mkdir(exist_ok=True)
    with open(ANALYSES_FILE, 'w', encoding='utf-8') as f:
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
                    })
        except Exception as e:
            print(f"Viga CSV lugemisel {csv_file}: {e}", file=sys.stderr)
    return workouts


def workout_date(w):
    ts = w.get('timestamp', '') or w.get('date', '')
    return ts[:10] if ts else ''


def build_exercise_context(workout, all_workouts, history_count=5):
    """Arvuta struktureeritud kontekst iga harjutuse kohta: baseline, PR, eelmised esinemised.

    Tagastab tekstibloki, mis läheb user promptisse. Kõik numbrilised võrdlused
    tehakse siin, et Claude ei peaks neid ajaloost leidma ega hallutsineerima.
    """
    if workout.get('source') != 'gymaholic' or not workout.get('exercises'):
        return ''

    this_ts = workout.get('timestamp', '')
    earlier = [
        w for w in all_workouts
        if w.get('source') == 'gymaholic'
        and w.get('timestamp', '') < this_ts
    ]
    earlier.sort(key=lambda w: w.get('timestamp', ''), reverse=True)

    lines = ["\n## Harjutuste ajalooline kontekst (arvutatud, usalda neid fakte)"]

    seen_names = set()
    for ex in workout['exercises']:
        name = ex.get('name', '')
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        cur_weight = ex.get('weight_kg', 0)
        cur_reps = ex.get('reps', 0)
        cur_sets = ex.get('sets', 0)

        occurrences = []
        for w in earlier:
            for e in w.get('exercises', []):
                if e.get('name') == name and e.get('weight_kg', 0) > 0:
                    occurrences.append({
                        'date': workout_date(w),
                        'sets': e.get('sets', 0),
                        'reps': e.get('reps', 0),
                        'weight': e.get('weight_kg', 0),
                    })

        lines.append(f"\n### {name} (täna: {cur_sets}×{cur_reps} @ {cur_weight}kg)")

        if not occurrences:
            lines.append("- Eelmised esinemised: PUUDUB (esimene kord ajaloos)")
            continue

        baseline = occurrences[-1]
        max_weight = max(o['weight'] for o in occurrences)
        prev_pr_reps_at_max = max(
            (o['reps'] for o in occurrences if o['weight'] == max_weight),
            default=0,
        )

        is_new_max = cur_weight > max_weight
        is_new_pr_at_same_weight = (
            cur_weight == max_weight and cur_reps > prev_pr_reps_at_max
        )
        if is_new_max:
            pr_tag = f"UUS PR (eelmine max: {max_weight}kg)"
        elif is_new_pr_at_same_weight:
            pr_tag = f"UUS PR @ {cur_weight}kg (eelmine parim: {prev_pr_reps_at_max} kordust)"
        else:
            pr_tag = f"pole PR (eelmine parim: {prev_pr_reps_at_max} kordust @ {max_weight}kg)"
        lines.append(f"- PR staatus: {pr_tag}")

        bl_diff = cur_weight - baseline['weight']
        bl_pct = (bl_diff / baseline['weight'] * 100) if baseline['weight'] else 0
        lines.append(
            f"- Baseline (esimene): {baseline['sets']}×{baseline['reps']} @ {baseline['weight']}kg ({baseline['date']}) "
            f"→ muutus: {bl_diff:+.1f}kg ({bl_pct:+.0f}%)"
        )

        recent = occurrences[:history_count]
        lines.append(f"- Viimased {len(recent)} esinemist (uuemad enne):")
        for o in recent:
            lines.append(f"  - {o['date']}: {o['sets']}×{o['reps']} @ {o['weight']}kg")

        prev = occurrences[0]
        if prev['weight'] == cur_weight:
            rep_diff = cur_reps - prev['reps']
            if rep_diff > 0:
                lines.append(f"- Progress vs eelmine ({prev['date']}): +{rep_diff} kordust samal kaalul")
            elif rep_diff < 0:
                lines.append(f"- Regress vs eelmine ({prev['date']}): {rep_diff} kordust samal kaalul")
            else:
                lines.append(f"- Sama kui eelmine ({prev['date']}): {prev['sets']}×{prev['reps']} @ {prev['weight']}kg")
        else:
            wdiff = cur_weight - prev['weight']
            lines.append(
                f"- Vs eelmine ({prev['date']}): kaal {wdiff:+.1f}kg "
                f"({prev['sets']}×{prev['reps']} @ {prev['weight']}kg → {cur_sets}×{cur_reps} @ {cur_weight}kg)"
            )

    return '\n'.join(lines)


def build_cardio_context(workout, all_workouts, history_count=5):
    """Struktureeritud kontekst kardiotreeningu kohta."""
    if workout.get('source') != 'workoutdoor':
        return ''

    wtype = workout.get('workout_type', 'cardio')
    this_ts = workout.get('timestamp', '')
    earlier = [
        w for w in all_workouts
        if w.get('source') == 'workoutdoor'
        and w.get('workout_type') == wtype
        and w.get('timestamp', '') < this_ts
    ]
    earlier.sort(key=lambda w: w.get('timestamp', ''), reverse=True)

    if not earlier:
        return f"\n## Kardio kontekst\n- Esimene '{wtype}' treening ajaloos."

    lines = [f"\n## Kardio kontekst ({wtype}, arvutatud)"]
    recent = earlier[:history_count]
    lines.append(f"- Viimased {len(recent)} '{wtype}' treeningut (uuemad enne):")
    for w in recent:
        lines.append(
            f"  - {workout_date(w)}: {w.get('duration_min', 0)} min, "
            f"{w.get('distance_km', 0):.2f} km, HR {w.get('avg_hr', 0)}/{w.get('max_hr', 0)} bpm, "
            f"{w.get('kcal', 0)} kcal"
        )
    return '\n'.join(lines)


def format_workout_for_analysis(w):
    """Vormista üks treening tekstiks, mis läheb user promptisse."""
    date = workout_date(w)
    lines = [f"**Kuupäev:** {date}"]

    if w['source'] == 'gymaholic':
        lines.append(f"**Tüüp:** Jõutrenn - {w.get('workout_name', '?')}")
        lines.append(f"**Kestus:** {w.get('duration_min', w.get('duration', 0) // 60)} min")
        if w.get('total_volume'):
            lines.append(f"**Kogumaht:** {w['total_volume']:.0f} kg")
        if w.get('avg_hr'):
            lines.append(f"**Keskmine HR:** {w['avg_hr']} bpm")
        if w.get('exercises'):
            lines.append("\n**Harjutused:**")
            for ex in w['exercises']:
                name = ex.get('name', '?')
                sets = ex.get('sets', 0)
                reps = ex.get('reps', 0)
                weight = ex.get('weight_kg', 0)
                volume = ex.get('total_volume', 0)
                line = f"- {name}: {sets}×{reps}"
                if weight > 0:
                    line += f" @ {weight}kg"
                if volume > 0:
                    line += f" (maht {volume:.0f}kg)"
                lines.append(line)
        if w.get('notes', '').strip():
            lines.append(f"\n**Märkmed:** {w['notes']}")
    else:
        emoji = {'walking': '🚶', 'running': '🏃', 'cycling': '🚴', 'hiking': '⛰️', 'swimming': '🏊'}
        wtype = w.get('workout_type', 'cardio')
        lines.append(f"**Tüüp:** Kardio - {emoji.get(wtype, '🏃')} {wtype}")
        lines.append(f"**Kestus:** {w.get('duration_min', 0)} min")
        if w.get('distance_km', 0) > 0:
            lines.append(f"**Distants:** {w['distance_km']:.2f} km")
        if w.get('avg_hr'):
            lines.append(f"**Keskmine HR:** {w['avg_hr']} bpm  |  **Max HR:** {w.get('max_hr', 0)} bpm")
        if w.get('kcal'):
            lines.append(f"**Kalorid:** {w['kcal']} kcal")

    return '\n'.join(lines)


def analyze_one(client, knowledge, instructions, workout, all_workouts):
    """Kutsub Claude API ühe trenni kohta, tagastab structured dict."""
    context_block = (
        build_exercise_context(workout, all_workouts)
        if workout.get('source') == 'gymaholic'
        else build_cardio_context(workout, all_workouts)
    )
    user_msg = (
        "Analüüsi seda uut treeningut Aimari ajaloo kontekstis. "
        "Allpool on Pythonis arvutatud täpsed ajaloolised faktid (PR staatus, baseline, eelmised esinemised) "
        "- kasuta ainult neid numbreid, ära arvuta ise ega kasuta knowledge-failist numbreid. "
        "Märka progressi/regressi, anna konkreetsed soovitused.\n\n"
        + format_workout_for_analysis(workout)
        + '\n'
        + context_block
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        temperature=0,
        system=[
            {
                "type": "text",
                "text": instructions,
            },
            {
                "type": "text",
                "text": "# Täielik treeninguajalugu\n\n" + knowledge,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_msg}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": OUTPUT_SCHEMA,
            }
        },
    )

    text = next(b.text for b in response.content if b.type == "text")
    parsed = json.loads(text)

    usage = response.usage
    print(
        f"  Tokens: in={usage.input_tokens} cache_read={usage.cache_read_input_tokens} "
        f"cache_write={usage.cache_creation_input_tokens} out={usage.output_tokens}",
        file=sys.stderr,
    )
    return parsed


def format_analysis_text(parsed):
    """Vormista struktureeritud analüüs kalendri jaoks inimloetavaks."""
    parts = [parsed['kokkuvote']]
    if parsed.get('plusid'):
        parts.append("\n✅ **Plussid:**\n" + '\n'.join(f"- {p}" for p in parsed['plusid']))
    if parsed.get('miinused'):
        parts.append("\n⚠️ **Miinused:**\n" + '\n'.join(f"- {m}" for m in parsed['miinused']))
    if parsed.get('soovitused'):
        parts.append("\n🎯 **Soovitused:**\n" + '\n'.join(f"- {s}" for s in parsed['soovitused']))
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', nargs='?', help='Analüüsi ainult seda kuupäeva (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, default=10, help='Max trenne ühe jooksu kohta')
    parser.add_argument('--force', action='store_true', help='Analüüsi ka need, millel on juba analüüs')
    parser.add_argument('--since', help='Analüüsi alates kuupäevast (YYYY-MM-DD), kaasa arvatud')
    parser.add_argument('--until', help='Analüüsi kuni kuupäevani (YYYY-MM-DD), kaasa arvatud')
    args = parser.parse_args()

    if not os.getenv('ANTHROPIC_API_KEY'):
        print("ERROR: ANTHROPIC_API_KEY puudub .env-ist", file=sys.stderr)
        sys.exit(1)

    if not KNOWLEDGE_FILE.exists() or not INSTRUCTIONS_FILE.exists():
        print(f"ERROR: {KNOWLEDGE_FILE} või {INSTRUCTIONS_FILE} puudub", file=sys.stderr)
        sys.exit(1)

    knowledge = KNOWLEDGE_FILE.read_text(encoding='utf-8')
    instructions = INSTRUCTIONS_FILE.read_text(encoding='utf-8')

    all_workouts = load_gymaholic_workouts() + load_cardio_workouts()
    all_workouts.sort(key=lambda w: w.get('timestamp', ''), reverse=True)

    analyses = load_analyses()

    if args.date:
        targets = [w for w in all_workouts if workout_date(w) == args.date]
        if not targets:
            print(f"Ei leidnud treeningut kuupäeval {args.date}", file=sys.stderr)
            sys.exit(1)
        if not args.force:
            targets = [w for w in targets if w.get('timestamp') not in analyses]
    else:
        targets = [w for w in all_workouts if args.force or w.get('timestamp') not in analyses]
        if args.since:
            targets = [w for w in targets if workout_date(w) >= args.since]
        if args.until:
            targets = [w for w in targets if workout_date(w) <= args.until]

    if not targets:
        print("Kõigil treeningutel on juba analüüs olemas.")
        return

    targets = targets[:args.limit]
    print(f"Analüüsin {len(targets)} treeningut (mudel: {MODEL})...")

    client = anthropic.Anthropic()
    success = 0
    for w in targets:
        key = w.get('timestamp')
        name = w.get('workout_name') or '?'
        print(f"→ {key} {name}", file=sys.stderr)
        try:
            parsed = analyze_one(client, knowledge, instructions, w, all_workouts)
            analyses[key] = format_analysis_text(parsed)
            save_analyses(analyses)
            success += 1
        except anthropic.APIError as e:
            print(f"  API viga: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  Viga: {e}", file=sys.stderr)

    print(f"✅ {success}/{len(targets)} analüüsitud → {ANALYSES_FILE}")


if __name__ == '__main__':
    main()
