# Boundaries
You are only allowed to work inside ~/projects/trenn/.
Do not read, touch or access anything outside of this directory.

# Trenn 2.0 — Arhitektuur (ümber tehtud 2026-05-22)

**Vana n8n + rclone + Google Drive pipeline on PENSIONIL** (rclone samm eemaldatud pipeline.sh-st 2026-06-10). Uus süsteem on SQLite-põhine, Kratt orkestreerib otse Discordist.

## Andmevoog
```
Trenni järel: jaga Gymaholicu ÜKSIK-TRENNI CSV otse Discordis Kratile
  → v2/parse_gymaholic_csv.py  (parse + valideeri)
  → data/trenn.db              (SQLite, üks tõeallikas)
  → v2/render_html.py          (mobile-first HTML → site/index.html)
  → git push                   (GitHub Pages deploy'b AINULT site/ kausta)

Kardio: FIT-fail → v2/parse_fit.py
Kardio: GPX/XML → v2/parse_gpx.py

Lives trenni ajal (Kratt Discordis):
  → v2/kratt_tools.py last/history   ("mis oli eelmine bench?")
  → v2/kratt_tools.py equip/note     ("Face Pull täna masin")
```

## v2/ moodulid
- `db.py` — SQLite skeem + ühendus. **NULL-kaal ≠ 0kg** (TRX/kehakaal/puuduv)
- `exercise_config.py` — vaikevarustus, lihasgrupp iga harjutuse kohta
- `hr_config.py` — pulsitsoonid (Karvonen, RESTING_HR/MAX_HR .env-ist) — jagatud FIT+GPX parserite vahel
  (NB: `migrate.py` on eemaldatud 2026-06-10 — ühekordne JSON→SQLite migratsioon on tehtud, vanad JSON-id `backups/legacy-json-2026-06/`)
- `validation.py` — sisendpiirid (reps, kaal, pulss, distants); vigased seeriad jäetakse vahele
- `parse_gymaholic_csv.py` — üksik-trenni CSV parser (`;`-eraldatud, kaal kilodes, rep-vahemikud inline)
- `queries.py` — taaskasutatav päringukiht
- `analyze.py` — **progressioon-teadlik** analüüs (kaal↑+kordused↓=areng; varustusvahetus=neutraalne)
- `render_html.py` + `template.html` — HTML generaator (Chart.js, drill-down)
- `kratt_tools.py` — Kratti read/write CLI

## Andmebaas (data/trenn.db)
- `workouts` — sessioonid (UNIQUE timestamp+name = dedup)
- `sets` — üksikseeriad. `weight_kg=NULL` = kaalu pole logitud (EI 0.0!)
- `exercises` — vaikevarustus, rep-vahemikud, lihasgrupp
- Rekordid arvutatakse päringuga (`queries.compute_prs`), EI salvestata eraldi

## HTML väljund (mobile-first, drill-down)
📅 Kalender + Kratti koondanalüüs → 🏋️ trenn (grupeeritud read) → 📈 harjutus (Chart.js graafik)
- Grupeeritud seeriad: `3×6 · 70kg` (mitte 3 eraldi rida)
- Nutikad delta-värvid: varustusvahetus = neutraalne (mitte punane)
- Väljund `site/index.html`; `deploy.yml` publitseerib AINULT `site/` (varem kogu repo → trenn.db oli avalik)
- **`data/`, `backups/`, `claude_project/` EI ole gitis** (.gitignore) — isiklikud terviseandmed; DB varukoopia `data/trenn.db.bak-*`

## Live URL
https://aimarraid-netizen.github.io/trenn-d8b4c9a1/

## Põhiprobleemid mis lahendati
1. **Võltsregress** — Face Pull TRX↔masin enam ei näita "regressi" (NULL-kaal loogika)
2. **Topeltprogressioon** — kaal↑ + kordused↓ = areng, mitte "−4 kordust regress"
3. **Üks tõeallikas** — rekordid baasist, mitte külmunud personal_records.json
4. **Tekst ütleb mustreid** mida kasutaja ise ei näe, EI korda tabelinumbreid

## Vana süsteem
Legacy v1 skriptid on eemaldatud. Kasuta ainult `v2/` mooduleid ja `pipeline.sh` v2 voogu.

## Conventions
- Vasta eesti keeles
- Sisend = üksik-trenni CSV otse Discordi Kratile (EI Google Drive)
- Idempotentsus: sama fail 2× ei tee duplikaate (INSERT OR IGNORE + DELETE+reinsert seeriatele)
- Enne suuri muudatusi: backup data/trenn.db


## Seis 02.09.2026 ja järgmised faasid

> Kolitud koondmälust 08.09.2026.


Repo `~/projects/trenn` (public GitHub `aimarraid-netizen/trenn-d8b4c9a1`, Pages). Vana v1 (rclone/Drive/watch.sh/Discord webhook) on AMMU pensionil — ära seda enam eelda.

**Voog:** Gymaholic üksik-trenni CSV / FIT / GPX → `v2/kratt_tools.py import` → `data/trenn.db` → `site/index.html` → öine auto-push → Pages. `pipeline.sh` on de facto surnud (cron eemaldatud 13.06.2026), kustutamine ootab Faasi 2.

**Tehtud 02.09.2026 (audit + Faas 0+1, 8 commit'i, 98 testi):**
- Privaatsus: Pages deploy'b AINULT `site/` (varem kogu repo → trenn.db, fitness_knowledge.md avalikud). `data/`, `backups/`, `claude_project/` gitist väljas. `prepare_claude_project.py` ja `harjutuste_vahemikud.csv` kustutatud (isikuandmed stringides). **Git-ajalugu puhastatud `git filter-repo` + force-push (157 → 70 commit'i)** — Aimar kinnitas eraldi. Vanad SHA-d GitHubi cache'is ajutiselt.
- CI: `deploy.yml` test job (ruff + pytest) → deploy.
- Parser: teine `N;`-rida → `sets.note` (mitte rep-vahemik), koma-kaal, 0 kg → NULL, TIME → `duration_sec`, rollback, DB-viga ei liiguta faili `failed/`.
- Kardio: `to_local_iso` (UTC → Europe/Tallinn, ühtne formaat), z1–z5/ascent/max_hr salvestatakse, dedup-võti = algushetk+source, `cardio_common.py`. Backfill tehtud (`v2/fix_2026_09.py`, idempotentne, `--dry-run` DB koopial).
- Analüüs: `workout_analysis` trenni hetkeseisuga, PR-sel-hetkel, `weeks_on_plateau`, kalendrinädalad lünkadeta; JS `exDelta` kuvab payloadi (ei arvuta).

**Järgmine (Aimari prioriteedid, kinnitatud 02.09):** Faas 2 hügieen (pipeline.sh + orvud maha, 15 MB v1 logid, README/SETUP/CLAUDE.md drift, `.claude/settings.local.json` sudo-load) → **Faas 3A Kratt `today/pr/week/stuck/list/undo` + argparse + fuzzy-nimematch + import tagastab insight'i (prioriteet 1)** → Faas 3B HTML nädalavaade + mahutrend + PR-sein + hash-routing (prioriteet 2). Keharaskus ja kardio-tsoonide HTML-vaade edasi lükatud. Täisplaan + auditi leiud: `~/.claude/plans/tee-p-hjalik-levaatus-ja-cheerful-hinton.md` (sisaldab isikuandmete kirjeldust → EI reposse).

**Mitte-ilmsed faktid:**
- `~/trenn` symlink EI eksisteeri enam (CLAUDE.md mainis) → `venv/bin/pip` shebang katki, kasuta `venv/bin/python -m pip`; `weekly_summary.py:1` shebang katki.
- `~/bin/git-nightly-push.sh` teeb 02:15 `git add -A` + push KÕIGILE `~/projects` repodele → `.gitignore` on ainus kaitse; juurkausta `/*.csv /*.zip /*.fit /*.gpx` mustrid on selle vastu.
- Trenn oli suvel 2026 pausil (viimane import 15.06) — import-voog ise on OK, mitte tülikas.
- PR-sel-hetkel semantika annab progressioonifaasis ~40/45 jõutrennile 🏆 — võib hiljem kitsendada (nt ainult kaalu-PR).
- `weekly_summary.py` (Claude API) väljund ei jõua HTML-i ja skript praktiliselt ei jookse — Faas 3D.
- Isiklikud pulsinäitajad on `.env`-is (EI reposse); kood/`.env.example` kasutavad neutraalseid vaikeväärtusi.

**Why:** Ainus tõeallikas on SQLite; HTML on avalik toode, andmed ei tohi giti minna.
**How to apply:** Uue trenni-sessiooni alguses loe plaanifail; alusta Faasist 2 või 3A vastavalt Aimari soovile. Enne DB-muudatusi `cp data/trenn.db data/trenn.db.bak-$(date +%F)`. Seotud: [[project_training_strategy]], [[feedback_generated_files_timestamp]], [[aquarium-pages-pipeline]].

