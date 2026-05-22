# Boundaries
You are only allowed to work inside ~/projects/trenn/ (symlink: ~/trenn/).
Do not read, touch or access anything outside of this directory.

# Architecture

Single pipeline orkestreeritud n8n-st. **Käivitusviis: Docker bind mount, MITTE SSH** — `/home/aimar/trenn` on n8n konteineris `/trenn`-na nähtav, niiet `Execute Command` node käivitab `/trenn/pipeline.sh` otse. Kui näed kuskil dokumentatsioonis "n8n → SSH → pipeline.sh", siis see on aegunud.

```
n8n Schedule Trigger (iga 15 min)
  → Execute Command: /trenn/pipeline.sh
    → flock-protected (üks instants korraga)
    → rclone sync Google Drive _trenn_input/ → data/incoming/
    → routing failipikenduse järgi:
        gym_*.zip  → restore_gymaholic.py → data/workout_history.json
        *.fit      → convert_fit.py       → data/processed/csv/
        *.gpx      → convert_gpx.py       → data/processed/gpx/
    → prepare_claude_project.py → fitness_knowledge.md → rclone → Google Drive _trenn_output/
    → generate_calendar.py → calendar.html → git push (GitHub Pages)
```

## Andmestruktuur

`data/` keskne kataloog:
- `analyses.json` — peamine andmebaas (kõik workout'id, tagasi varundatud `.bak`, `.bak2`, `.pre-migration.bak` failidesse)
- `personal_records.json` — rekordid harjutuste lõikes
- `training_strategy.json` — strateegia parameetrid
- `workout_history.json` — Gymaholic'ist taastatud sessioonid (dedup timestamp+name kombo järgi)
- `incoming/` — rclone sync sihtkoht, töötlemise input
- `processed/` — õnnestunult töödeldud failid
- `failed/` — vead (uuri logs/-s põhjust enne ümber-mängimist)
- `temp_import/` — vahelaad

`logs/processed_files.log` — SHA256 hash'id juba töödeldud failidest (deduplikatsiooniks). Pipeline ei taastöötle sama faili ka kui see uuesti `incoming/`-sse jõuab.

## Skriptid

- `pipeline.sh` — ainus orkestreerija, `flock`-iga kaitstud (paralleelse jookse vältimiseks)
- `convert_fit.py` — FIT → CSV, Karvonen HR zones (RHR, max HR `.env`-s)
- `convert_gpx.py` — GPX → CSV. **Hoiatus:** varasem bug — kirjutas tühjad HR väljad mis lõhkusid kalendri ja knowledge generaatorid (sessioon `695a6945`). Kui muudad seda, kontrolli HR välju lõpuks
- `restore_gymaholic.py` — Gymaholic ZIP → workout_history.json
- `generate_calendar.py` — HTML kalender + rclone upload + git push (`index.html` ja `calendar.html` on identsed, viimane on alias)
- `prepare_claude_project.py` — fitness_knowledge.md, rclone Google Drive'i
- `analyze_workout.py` — analüüs ühe workout'i kohta
- `save_analysis.py` — analüüsi kirjutamine andmebaasi

## Konfiguratsioon

- `.env` — rclone token, GitHub PAT, max HR, RHR (vt `.env.example`)
- `requirements.txt` — Python paketid (3 paketti, vaata faili)
- `harjutuste_vahemikud.csv` — harjutuste rep range tabel

## Output

- `index.html` / `calendar.html` — push'itud GitHub Pages'i
- `fitness_knowledge.md` — Claude Project'is kasutatav, Google Drive `_trenn_output/`-is

## Conventions

- Vasta eesti keeles
- Pipeline'i muudatused: testida käsitsi `bash pipeline.sh` käivitusega ENNE n8n workflow'sse jätmist
- Kui debug'id miks pipeline ei tee õigesti — vaata kõigepealt `logs/` (see on suur, kasuta `tail -100`), siis n8n Execution UI'd
- Enne pipeline.sh muudatusi mõtle: kas see jookseb iga 15 min — uus skript peab olema **idempotentne** (ei tee duplikaate, ei lõhu juba edukalt töödeldud andmeid)
