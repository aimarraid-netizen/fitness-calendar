# Trenn 2.0 — seadistus

> Vana voog (rclone + Google Drive + Discord webhook + watch.sh) on PENSIONIL.
> Praegune süsteem: Kratt (Discordi bot) → `data/incoming/` või `kratt_tools.py import` → SQLite → HTML → GitHub Pages.

## 1. Sõltuvused

```bash
cd ~/projects/trenn
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install -r requirements-dev.txt   # pytest + ruff (arendus)
```

## 2. .env

```bash
cp .env.example .env
```

| Võti | Kirjeldus |
|---|---|
| `RESTING_HR` / `MAX_HR` | Pulsitsoonide arvutus (Karvonen, `v2/hr_config.py`) |
| `ANTHROPIC_API_KEY` | Claude API võti (`weekly_summary.py`) |
| `CLAUDE_MODEL` | Vaikimisi `claude-sonnet-4-6` |

## 3. Andmebaas

`data/trenn.db` luuakse automaatselt esimese impordi ajal (`init_schema` + `ensure_columns`).
Enne suuri muudatusi: `cp data/trenn.db data/trenn.db.bak-$(date +%F)`.

## 4. Import

```bash
# Üksik fail (CSV/FIT/GPX/XML/ZIP) — nii kutsub ka Kratt
venv/bin/python3 v2/kratt_tools.py import fail.csv

# Või pane failid data/incoming/ ja jooksuta pipeline
bash pipeline.sh
```

Pipeline väljastab JSON-i (`{"status":"ok",...}` või `{"status":"error",...}`), mille Kratt edastab Discordi. Vigased failid liiguvad `data/failed/`.

## 5. Publitseerimine

```bash
bash smart_git_commit.sh   # commit + push -> GitHub Actions deploy't Pages'i
```

`pipeline.sh` ise EI push'i — see on teadlik valik, et import ja publitseerimine oleks lahus.

## 6. Nädala kokkuvõte

Jookseb pipeline'i sammuna 5 automaatselt (pühapäeviti, kord nädalas, kui uusi faile tuli) või käsitsi:

```bash
venv/bin/python3 weekly_summary.py --force
```

## 7. Testid

```bash
venv/bin/pytest
venv/bin/ruff check v2 tests weekly_summary.py
```

## Tõrkeotsing

- Logi: `logs/pipeline.log`; töödeldud failide hash-register: `logs/processed_files.log`
- Vigane fail → `data/failed/` + põhjus logis
- Duplikaadid: sama faili uuesti import on ohutu (UNIQUE timestamp+name, SHA256 hash skip)
