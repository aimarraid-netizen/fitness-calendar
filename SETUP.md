# Seadistamise Samm-Sammult Juhend

## ✅ Samm 1: Installi kõik paketid

```bash
cd ~/trenn
./setup_packages.sh
```

See installeerib:
- `rclone` (Google Drive sync)
- `python3-pandas`, `python3-matplotlib` (süsteemist, ei kompileeri)
- `python3-venv` (virtual environment)
- `fitparse`, `anthropic` (venv'i pip kaudu)

**Märkus:** Kasutame `--system-site-packages` et vältida pandas kompileerimist!

---

---

## ✅ Samm 2: Seadista rclone Google Drive'iga

```bash
cd ~/trenn
./setup_rclone.sh
```

**Dialoogis:**
1. Vajuta `n` (new remote)
2. Nimi: `gdrive`
3. Storage: vali number `drive` või kirjuta `drive`
4. Google Application Client Id: vajuta Enter (jäta tühjaks)
5. OAuth Client Secret: vajuta Enter (jäta tühjaks)
6. Scope: vali `1` (Full access)
7. Service Account: vajuta Enter (jäta tühjaks)
8. Edit advanced config: `n`
9. Use auto config: `y` ← **AVANEB BRAUSER**
10. Google kontoga sisse logimine ja õiguste andmine
11. Configure as Team Drive: `n`
12. Keep this remote: `y`
13. Quit config: `q`

**Testi:**
```bash
rclone lsd gdrive:
rclone lsd gdrive:_trenni_data
```

---

## ✅ Samm 3: Loo Discord Webhook

1. Ava Discord
2. Mine oma serverisse → **Server Settings**
3. **Integrations** → **Webhooks**
4. **New Webhook** või **Create Webhook**
5. Anna nimi (nt "Trenn Bot")
6. Vali kanal kuhu sõnumid lähevad
7. **Copy Webhook URL**

Näide URL: `https://discord.com/api/webhooks/1234567890/AbCdEf...`

---

## ✅ Samm 4: Loo .env fail

```bash
cd ~/trenn
cp .env.example .env
nano .env
```

**Täida väärtused:**

```bash
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/AbCdEfGhIjKlMnOpQrStUvWxYz
RESTING_HR=62
MAX_HR=179
```

**API võtme saamiseks:**
1. Mine: https://console.anthropic.com/
2. **API Keys** → **Create Key**
3. Kopeeri võti (algab `sk-ant-`)

**Salvesta:** Ctrl+X, siis Y, siis Enter

**Turva fail:**
```bash
chmod 600 ~/trenn/.env
```

---

## ✅ Samm 5: Testi pipeline'i

### Test 1: rclone ligipääs
```bash
rclone lsd gdrive:_trenni_data
```
✓ Peaks näitama kausta sisu või "not found" kui tühi

### Test 2: Python skriptid
```bash
cd ~/trenn
source venv/bin/activate
python convert_fit.py --help 2>&1 | head -5
python analyze.py --help 2>&1 | head -5
deactivate
```

### Test 3: Käsitsi sync (dry-run)
```bash
cd ~/trenn
rclone sync gdrive:_trenni_data data/incoming/ --dry-run
```
✓ Näitab mis faile kopeeritaks

### Test 4: Täis pipeline (kui Google Drive'is on juba faile)
```bash
cd ~/trenn
./watch.sh
```

Kontrolli:
- `logs/watch.log` - üldine logi
- `logs/error.log` - vead (peaks olema tühi)
- **Discord kanal** - peaks tulema sõnum!

---

## ✅ Samm 6: Seadista automaatne käivitamine (cron)

```bash
crontab -e
```

**Esimesel korral** küsib editori - vali `nano` (tavaliselt option 1).

**Lisa faili lõppu:**
```cron
# Fitness pipeline - iga 15 minuti tagant
*/15 * * * * cd /home/aimar/trenn && /home/aimar/trenn/watch.sh >> /home/aimar/trenn/logs/watch.log 2>&1
```

**Salvesta:** Ctrl+X, siis Y, siis Enter

**Kontrolli:**
```bash
crontab -l
```

✓ Peaks näitama sinu lisatud rida

---

## 🎯 Valmis!

Pipeline töötab nüüd automaatselt:

1. **Ekspordin trenni** Gymaholic/Workoutdoor → Google Drive kausta `_trenni_data`
2. **Ootan max 15 min** (cron käivitab)
3. **Saan Discord sõnumi** analüüsiga! 💪

---

## 📊 Testimine reaalsete andmetega

1. Tee trenn Gymaholic või Workoutdoor rakenduses
2. Ekspordi (Gymaholic: Settings → Export)
3. Uploadi Google Drive kausta `_trenni_data`
4. Käivita käsitsi: `cd ~/trenn && ./watch.sh`
5. Kontrolli Discord kanalit!

---

## 🔧 Tõrkeotsing

### "ANTHROPIC_API_KEY puudub"
```bash
cat ~/trenn/.env
# Kontrolli kas võti on seal ja algab sk-ant-
```

### "rclone 'gdrive' remote puudub"
```bash
rclone listremotes
# Peaks näitama: gdrive:
```

### "Discord webhook fail"
- Kontrolli URL-i Discord settings'ist
- Testi käsitsi:
```bash
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"content": "Test sõnum!"}'
```

### "ModuleNotFoundError"
```bash
cd ~/trenn
source venv/bin/activate
pip install -r requirements.txt
```

### Logide vaatamine
```bash
# Viimased read
tail -20 ~/trenn/logs/watch.log
tail -20 ~/trenn/logs/error.log

# Reaalajas jälgimine
tail -f ~/trenn/logs/watch.log
```

---

## ❓ Abi

Kui midagi ei tööta:
1. Vaata `logs/error.log`
2. Käivita `./watch.sh` käsitsi ja vaata väljundit
3. Kontrolli `.env` faili
4. Küsi abi!
