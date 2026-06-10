# Trenn 2.0 — treeningute analüüs

Gymaholicu üksik-trenni CSV + FIT/GPX kardiofailid → SQLite → mobile-first HTML → GitHub Pages.
Kratt (Discordi bot) orkestreerib: failid jõuavad `data/incoming/` kausta või otse `v2/kratt_tools.py import` kaudu.

**Live:** https://aimarraid-netizen.github.io/trenn-d8b4c9a1/

## Kiirjuhend

```bash
cd ~/projects/trenn
python3 -m venv venv
venv/bin/pip install -r requirements.txt      # + requirements-dev.txt arenduseks
cp .env.example .env                          # täida ANTHROPIC_API_KEY, RESTING_HR, MAX_HR
```

## Töövoog

1. Trenni järel: jaga Gymaholicu CSV (või FIT/GPX/ZIP) Discordis Kratile
2. Kratt: `v2/kratt_tools.py import <fail>` või fail `data/incoming/` + `bash pipeline.sh`
3. Pipeline: parse → SQLite (`data/trenn.db`) → analüüs → `index.html`
4. `smart_git_commit.sh` push'ib → GitHub Pages deploy (automaatne Actions)
5. Pühapäeviti: `weekly_summary.py` genereerib Claude API-ga nädala kokkuvõtte

## Failid

- `pipeline.sh` — v2 orkestrator (ZIP/FIT/GPX → SQLite → HTML), lukustusega, idempotentne
- `v2/parse_gymaholic_csv.py` — Gymaholic CSV parser
- `v2/parse_fit.py` / `v2/parse_gpx.py` — kardio importerid (pulsitsoonid `v2/hr_config.py`)
- `v2/analyze.py` — progressioon-teadlik analüüs
- `v2/render_html.py` + `v2/template.html` — HTML generaator
- `v2/kratt_tools.py` — Kratti read/write CLI
- `weekly_summary.py` — nädala kokkuvõte (Claude API, loeb SQLite-st)

## Testid

```bash
venv/bin/pytest
venv/bin/ruff check v2 tests weekly_summary.py
```

## Tõrkeotsing

- **"ANTHROPIC_API_KEY puudub"** → kontrolli `.env` faili
- **Parse error** → fail liigub automaatselt `data/failed/`, põhjus `logs/pipeline.log`-is
- **Pipeline JSON `status:error`** → vaata `logs/pipeline.log`; Kratt edastab vea Discordi
