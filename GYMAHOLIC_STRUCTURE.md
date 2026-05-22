# Gymaholic Andmestruktuur

## 📁 Failid ZIP-is

### 1. **history.csv** - Treeningu sessioonid
```
Eraldaja: TAB
Veergud:
  - id: Sessiooni ID (34, 35, 36...)
  - workout: Programmi ID (100014, 100015, 100016)
  - name: Treeningu nimi ("1. Jalad & kõht", "2. Rind, õlg & triitseps", ...)
  - date: Kuupäev "dd.mm.yyyy, HH:MM" (nt "17.01.2026, 15:02")
  - duration: Kestus SEKUNDITES (2128 = 35min 28sek)
  - kcal: Kalorid
  - avg bpm: Keskmine pulss
  - notes: Märkmed (tavaliselt tühi)

Näide:
34	100014	1. Jalad & kõht	17.01.2026, 15:02	2128	316	135
```

### 2. **history_sets.csv** - Harjutused ja setid
```
Eraldaja: TAB
Veergud:
  - history: Sessiooni ID (viide history.csv-le)
  - exercise: Harjutuse nimi ("Barbell Squat", "Romanian Deadlift", ...)
  - muscle: Lihasgrupi ID (vt dictionaries.csv MUSCLES)
  - equipment: Vahendi ID (vt dictionaries.csv EQUIPMENTS)
  - sets: Settide arv
  - reps: Korduste arv
  - quantity: KAAL GRAMMIDES! (4000 = 4kg, 5000 = 5kg)
  - time: Aeg MILLISEKUNDITES (kasutatakse cardio puhul, 30000 = 30sek, 180000 = 3min)
  - max bpm: Maksimaalne pulss
  - avg bpm: Keskmine pulss
  - kcal: Kalorid
  - rpe: RPE (Rate of Perceived Exertion, tavaliselt 0)

Näide:
34	Barbell Squat	9	1	4	10	4000	0	147	128	73	0
  └─ Sessioon 34, Barbell Squat, 4 setti x 10 kordust, 4kg kaal

39	Barbell Bench Press	2	1	1	8	6000	0	140	112	20	0
  └─ Sessioon 39, Bench Press, 1 sett x 8 kordust, 6kg kaal
```

**OLULINE:**
- `quantity` on GRAMMIDES: jagada 1000-ga et saada kg
- `time` on MILLISEKUNDITES: jagada 1000-ga et saada sekundid
- Üks rida = üks harjutus sessionis
- Sama `history` ID-ga ridu võib olla palju (erinevad harjutused)

### 3. **dictionaries.csv** - ID-de tähendused
```
MUSCLES (lihasgrupid):
  1	Shoulder
  2	Chest
  3	Lats
  4	Triceps
  5	Biceps
  7	Abs
  9	Quads
  10	Calves
  14	Hamstrings
  16	Middle Back
  ...

EQUIPMENTS (vahendid):
  1	Barbell
  2	Dumbbell
  3	EZ bar
  4	Cable
  5	Body only
  6	Machine
  ...

MYBODY (keha mõõtmed):
  101	Weight
  ...
```

### 4. **mybody.csv** - Kehakaalu ajalugu
```
Veergud:
  - date: Kuupäev (yyyy-mm-dd)
  - type: 101 = Weight
  - value: Kaal GRAMMIDES (10000 = 100kg, 10300 = 103kg)

Näide:
2026-01-19	101	10000  ← 100kg
```

### 5. **exercises.csv** - Kohandatud harjutused
```
Tavaliselt TÜHI (kui pole loodud kohandatud harjutusi)
```

---

## 📊 Andmete töötlemise loogika

### Sessiooni tuvastamine:
1. Loe `history.csv` → iga rida on üks trenn
2. Iga trenni kohta loe `history_sets.csv` kus `history` = trenni ID
3. Arvuta MAHT: kaal (quantity/1000) × setid × kordused

### Näide: Sessioon 34
```
history.csv:
34	100014	1. Jalad & kõht	17.01.2026, 15:02	2128	316	135

history_sets.csv (history=34):
34	Barbell Squat	9	1	4	10	4000	0	147	128	73	0
   → 4kg × 4 setti × 10 kordust = 160kg maht

34	Romanian Deadlift	14	1	3	10	4000	0	161	132	64	0
   → 4kg × 3 setti × 10 kordust = 120kg maht

34	Lunge	9	5	1	20	0	0	153	138	23	0
   → kehakaalu harjutus (quantity=0)

KOKKU MAHT: 160 + 120 = 280kg
KESTUS: 2128 sek = 35min 28sek
```

---

## 🔄 Võrdlus eelmise treeninguga

**Probleem:** Gymaholic ekspordib viimased 30 päeva korraga!
- ZIP failis on 24 trenni (17.01 - 24.03.2026)
- Iga eksport sisaldab KÕIKI viimase kuu trenne
- Duplikaatide vältimine vajalik!

**Lahendus:**
1. Parsi iga sessioon eraldi (history.csv read)
2. Arvuta iga sessiooni SHA256 hash (id + date + exercises)
3. Kontrolli `logs/processed_files.log` - kui hash on olemas, jäta vahele
4. Ainult UUED sessioonid saadetakse Discordisse

---

## 📈 Progressi jälgimine

**Näited:**

### Bench Press progressioon:
```
18.01: 5kg × 3×12 + 1×6 = 210kg
27.01: 6kg × 1×8 + 1×6 + 1×4 = 108kg
03.02: [vaata history_sets.csv]
...
24.03: [viimane trenn]
```

### Jalaharjutuste võrdlus (vasak jalg vs parem):
```
Lunge - kehakaalu harjutus
→ Kontrolli kas quantity on võrdne mõlemal jalal
→ Kui puudub, märgi HOIATUS
```

---

## 🤖 Claude API prompti kontekst

Saadame iga sessiooni kohta:
```json
{
  "date": "17.01.2026",
  "workout_name": "1. Jalad & kõht",
  "duration_min": 35,
  "kcal": 316,
  "avg_hr": 135,
  "exercises": [
    {
      "name": "Barbell Squat",
      "muscle": "Quads",
      "equipment": "Barbell",
      "sets": 4,
      "reps": 10,
      "weight_kg": 4,
      "total_volume": 160
    },
    ...
  ],
  "total_volume": 280
}
```

Claude analüüsib:
- Mahumuutus vs eelmine sama nimega trenn
- PR-id (kas kaal või maht suurenes)
- Jalaharjutuste tasakaal
- Soovitused

---

## ✅ Kokkuvõte

**Kõige olulisemad:**
1. `quantity` JA `value` on **GRAMMIDES** → jaga 1000-ga!
2. `time` on **MILLISEKUNDITES** → jaga 1000-ga!
3. Kuupäev on **dd.mm.yyyy, HH:MM** formaadis
4. Üks ZIP = 30 päeva andmed (duplikaatide kontroll vajalik!)
5. Sessioonid on jagatud 3 programmiks: Jalad, Rind/Õlg, Selg/Biitseps
