#!/home/aimar/trenn/venv/bin/python3
"""
Salvesta treeningu analüüs JSON faili.
Kasutus: echo "analüüsi tekst" | python3 save_analysis.py 2026-04-11
"""

import json
import sys
from pathlib import Path

ANALYSES_FILE = Path(__file__).parent / 'data' / 'analyses.json'

def main():
    if len(sys.argv) != 2:
        print("Kasutus: echo 'tekst' | python3 save_analysis.py YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    date = sys.argv[1]
    analysis = sys.stdin.read().strip()

    if not analysis:
        print("ERROR: tühi analüüs", file=sys.stderr)
        sys.exit(1)

    # Lae olemasolevad
    data = {}
    if ANALYSES_FILE.exists():
        with open(ANALYSES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

    # Lisa/uuenda
    data[date] = analysis

    # Salvesta
    with open(ANALYSES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"OK: analüüs salvestatud ({date})")

if __name__ == '__main__':
    main()
