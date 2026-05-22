#!/home/aimar/trenn/venv/bin/python3
"""
Genereeri interaktiivne HTML kalender treeningute jaoks
"""

import json
from datetime import datetime
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).parent / 'data'
HISTORY_FILE = DATA_DIR / 'workout_history.json'
ANALYSES_FILE = DATA_DIR / 'analyses.json'
OUTPUT_FILE = Path(__file__).parent / 'calendar.html'

def load_data():
    """Lae workout_history.json ja CSV failid"""
    # Lae Gymaholic (ainult gymaholic source)
    with open(HISTORY_FILE, 'r') as f:
        data = json.load(f)
        all_workouts = data.get('workouts', [])
        gym = [w for w in all_workouts if w.get('source') == 'gymaholic']

    # Lae Workoutdoor
    import csv
    cardio = []
    csv_dir = DATA_DIR / 'processed' / 'csv'
    for csv_file in csv_dir.glob('*.csv'):
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = csv_file.stem
                duration_sec = float(row.get('duration_sec', 0))
                distance_m = float(row.get('distance_m', 0))
                duration_min = duration_sec / 60.0
                distance_km = distance_m / 1000.0
                pace_min_per_km = (duration_min / distance_km) if distance_km > 0 else 0
                speed_km_per_h = (distance_km / (duration_sec / 3600.0)) if duration_sec > 0 else 0
                pace_min_per_100m = (duration_min / (distance_m / 100.0)) if distance_m > 0 else 0
                cardio.append({
                    'source': 'workoutdoor',
                    'timestamp': row.get('timestamp', ''),
                    'date': row.get('timestamp', '').split()[0],
                    'workout_name': filename.split('_', 2)[2] if len(filename.split('_')) > 2 else 'Cardio',
                    'workout_type': row.get('activity_type', 'cardio'),
                    'duration_min': int(duration_min),
                    'distance': distance_km,
                    'avg_hr': int(float(row.get('avg_hr') or 0)),
                    'max_hr': int(float(row.get('max_hr') or 0)),
                    'kcal': int(float(row.get('calories') or 0)),
                    'pace_min_per_km': round(pace_min_per_km, 2),
                    'speed_km_per_h': round(speed_km_per_h, 2),
                    'pace_min_per_100m': round(pace_min_per_100m, 2),
                    'z2_min': float(row.get('hr_z2_min', 0) or 0),
                })

    return gym + cardio

def load_analyses():
    """Lae analüüsid JSON failist"""
    if ANALYSES_FILE.exists():
        with open(ANALYSES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def generate_html(workouts):
    """Genereeri HTML kalender"""

    # Grupeeri treeningud kuupäeva järgi
    by_date = defaultdict(list)
    for w in workouts:
        date = w.get('timestamp', w.get('date', ''))[:10]
        by_date[date].append(w)

    # Genereeri HTML
    html = """<!DOCTYPE html>
<html lang="et">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    <title>Treeningute Kalender</title>

    <!-- iOS Web App optimeeringud -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Trenn">

    <!-- Cache control - värskenda alati -->
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">

    <!-- Chart.js for progress graphs -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

    <style>
        :root {
            --bg: #0f0f0f;
            --surface: #181818;
            --surface2: #222;
            --border: #2a2a2a;
            --text: #f0f0f0;
            --text2: #b0b0b0;
            --text3: #666;
            --accent: #e0bd7a;
            --accent2: #bd9d67;
            --green: #6fc282;
            --red: #d96560;
            --blue: #6fa8d4;
            --purple: #a583ce;
            --orange: #e0a35a;
            --cyan: #6fbbbb;
            --brown: #a4866e;
            --radius: 6px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 24px;
            -webkit-font-smoothing: antialiased;
        }
        .container { max-width: 960px; margin: 0 auto; }
        .timestamp {
            text-align: right;
            font-size: 11px;
            color: var(--text3);
            margin-bottom: 16px;
            letter-spacing: 0.3px;
        }

        .month-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 12px 0;
        }
        .month-nav button {
            background: transparent;
            color: var(--text2);
            border: 1px solid var(--border);
            padding: 8px 16px;
            border-radius: var(--radius);
            cursor: pointer;
            font-size: 13px;
            letter-spacing: 0.5px;
            transition: all 0.15s;
        }
        .month-nav button:hover {
            color: var(--text);
            border-color: var(--accent);
        }
        .month-nav h2 {
            color: var(--text);
            font-size: 20px;
            font-weight: 500;
            letter-spacing: 0.5px;
        }

        .calendar {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 3px;
            margin-bottom: 24px;
        }
        .day-header {
            padding: 10px 4px;
            text-align: center;
            font-weight: 500;
            font-size: 11px;
            color: var(--text2);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .day {
            background: var(--surface);
            padding: 10px 6px;
            text-align: center;
            border-radius: var(--radius);
            min-height: 76px;
            cursor: pointer;
            transition: all 0.15s;
            border: 1px solid transparent;
            position: relative;
        }
        .day:hover {
            border-color: var(--accent);
            background: var(--surface2);
        }
        .day.empty { opacity: 0.2; cursor: default; border: none; }
        .day.empty:hover { background: var(--surface); }

        .day.gym-jalad { border-left: 3px solid var(--red); }
        .day.gym-rind { border-left: 3px solid var(--green); }
        .day.gym-selg { border-left: 3px solid var(--accent); }
        .day.walking { border-left: 3px solid var(--blue); }
        .day.running { border-left: 3px solid var(--orange); }
        .day.cycling { border-left: 3px solid var(--purple); }
        .day.hiking { border-left: 3px solid var(--brown); }
        .day.swimming { border-left: 3px solid var(--cyan); }
        .day.multi { border-left: 3px solid var(--accent); }

        .day-number {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 4px;
            color: #ffffff;
        }
        .day-name {
            font-size: 10px;
            margin-top: 3px;
            font-weight: 500;
            line-height: 1.2;
            color: var(--text2);
        }
        .day-cardio-info {
            font-size: 9px;
            margin-top: 2px;
            line-height: 1.2;
            color: var(--text3);
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.85);
            backdrop-filter: blur(4px);
            z-index: 1000;
            overflow-y: auto;
        }
        .modal.active { display: flex; align-items: center; justify-content: center; }
        .modal-content {
            background: var(--surface);
            padding: 28px;
            border-radius: 10px;
            max-width: 720px;
            width: 95%;
            max-height: 85vh;
            overflow-y: auto;
            border: 1px solid var(--border);
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 14px;
            border-bottom: 1px solid var(--border);
        }
        .modal-header h2 {
            font-weight: 500;
            font-size: 18px;
        }
        .close {
            font-size: 24px;
            cursor: pointer;
            color: var(--text3);
            width: 32px;
            height: 32px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: var(--radius);
            transition: all 0.15s;
        }
        .close:hover { color: var(--text); background: var(--surface2); }

        .workout-analysis {
            margin-top: 16px;
            padding: 16px;
            background: var(--bg);
            border-radius: var(--radius);
            border-left: 3px solid var(--purple);
        }
        .workout-analysis h3 {
            margin-bottom: 8px;
            color: var(--purple);
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }
        .analysis-text { color: var(--text2); line-height: 1.7; font-size: 14px; }

        .workout-details {
            margin-bottom: 16px;
            padding: 16px;
            background: var(--bg);
            border-radius: var(--radius);
            border-left: 3px solid var(--green);
        }
        .workout-details.cardio { border-left-color: var(--blue); }
        .workout-details h3 {
            margin-bottom: 8px;
            color: var(--text);
            font-size: 15px;
            font-weight: 500;
        }
        .workout-details p { margin: 4px 0; color: var(--text2); font-size: 14px; }

        .workout-table {
            width: 100%;
            margin-top: 12px;
            border-collapse: collapse;
            font-size: 13px;
        }
        .workout-table th {
            padding: 8px 10px;
            text-align: left;
            font-weight: 500;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text3);
            border-bottom: 1px solid var(--border);
        }
        .workout-table td {
            padding: 8px 10px;
            border-bottom: 1px solid var(--border);
            color: var(--text2);
        }
        .workout-table tr:hover td { color: var(--text); }
        .workout-table .comparison { font-size: 11px; font-weight: 600; }
        .workout-table .comparison.positive { color: var(--green); }
        .workout-table .comparison.negative { color: var(--orange); }

        /* Stats */
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
            gap: 8px;
            margin-top: 20px;
        }
        .stat-card {
            background: var(--surface);
            padding: 14px 8px;
            border-radius: var(--radius);
            text-align: center;
            border: 1px solid var(--border);
        }
        .stat-value {
            font-size: 28px;
            font-weight: 600;
            color: #ffffff;
            margin: 4px 0;
        }
        .stat-label { color: var(--text); font-size: 14px; letter-spacing: 0.3px; }

        /* Progress */
        .progress-section {
            margin-top: 24px;
            background: var(--surface);
            padding: 20px;
            border-radius: var(--radius);
            border: 1px solid var(--border);
        }
        .progress-section h3 {
            color: var(--text);
            font-size: 15px;
            font-weight: 500;
            margin-bottom: 16px;
        }
        .progress-group { margin-bottom: 20px; }
        .progress-group:last-child { margin-bottom: 0; }
        .progress-group-title {
            color: var(--text);
            font-size: 13px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
            padding-left: 6px;
            border-left: 3px solid var(--accent);
        }
        .progress-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
        .progress-item {
            background: var(--bg);
            padding: 12px 14px;
            border-radius: var(--radius);
            border-left: 2px solid var(--accent);
            display: grid;
            grid-template-columns: minmax(140px, 180px) 1fr auto;
            align-items: center;
            gap: 14px;
        }
        .progress-item .exercise-name {
            color: var(--text);
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 0.2px;
        }
        .progress-item .exercise-name .metric-unit {
            color: var(--text3);
            font-size: 11px;
            font-weight: 400;
            display: block;
            margin-top: 2px;
        }
        .progress-item .mini-chart-wrapper {
            position: relative;
            height: 70px;
            min-width: 0;
        }
        .progress-item .progress-summary {
            color: var(--text2);
            font-size: 11px;
            text-align: right;
            white-space: nowrap;
            line-height: 1.4;
        }
        .progress-item .progress-summary .trend {
            font-weight: 600;
            font-size: 13px;
        }
        .progress-item .progress-summary .trend.up { color: var(--green); }
        .progress-item .progress-summary .trend.down { color: var(--red); }
        .progress-item .progress-summary .trend.flat { color: var(--text3); }
        .progress-item .no-data {
            color: var(--text3);
            font-size: 11px;
            text-align: center;
            padding: 20px 0;
        }

        /* Mobile */
        @media (max-width: 768px) {
            body { padding: 12px; }

            .month-nav button {
                padding: 10px 14px;
                font-size: 13px;
                min-width: 70px;
                touch-action: manipulation;
            }
            .month-nav h2 { font-size: 17px; }

            .calendar { gap: 2px; margin-bottom: 16px; }
            .day-header { padding: 6px 2px; font-size: 10px; }
            .day {
                padding: 7px 3px;
                min-height: 58px;
                touch-action: manipulation;
            }
            .day-number { font-size: 13px; margin-bottom: 2px; }
            .day-name { font-size: 9px; margin-top: 2px; }
            .day-cardio-info { font-size: 8px; }

            .modal.active {
                align-items: flex-start;
                padding-top: calc(env(safe-area-inset-top, 0px) + 12px);
                padding-bottom: calc(env(safe-area-inset-bottom, 0px) + 12px);
            }
            .modal-content {
                padding: 16px;
                width: 98%;
                max-height: calc(100dvh - env(safe-area-inset-top, 0px) - env(safe-area-inset-bottom, 0px) - 24px);
                margin: 8px;
            }
            .modal-header h2 { font-size: 16px; }

            .workout-details { padding: 12px; }
            .workout-details h3 { font-size: 14px; }
            .workout-details p { font-size: 13px; }

            .workout-table {
                font-size: 11px;
                display: block;
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            .workout-table th, .workout-table td {
                padding: 6px 4px;
                font-size: 11px;
            }

            .stats {
                grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
                gap: 4px;
                margin-top: 12px;
            }
            .stat-card { padding: 10px 4px; }
            .stat-value { font-size: 18px; }
            .stat-label { font-size: 9px; }

            .progress-section {
                padding: 14px;
                margin-top: 16px;
            }
            .progress-grid { gap: 8px; }
            .progress-item {
                grid-template-columns: 110px 1fr auto;
                gap: 10px;
                padding: 10px 12px;
            }
            .progress-item .exercise-name { font-size: 11px; }
            .progress-item .exercise-name .metric-unit { font-size: 10px; }
            .progress-item .mini-chart-wrapper { height: 56px; }
            .progress-item .progress-summary { font-size: 10px; }
            .progress-item .progress-summary .trend { font-size: 12px; }
        }

        @media (max-width: 400px) {
            .month-nav h2 { font-size: 15px; }
            .day { min-height: 48px; padding: 5px 2px; }
            .day-number { font-size: 12px; }
            .day-name { font-size: 8px; }
            .stats { grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="timestamp">Genereeritud: """ + datetime.now().strftime('%d.%m.%Y %H:%M') + """</div>

        <div class="month-nav">
            <button onclick="prevMonth()">&#8249;</button>
            <h2 id="currentMonth"></h2>
            <button onclick="nextMonth()">&#8250;</button>
        </div>

        <div class="calendar" id="calendar"></div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">🏋️ Jõusaal</div>
                <div class="stat-value" id="gymCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🚶 Kõndimine</div>
                <div class="stat-value" id="walkCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🏊 Ujumine</div>
                <div class="stat-value" id="swimCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🚴 Rattasõit</div>
                <div class="stat-value" id="cycleCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">🏃 Jooksmine</div>
                <div class="stat-value" id="runCount">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">⛰️ Matkamine</div>
                <div class="stat-value" id="hikeCount">0</div>
            </div>
        </div>

        <div class="progress-section">
            <h3>📈 Progress</h3>
            <div id="progressGroups"></div>
        </div>
    </div>

    <div class="modal" id="modal" onclick="closeModal(event)">
        <div class="modal-content" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h2 id="modalDate"></h2>
                <span class="close" onclick="closeModal()">&times;</span>
            </div>
            <div id="modalBody"></div>
        </div>
    </div>

    <script>
        const workouts = """ + json.dumps(dict(by_date), ensure_ascii=False) + """;
        const analyses = """ + json.dumps(load_analyses(), ensure_ascii=False) + """;

        let currentYear = new Date().getFullYear();
        let currentMonth = new Date().getMonth();

        const monthNames = ['Jaanuar', 'Veebruar', 'Märts', 'Aprill', 'Mai', 'Juuni',
                           'Juuli', 'August', 'September', 'Oktoober', 'November', 'Detsember'];
        const dayNames = ['E', 'T', 'K', 'N', 'R', 'L', 'P'];

        function findPreviousWorkout(workoutType, currentTimestamp) {
            // Leia kõik sama tüüpi treeningud
            const allWorkoutsFlat = [];
            Object.keys(workouts).forEach(date => {
                workouts[date].forEach(w => {
                    if (w.source === 'gymaholic' && w.workout_type === workoutType && w.timestamp < currentTimestamp) {
                        allWorkoutsFlat.push(w);
                    }
                });
            });

            // Sorteeri timestampi järgi kahanevas järjekorras ja võta esimene
            allWorkoutsFlat.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
            return allWorkoutsFlat.length > 0 ? allWorkoutsFlat[0] : null;
        }

        function renderCalendar() {
            const cal = document.getElementById('calendar');
            cal.innerHTML = '';

            // Päeva päised
            dayNames.forEach(day => {
                const header = document.createElement('div');
                header.className = 'day-header';
                header.textContent = day;
                cal.appendChild(header);
            });

            const firstDay = new Date(currentYear, currentMonth, 1).getDay();
            const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();

            // Tühjad ruudud
            for (let i = 0; i < (firstDay || 7) - 1; i++) {
                const empty = document.createElement('div');
                empty.className = 'day empty';
                cal.appendChild(empty);
            }

            // Päevad
            for (let day = 1; day <= daysInMonth; day++) {
                const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const dayWorkouts = workouts[dateStr] || [];

                const dayEl = document.createElement('div');
                dayEl.className = 'day';

                if (dayWorkouts.length > 0) {
                    const types = [...new Set(dayWorkouts.map(w => {
                        if (w.source === 'gymaholic') {
                            return `gym-${w.workout_type}`;
                        }
                        return w.workout_type;
                    }))];

                    // Värvi kaart (uus stiil)
                    const colorMap = {
                        'gym-jalad': '#d96560',
                        'gym-rind': '#6fc282',
                        'gym-selg': '#e0bd7a',
                        'walking': '#6fa8d4',
                        'running': '#e0a35a',
                        'cycling': '#a583ce',
                        'hiking': '#a4866e',
                        'swimming': '#6fbbbb'
                    };

                    if (types.length > 1) {
                        const colors = types.map(t => colorMap[t] || '#666');
                        dayEl.style.borderLeft = `3px solid ${colors[0]}`;
                        dayEl.style.borderRight = `3px solid ${colors[1]}`;
                        dayEl.className += ' multi';
                    } else {
                        dayEl.className += ` ${types[0]}`;
                    }

                    dayEl.onclick = () => showDetails(dateStr, dayWorkouts);

                    // Treeningu nimed
                    let labels = [];
                    dayWorkouts.forEach(w => {
                        if (w.source === 'gymaholic') {
                            const name = (w.workout_name || '').replace(/^\\d+\\.\\s*/, '').trim();
                            labels.push(`<div class="day-name">${name}</div>`);
                        } else {
                            const cardioNames = {
                                'walking': 'Kõndimine',
                                'running': 'Jooksmine',
                                'cycling': 'Rattasõit',
                                'hiking': 'Matkamine',
                                'swimming': 'Ujumine'
                            };
                            const cardioName = cardioNames[w.workout_type] || w.workout_name || 'Kardio';
                            const distanceInfo = w.distance > 0 ? `${w.distance.toFixed(1)}km` : '';
                            labels.push(`<div class="day-name">${cardioName}</div>` +
                                (distanceInfo ? `<div class="day-cardio-info">${distanceInfo}</div>` : ''));
                        }
                    });

                    dayEl.innerHTML = `
                        <div class="day-number">${day}</div>
                        ${labels.join('')}
                    `;
                } else {
                    dayEl.className += ' empty';
                    dayEl.innerHTML = `<div class="day-number">${day}</div>`;
                }

                cal.appendChild(dayEl);
            }

            document.getElementById('currentMonth').textContent = `${monthNames[currentMonth]} ${currentYear}`;
            updateStats();
        }

        function showDetails(date, dayWorkouts) {
            const modal = document.getElementById('modal');
            const modalDate = document.getElementById('modalDate');
            const modalBody = document.getElementById('modalBody');

            const [y, m, d] = date.split('-');
            modalDate.textContent = `${parseInt(d)}. ${monthNames[parseInt(m) - 1]} ${y}`;

            modalBody.innerHTML = '';

            dayWorkouts.forEach(w => {
                const div = document.createElement('div');
                div.className = w.source === 'gymaholic' ? 'workout-details' : 'workout-details cardio';

                if (w.source === 'gymaholic') {
                    // Leia eelmine sama tüüpi treening
                    const prevWorkout = findPreviousWorkout(w.workout_type, w.timestamp);

                    let exerciseRows = '';
                    if (w.exercises) {
                        w.exercises.forEach(ex => {
                            // Võrdlus eelmise trenniga
                            let weightComparison = '';
                            let repsComparison = '';
                            let weightClass = '';
                            let repsClass = '';

                            if (prevWorkout && prevWorkout.exercises) {
                                const prevEx = prevWorkout.exercises.find(e => e.name === ex.name);
                                if (prevEx) {
                                    const weightDiff = ex.weight_kg - prevEx.weight_kg;
                                    const repsDiff = ex.reps - prevEx.reps;

                                    if (weightDiff > 0) {
                                        weightComparison = ` <span class="comparison positive">(+${weightDiff}kg)</span>`;
                                        weightClass = 'positive';
                                    } else if (weightDiff < 0) {
                                        weightComparison = ` <span class="comparison negative">(${weightDiff}kg)</span>`;
                                        weightClass = 'negative';
                                    }

                                    if (repsDiff > 0) {
                                        repsComparison = ` <span class="comparison positive">(+${repsDiff})</span>`;
                                        repsClass = 'positive';
                                    } else if (repsDiff < 0) {
                                        repsComparison = ` <span class="comparison negative">(${repsDiff})</span>`;
                                        repsClass = 'negative';
                                    }
                                }
                            }

                            // Määra mis näidata Maht veerus
                            let volumeDisplay = '-';
                            if (ex.total_volume > 0) {
                                volumeDisplay = ex.total_volume.toFixed(0) + ' kg';
                            } else if (ex.duration_sec > 0) {
                                // Kui on kestus (Rowing, Walking), näita seda
                                const totalMins = Math.floor(ex.duration_sec / 60);
                                if (totalMins < 60) {
                                    // Alla tunni: "5 min"
                                    volumeDisplay = `${totalMins} min`;
                                } else {
                                    // Üle tunni: "1:05" (hh:mm)
                                    const hours = Math.floor(totalMins / 60);
                                    const mins = totalMins % 60;
                                    volumeDisplay = `${hours}:${mins.toString().padStart(2, '0')}`;
                                }
                            }

                            exerciseRows += `
                                <tr>
                                    <td>${ex.name}</td>
                                    <td>${ex.sets}</td>
                                    <td>${ex.reps}${repsComparison}</td>
                                    <td>${ex.weight_kg > 0 ? ex.weight_kg + ' kg' + weightComparison : '-'}</td>
                                    <td>${volumeDisplay}</td>
                                    <td>${ex.avg_hr > 0 ? ex.avg_hr + ' bpm' : '-'}</td>
                                </tr>
                            `;
                        });
                    }

                    // Eemalda numbrid trenni nimest (nt "1. Jalad & kõht" -> "Jalad & kõht")
                    const cleanWorkoutName = w.workout_name ? w.workout_name.replace(/^\\d+\\.\\s*/, '') : 'Jõutreening';

                    div.innerHTML = `
                        <h3>🏋️ ${cleanWorkoutName}</h3>
                        <p><strong>Kestus:</strong> ${w.duration_min || 0} min | <strong>Kogumaht:</strong> ${(w.total_volume || 0).toFixed(0)} kg${w.avg_hr && w.avg_hr > 0 ? ` | <strong>Keskmine pulss:</strong> ${w.avg_hr} bpm` : ''}</p>
                        <table class="workout-table">
                            <thead>
                                <tr>
                                    <th>Harjutus</th>
                                    <th>Setid</th>
                                    <th>Kordused</th>
                                    <th>Kaal</th>
                                    <th>Maht</th>
                                    <th>Pulss</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${exerciseRows}
                            </tbody>
                        </table>
                    `;
                } else {
                    const icon = {
                        'walking': '🚶',
                        'running': '🏃',
                        'cycling': '🚴',
                        'hiking': '⛰️',
                        'swimming': '🏊'
                    }[w.workout_type] || '🏃';

                    div.innerHTML = `
                        <h3>${icon} ${w.workout_name}</h3>
                        ${w.distance > 0 ? `<p><strong>Distants:</strong> ${w.distance.toFixed(2)} km</p>` : ''}
                        <p><strong>Kestus:</strong> ${w.duration_min} min</p>
                        <p><strong>HR:</strong> ${w.avg_hr} avg, ${w.max_hr} max</p>
                        ${w.kcal > 0 ? `<p><strong>Kalorid:</strong> ${w.kcal} kcal</p>` : ''}
                    `;
                }

                modalBody.appendChild(div);

                // Analüüs antud konkreetse treeningu kohta (timestamp-võti)
                if (analyses[w.timestamp]) {
                    const analysisDiv = document.createElement('div');
                    analysisDiv.className = 'workout-analysis';
                    analysisDiv.innerHTML = `
                        <h3>Analüüs</h3>
                        <div class="analysis-text">${analyses[w.timestamp].replace(/\\n/g, '<br>')}</div>
                    `;
                    modalBody.appendChild(analysisDiv);
                }
            });

            modal.classList.add('active');
        }

        function closeModal(event) {
            if (!event || event.target.id === 'modal') {
                document.getElementById('modal').classList.remove('active');
            }
        }

        function prevMonth() {
            currentMonth--;
            if (currentMonth < 0) {
                currentMonth = 11;
                currentYear--;
            }
            renderCalendar();
        }

        function nextMonth() {
            currentMonth++;
            if (currentMonth > 11) {
                currentMonth = 0;
                currentYear++;
            }
            renderCalendar();
        }

        function updateStats() {
            // Filtreeri ainult valitud kuu treeningud
            const monthPrefix = `${currentYear}-${String(currentMonth + 1).padStart(2, '0')}`;
            const monthWorkouts = Object.entries(workouts)
                .filter(([date]) => date.startsWith(monthPrefix))
                .flatMap(([, ws]) => ws);

            const statCounts = {
                gymCount: monthWorkouts.filter(w => w.source === 'gymaholic').length,
                walkCount: monthWorkouts.filter(w => w.workout_type === 'walking').length,
                swimCount: monthWorkouts.filter(w => w.workout_type === 'swimming').length,
                cycleCount: monthWorkouts.filter(w => w.workout_type === 'cycling').length,
                runCount: monthWorkouts.filter(w => w.workout_type === 'running').length,
                hikeCount: monthWorkouts.filter(w => w.workout_type === 'hiking').length,
            };
            Object.entries(statCounts).forEach(([id, count]) => {
                const el = document.getElementById(id);
                el.textContent = count;
                el.closest('.stat-card').style.display = count > 0 ? '' : 'none';
            });

            // Progressi arvutamine (kogu ajalugu)
            const allWorkouts = Object.values(workouts).flat();
            updateProgress(allWorkouts);
        }

        const TYPE_LABELS = {
            'rind': 'Rind, õlg & triitseps',
            'selg': 'Selg & biitseps',
            'jalad': 'Jalad & kõht',
            'strength': 'Muud',
            'walking': '🚶 Kõndimine',
            'running': '🏃 Jooksmine',
            'cycling': '🚴 Rattasõit',
            'swimming': '🏊 Ujumine',
            'hiking': '⛰️ Matkamine'
        };
        const TYPE_COLORS = {
            'rind': '#6fc282',
            'selg': '#e0bd7a',
            'jalad': '#d96560',
            'strength': '#a0a0a0',
            'walking': '#6fa8d4',
            'running': '#e0a35a',
            'cycling': '#a583ce',
            'swimming': '#6fbbbb',
            'hiking': '#a4866e'
        };
        const TYPE_ORDER = ['rind', 'selg', 'jalad', 'strength', 'walking', 'running', 'cycling', 'swimming', 'hiking'];

        // Mis näitajad iga kardio tüübi puhul (nimi, ühik, võti w-s, parem = väiksem?)
        const CARDIO_METRICS = {
            'walking':  [
                {name: 'Tempo',        unit: 'min/km',  key: 'pace_min_per_km',  lowerBetter: true},
                {name: 'Keskmine HR',  unit: 'bpm',     key: 'avg_hr',           lowerBetter: true},
                {name: 'Z2 aeg',       unit: 'min',     key: 'z2_min',           lowerBetter: false}
            ],
            'running':  [
                {name: 'Tempo',        unit: 'min/km',  key: 'pace_min_per_km',  lowerBetter: true},
                {name: 'Keskmine HR',  unit: 'bpm',     key: 'avg_hr',           lowerBetter: true},
                {name: 'Z2 aeg',       unit: 'min',     key: 'z2_min',           lowerBetter: false}
            ],
            'cycling':  [
                {name: 'Kiirus',       unit: 'km/h',    key: 'speed_km_per_h',   lowerBetter: false},
                {name: 'Keskmine HR',  unit: 'bpm',     key: 'avg_hr',           lowerBetter: true},
                {name: 'Distants',     unit: 'km',      key: 'distance',         lowerBetter: false}
            ],
            'swimming': [
                {name: 'Tempo',        unit: 'min/100m',key: 'pace_min_per_100m',lowerBetter: true},
                {name: 'Keskmine HR',  unit: 'bpm',     key: 'avg_hr',           lowerBetter: true},
                {name: 'Distants',     unit: 'm',       key: 'distance_m',       lowerBetter: false}
            ],
            'hiking':   [
                {name: 'Distants',     unit: 'km',      key: 'distance',         lowerBetter: false},
                {name: 'Keskmine HR',  unit: 'bpm',     key: 'avg_hr',           lowerBetter: true},
                {name: 'Kestus',       unit: 'min',     key: 'duration_min',     lowerBetter: false}
            ]
        };

        function renderChart(canvasId, labels, values, color, tooltipFmt) {
            requestAnimationFrame(() => {
                const ctx = document.getElementById(canvasId);
                if (!ctx) return;
                const chart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            borderColor: color,
                            backgroundColor: color + '33',
                            borderWidth: 2,
                            cubicInterpolationMode: 'monotone',
                            tension: 0,
                            fill: true,
                            pointRadius: 2,
                            pointHoverRadius: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: { callbacks: { label: tooltipFmt } }
                        },
                        scales: {
                            x: { ticks: { color: '#999', font: { size: 9 }, maxTicksLimit: 4 }, grid: { display: false } },
                            y: { ticks: { color: '#999', font: { size: 9 }, maxTicksLimit: 4 }, grid: { color: 'rgba(255,255,255,0.05)' } }
                        }
                    }
                });
                window._progressCharts.push(chart);
            });
        }

        function trendSummary(values, lowerBetter, unit) {
            if (!values || values.length === 0) return {html: '', trendClass: ''};
            const first = values[0];
            const last = values[values.length - 1];
            const delta = last - first;
            const absDelta = Math.abs(delta);
            let trendClass = 'flat';
            let arrow = '→';
            if (absDelta > (Math.abs(first) * 0.02)) {
                const isImprovement = lowerBetter ? delta < 0 : delta > 0;
                trendClass = isImprovement ? 'up' : 'down';
                arrow = delta > 0 ? '↑' : '↓';
            }
            const lastStr = (Number.isInteger(last) ? last : last.toFixed(1));
            return {
                html: `<div class="trend ${trendClass}">${arrow} ${lastStr} ${unit}</div><div>${values.length} sess.</div>`,
                trendClass
            };
        }

        function addProgressItem(grid, type, key, label, unit, values, labels, tooltipFmt, lowerBetter) {
            if (!values || values.length === 0) return;
            const card = document.createElement('div');
            card.className = 'progress-item';
            card.style.borderLeftColor = TYPE_COLORS[type];

            const canvasId = `chart_${type}_${key}`;
            const nameDiv = document.createElement('div');
            nameDiv.className = 'exercise-name';
            nameDiv.innerHTML = `${label}<span class="metric-unit">${unit}</span>`;
            card.appendChild(nameDiv);

            const wrap = document.createElement('div');
            wrap.className = 'mini-chart-wrapper';
            const canvas = document.createElement('canvas');
            canvas.id = canvasId;
            wrap.appendChild(canvas);
            card.appendChild(wrap);

            const summary = document.createElement('div');
            summary.className = 'progress-summary';
            summary.innerHTML = trendSummary(values, lowerBetter, unit).html;
            card.appendChild(summary);

            grid.appendChild(card);
            renderChart(canvasId, labels, values, TYPE_COLORS[type], tooltipFmt);
        }

        function updateProgress(allWorkouts) {
            const gymWorkouts = allWorkouts.filter(w => w.source === 'gymaholic');

            // Kogu iga harjutuse ajalugu
            const exerciseHistory = {};
            gymWorkouts.forEach(w => {
                const wtype = w.workout_type || 'strength';
                if (!w.exercises) return;
                w.exercises.forEach(ex => {
                    const name = ex.name;
                    const weight = ex.weight_kg || 0;
                    const lname = name.toLowerCase();
                    if (weight <= 0 || lname.includes('rowing') || lname.includes('treadmill')) return;
                    if (!exerciseHistory[name]) {
                        exerciseHistory[name] = { type: wtype, history: [] };
                    }
                    exerciseHistory[name].history.push({
                        date: w.timestamp || w.date,
                        weight: weight,
                        reps: ex.reps || 0,
                        sets: ex.sets || 0
                    });
                });
            });

            // Grupeeri treeningtüübi järgi
            const typeGroups = { 'rind': [], 'selg': [], 'jalad': [], 'strength': [] };
            Object.entries(exerciseHistory).forEach(([name, data]) => {
                const type = typeGroups[data.type] !== undefined ? data.type : 'strength';
                typeGroups[type].push({ name, type, history: data.history });
            });

            const container = document.getElementById('progressGroups');
            container.innerHTML = '';

            // Hävita vanad chart'id
            if (window._progressCharts) {
                window._progressCharts.forEach(c => { try { c.destroy(); } catch(e) {} });
            }
            window._progressCharts = [];

            // Jõutrennide sektsioonid
            ['rind', 'selg', 'jalad', 'strength'].forEach(type => {
                const exercises = typeGroups[type];
                if (!exercises || exercises.length === 0) return;

                exercises.sort((a, b) => a.name.localeCompare(b.name, 'et'));

                const group = document.createElement('div');
                group.className = 'progress-group';
                const title = document.createElement('div');
                title.className = 'progress-group-title';
                title.textContent = TYPE_LABELS[type];
                title.style.borderLeftColor = TYPE_COLORS[type];
                group.appendChild(title);

                const grid = document.createElement('div');
                grid.className = 'progress-grid';

                exercises.forEach((ex, i) => {
                    ex.history.sort((a, b) => (a.date || '').localeCompare(b.date || ''));
                    const labels = ex.history.map(h => {
                        const d = new Date(h.date);
                        return isNaN(d) ? '' : d.toLocaleDateString('et-EE', { day: '2-digit', month: '2-digit' });
                    });
                    const weights = ex.history.map(h => h.weight);
                    const tooltipFmt = (c) => {
                        const h = ex.history[c.dataIndex];
                        return `${h.sets}×${h.reps} @ ${h.weight}kg`;
                    };
                    addProgressItem(grid, type, `ex${i}`, ex.name, 'kg', weights, labels, tooltipFmt, false);
                });

                group.appendChild(grid);
                container.appendChild(group);
            });

            // Kardio sektsioonid — iga tüübi kohta 3 näitajat
            const cardioWorkouts = allWorkouts.filter(w => w.source === 'workoutdoor');
            const cardioByType = {};
            cardioWorkouts.forEach(w => {
                const t = w.workout_type;
                if (!CARDIO_METRICS[t]) return;
                (cardioByType[t] = cardioByType[t] || []).push(w);
            });

            Object.keys(CARDIO_METRICS).forEach(type => {
                const sessions = cardioByType[type];
                if (!sessions || sessions.length < 2) return;  // Trendi jaoks vaja ≥2 sessiooni

                sessions.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

                const group = document.createElement('div');
                group.className = 'progress-group';
                const title = document.createElement('div');
                title.className = 'progress-group-title';
                title.textContent = TYPE_LABELS[type];
                title.style.borderLeftColor = TYPE_COLORS[type];
                group.appendChild(title);

                const grid = document.createElement('div');
                grid.className = 'progress-grid';

                const labels = sessions.map(s => {
                    const d = new Date(s.timestamp || s.date);
                    return isNaN(d) ? '' : d.toLocaleDateString('et-EE', { day: '2-digit', month: '2-digit' });
                });

                CARDIO_METRICS[type].forEach(metric => {
                    const values = sessions.map(s => {
                        if (metric.key === 'distance_m') return Math.round((s.distance || 0) * 1000);
                        return s[metric.key] || 0;
                    }).filter(v => v > 0);
                    if (values.length < 2) return;
                    // Aga labels peavad vastama filtered values'ile:
                    const fullLabels = sessions.map((s, i) => {
                        const v = metric.key === 'distance_m' ? Math.round((s.distance || 0) * 1000) : (s[metric.key] || 0);
                        return v > 0 ? labels[i] : null;
                    }).filter(l => l !== null);
                    const tooltipFmt = (c) => `${values[c.dataIndex]} ${metric.unit}`;
                    addProgressItem(grid, type, metric.key, metric.name, metric.unit, values, fullLabels, tooltipFmt, metric.lowerBetter);
                });

                if (grid.children.length > 0) {
                    group.appendChild(grid);
                    container.appendChild(group);
                }
            });
        }

        // Initialize
        renderCalendar();
    </script>
</body>
</html>"""

    return html

def main():
    workouts = load_data()
    html = generate_html(workouts)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"✅ Kalender genereeritud: {OUTPUT_FILE}")
    print(f"📊 Kokku: {len(workouts)} treeningut")
    print(f"📄 Suurus: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")

    # Upload to Google Drive (Claude Projects kaust)
    try:
        import subprocess
        import os
        gdrive_folder = os.getenv('GDRIVE_CLAUDE_FOLDER', '_trenn_output')

        # Loo kaust kui ei eksisteeri
        subprocess.run(['rclone', 'mkdir', f'gdrive:{gdrive_folder}'],
                      capture_output=True, check=False)

        # Kopeeri fail
        result = subprocess.run(
            ['rclone', 'copy', str(OUTPUT_FILE), f'gdrive:{gdrive_folder}/'],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode == 0:
            print(f"📤 Üles laaditud: gdrive:{gdrive_folder}/calendar.html")
        else:
            print(f"⚠️  Google Drive upload ebaõnnestus: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Google Drive upload ebaõnnestus: {e}")

    # Push to GitHub Pages
    try:
        import shutil
        from pathlib import Path

        script_dir = Path(__file__).parent

        # Kopeeri calendar.html → index.html (GitHub Pages vajab index.html)
        shutil.copy(script_dir / 'calendar.html', script_dir / 'index.html')

        # Git add, commit, push
        subprocess.run(['git', 'add', 'index.html'], cwd=script_dir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'Update calendar'], cwd=script_dir, capture_output=True)
        result = subprocess.run(['git', 'push'], cwd=script_dir, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print(f"🐙 GitHub Pages uuendatud: https://aimarraid-netizen.github.io/trenn-d8b4c9a1/")
        else:
            print(f"⚠️  GitHub push ebaõnnestus: {result.stderr}")
    except Exception as e:
        print(f"⚠️  GitHub push ebaõnnestus: {e}")

if __name__ == '__main__':
    main()
