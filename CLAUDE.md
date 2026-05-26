# Boundaries
You are only allowed to work inside ~/projects/trenn/ (symlink: ~/trenn/).
Do not read, touch or access anything outside of this directory.

# Trenn 2.0 — Arhitektuur (ümber tehtud 2026-05-22)

**Vana n8n + rclone + Google Drive pipeline on PENSIONIL.** Uus süsteem on SQLite-põhine, Kratt orkestreerib otse Telegramist.

## Andmevoog
```
Trenni järel: jaga Gymaholicu ÜKSIK-TRENNI CSV otse Telegrami Kratile
  → v2/parse_gymaholic_csv.py  (parse + valideeri)
  → data/trenn.db              (SQLite, üks tõeallikas)
  → v2/render_html.py          (mobile-first HTML)
  → git push                   (GitHub Pages)

Kardio: FIT-fail → v2/parse_fit.py
Kardio: GPX/XML → v2/parse_gpx.py

Lives trenni ajal (Kratt Telegramis):
  → v2/kratt_tools.py last/history   ("mis oli eelmine bench?")
  → v2/kratt_tools.py equip/note     ("Face Pull täna masin")
```

## v2/ moodulid
- `db.py` — SQLite skeem + ühendus. **NULL-kaal ≠ 0kg** (TRX/kehakaal/puuduv)
- `exercise_config.py` — vaikevarustus, lihasgrupp iga harjutuse kohta
- `migrate.py` — vana JSON → SQLite (juba jooksnud, 37 trenni)
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
- `index.html` = `calendar.html` (alias), push GitHub Pages'i

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
- Sisend = üksik-trenni CSV otse Telegrami (EI Google Drive)
- Idempotentsus: sama fail 2× ei tee duplikaate (INSERT OR IGNORE + DELETE+reinsert seeriatele)
- Enne suuri muudatusi: backup data/trenn.db
