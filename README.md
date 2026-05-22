# Fitness Data Pipeline

Automatiseeritud treeninguandmete töötlemine Google Drive'ist Discord kanalisse.

## Kiirjuhend

### 1. Installeeri sõltuvused

```bash
cd ~/trenn

# Python paketid
pip3 install --user -r requirements.txt

# rclone (kui puudub)
sudo apt-get install rclone
```

### 2. Seadista rclone

```bash
./setup_rclone.sh
```

Järgi juhiseid Google Drive autentimiseks.

### 3. Loo .env fail

```bash
cp .env.example .env
nano .env
```

Täida:
- `ANTHROPIC_API_KEY` - võti https://console.anthropic.com
- `DISCORD_WEBHOOK_URL` - Discord → Server Settings → Integrations → Webhooks
- `DISCORD_BOT_TOKEN` - Discord bot token (vaata DISCORD_BOT_SETUP.md)

### 4. Testi pipeline'i

```bash
# Käsitsi sync test
rclone sync gdrive:_trenni_data data/incoming/ --dry-run

# Täis pipeline test
./watch.sh
```

### 5. Seadista Discord Bot (valikuline)

Interaktiivne bot käskude jaoks (`!stats`, `!last`, jne):

```bash
# Vaata täielikku juhendit
cat DISCORD_BOT_SETUP.md

# Käivita bot
python3 bot.py
```

### 6. Seadista automaatika (cron)

```bash
crontab -e
```

Lisa rida:
```
*/15 * * * * cd /home/aimar/trenn && /home/aimar/trenn/watch.sh >> /home/aimar/trenn/logs/watch.log 2>&1
```

## Töövoog

1. ✅ Teen trenni
2. ✅ Ekspordin Gymaholic/Workoutdoor → Google Drive (`_trenni_data` kaust)
3. ✅ Cron (iga 15min) käivitab `watch.sh`
4. ✅ Pipeline sünkroniseerib, konverteerib, analüüsib
5. ✅ **Saan Discord notifikatsiooni analüüsiga!**

## Failid

- `watch.sh` - Peamine orkestrator
- `convert_fit.py` - FIT → CSV konverter (Karvonen HR tsoonid)
- `analyze.py` - Claude API analüüs + Discord posting
- `bot.py` - Discord bot interaktiivseteks käskudeks
- `setup_rclone.sh` - rclone seadistamise abiline
- `prompts/workout_analysis.md` - Claude API prompti template
- `DISCORD_BOT_SETUP.md` - Discord boti seadistamise juhend

## Andmed

- `data/incoming/` - Google Drive sync sihtkoht
- `data/processed/csv/` - Konverteeritud CSV-d
- `data/processed/fit/` - Arhiveeritud FIT failid
- `data/charts/` - Genereeritud graafikud
- `data/workout_history.json` - Treeningu ajalugu

## Logid

- `logs/watch.log` - Üldine käivitamise logi
- `logs/error.log` - Veateatised
- `logs/processed_files.log` - SHA256 hash tracking (duplikaatide vältimine)
- `logs/rclone.log` - rclone sync detailid

## Tõrkeotsing

**"ANTHROPIC_API_KEY puudub"**
→ Kontrolli `.env` faili olemasolu ja sisu

**"rclone 'gdrive' remote puudub"**
→ Käivita `./setup_rclone.sh`

**"Discord webhook ebaõnnestus"**
→ Kontrolli webhook URL-i õigsust (Discord → Integrations)

**"FIT parsing error"**
→ Fail võib olla rikutud, liigub automaatselt `data/failed/` kausta

## Tugi

Küsimuste korral vaata:
- Logi faile: `logs/`
- Plaani faili: `~/.claude/plans/optimized-greeting-koala.md`
