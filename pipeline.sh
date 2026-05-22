#!/bin/bash
set -euo pipefail

# ==========================================
# Trenn Pipeline - ühtne orkestrator
# Kutsutav nii n8n-ist (SSH) kui käsitsi
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/tmp/trenn_pipeline.lock"
LOG_FILE="$SCRIPT_DIR/logs/pipeline.log"
PROCESSED_LOG="$SCRIPT_DIR/logs/processed_files.log"

# ==========================================
# Lukustus — ainult üks instants korraga
# ==========================================
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo '{"status":"locked","message":"Teine pipeline jookseb juba"}'
    exit 0
fi

cd "$SCRIPT_DIR"

# Aktiveeri venv
if [[ -d "venv" ]]; then
    source venv/bin/activate
fi

# Loo vajalikud kaustad
mkdir -p data/{incoming,temp_import,processed/{csv,fit,gpx}} logs

# Laadi .env
if [[ ! -f .env ]]; then
    echo '{"status":"error","message":".env fail puudub"}'
    exit 1
fi
set -a; source .env; set +a

# ==========================================
# Logimine
# ==========================================
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Logi rotatsioon (>5MB → viimased 5000 rida)
if [[ -f "$LOG_FILE" ]]; then
    size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if (( size > 5242880 )); then
        tail -5000 "$LOG_FILE" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "$LOG_FILE"
        log "Logi roteeritud"
    fi
fi

log "========== PIPELINE ALGUS =========="

# Loendurid
zip_count=0
fit_count=0
gpx_count=0
errors=()
zip_names=()
fit_names=()
gpx_names=()

# ==========================================
# 1. rclone sync Google Drive'ist
# ==========================================
log "1. rclone sync..."

if ! rclone sync "gdrive:_trenn_input" data/incoming/ --log-file=logs/rclone.log 2>&1; then
    log "ERROR: rclone sync ebaõnnestus"
    echo '{"status":"error","message":"rclone sync ebaõnnestus"}'
    exit 1
fi
log "   OK"

# ==========================================
# 2. Gymaholic ZIP failid
# ==========================================
log "2. Gymaholic ZIP-id..."

zip_files=(data/incoming/gym_*.zip)
if [[ -f "${zip_files[0]}" ]]; then
    new_zips=0

    # Tuvasta uued ZIP-id (hash-põhiselt)
    for zipfile in data/incoming/gym_*.zip; do
        filename=$(basename "$zipfile")
        file_hash=$(sha256sum "$zipfile" | cut -d' ' -f1)

        if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
            continue
        fi

        log "   Uus ZIP: $filename"
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ZIP_EXTRACTED|$file_hash" >> "$PROCESSED_LOG"
        zip_names+=("$filename")
        new_zips=$((new_zips + 1))
    done

    if (( new_zips > 0 )); then
        # Paki KÕIK ZIP-id lahti (mitte ainult uued), sest restore_gymaholic.py
        # asendab kõik gymaholic treeningud — vajab täielikku ajalugu
        rm -rf data/temp_import/gymexport_*
        log "   Pakin lahti KÕIK ${#zip_files[@]} ZIP-i (et säiliks täielik ajalugu)..."

        for zipfile in data/incoming/gym_*.zip; do
            filename=$(basename "$zipfile")
            if ! unzip -o -q "$zipfile" -d data/temp_import/ 2>>"$LOG_FILE"; then
                log "   VIGA: $filename lahti pakkimine ebaõnnestus"
                errors+=("ZIP: $filename")
            fi
        done

        log "   Taastan Gymaholic andmed ($new_zips uut ZIP-i, ${#zip_files[@]} kokku)..."
        if python3 restore_gymaholic.py data/temp_import/gymexport_*/ >> "$LOG_FILE" 2>&1; then
            log "   OK: taastatud"
            zip_count=$new_zips
        else
            log "   VIGA: restore_gymaholic.py ebaõnnestus"
            errors+=("restore_gymaholic.py")
        fi
        rm -rf data/temp_import/gymexport_*
    fi
else
    log "   Uusi ZIP-e pole"
fi

# ==========================================
# 3. FIT failid
# ==========================================
log "3. FIT failid..."

while IFS= read -r -d '' file; do
    filename=$(basename "$file")
    file_hash=$(sha256sum "$file" | cut -d' ' -f1)

    if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
        continue
    fi

    log "   Uus FIT: $filename"

    if python3 convert_fit.py "$file" >> "$LOG_FILE" 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|FIT_CONVERTED|$file_hash" >> "$PROCESSED_LOG"
        fit_names+=("$filename")
        fit_count=$((fit_count + 1))
        log "   OK: $filename"
    else
        log "   VIGA: $filename konverteerimine"
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ERROR|$file_hash" >> "$PROCESSED_LOG"
        errors+=("FIT: $filename")
    fi

done < <(find data/incoming/ -type f -iname "*.fit" -print0 2>/dev/null)

if (( fit_count == 0 )); then
    log "   Uusi FIT-e pole"
fi

# ==========================================
# 3b. GPX failid
# ==========================================
log "3b. GPX failid..."

while IFS= read -r -d '' file; do
    filename=$(basename "$file")
    file_hash=$(sha256sum "$file" | cut -d' ' -f1)

    if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
        continue
    fi

    log "   Uus GPX: $filename"

    if python3 convert_gpx.py "$file" >> "$LOG_FILE" 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|GPX_CONVERTED|$file_hash" >> "$PROCESSED_LOG"
        gpx_names+=("$filename")
        gpx_count=$((gpx_count + 1))
        log "   OK: $filename"
    else
        log "   VIGA: $filename konverteerimine"
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ERROR|$file_hash" >> "$PROCESSED_LOG"
        errors+=("GPX: $filename")
    fi

done < <(find data/incoming/ -type f -iname "*.gpx" -print0 2>/dev/null)

if (( gpx_count == 0 )); then
    log "   Uusi GPX-e pole"
fi

# ==========================================
# 4. Väljundite genereerimine (ainult kui töödeldud)
# ==========================================
total=$((zip_count + fit_count + gpx_count))

if (( total > 0 )); then
    log "4. Genereerin väljundid ($total uut faili)..."

    # fitness_knowledge.md (genereerib + laadib Google Drive'i)
    if python3 prepare_claude_project.py >> "$LOG_FILE" 2>&1; then
        log "   OK: fitness_knowledge.md"
    else
        log "   VIGA: prepare_claude_project.py"
        errors+=("prepare_claude_project.py")
    fi

    # analyze_workout.py — analüüsib uued trennid Claude API-ga (analyses.json)
    # Mitte-blokeeriv: kui API võti puudub või viga, jätkame ilma
    if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
        if python3 analyze_workout.py --limit "$total" >> "$LOG_FILE" 2>&1; then
            log "   OK: analyze_workout.py"
        else
            log "   HOIATUS: analyze_workout.py ebaõnnestus (pipeline jätkab)"
            errors+=("analyze_workout.py")
        fi

        # weekly_summary.py — pühapäeviti nädala kokkuvõte (week_summaries.json)
        if [[ "$(date +%u)" == "7" ]]; then
            if python3 weekly_summary.py >> "$LOG_FILE" 2>&1; then
                log "   OK: weekly_summary.py"
            else
                log "   HOIATUS: weekly_summary.py ebaõnnestus"
                errors+=("weekly_summary.py")
            fi
        fi
    else
        log "   SKIP: analyze_workout.py (ANTHROPIC_API_KEY puudub .env-is)"
    fi

    # calendar.html (genereerib + kopeerib index.html + git push + rclone)
    if python3 generate_calendar.py >> "$LOG_FILE" 2>&1; then
        log "   OK: calendar.html"
    else
        log "   VIGA: generate_calendar.py"
        errors+=("generate_calendar.py")
    fi

    # import_summary.md → Google Drive
    SUMMARY_FILE="$SCRIPT_DIR/import_summary.md"
    GDRIVE_FOLDER="${GDRIVE_CLAUDE_FOLDER:-_trenn_output}"
    TIMESTAMP=$(date '+%d.%m.%Y %H:%M')

    {
        echo "# Import $TIMESTAMP"
        echo ""
        echo "## Töödeldud failid"
        echo ""
        if (( zip_count > 0 )); then
            echo "### Gymaholic ZIP ($zip_count)"
            for name in "${zip_names[@]}"; do echo "- $name"; done
            echo ""
        fi
        if (( fit_count > 0 )); then
            echo "### Workoutdoor FIT ($fit_count)"
            for name in "${fit_names[@]}"; do echo "- $name"; done
            echo ""
        fi
        if (( gpx_count > 0 )); then
            echo "### GPX ($gpx_count)"
            for name in "${gpx_names[@]}"; do echo "- $name"; done
            echo ""
        fi
        echo "## Väljundid"
        echo ""
        if [[ -f claude_project/fitness_knowledge.md ]]; then
            wcount=$(python3 -c "import json; print(len(json.load(open('data/workout_history.json'))['workouts']))" 2>/dev/null || echo "?")
            fsize=$(ls -lh claude_project/fitness_knowledge.md | awk '{print $5}')
            echo "- **fitness_knowledge.md** — $wcount treeningut, $fsize"
        fi
        if [[ -f calendar.html ]]; then
            csize=$(ls -lh calendar.html | awk '{print $5}')
            echo "- **calendar.html** — $csize"
        fi
        if (( ${#errors[@]} > 0 )); then
            echo ""
            echo "## Vead"
            echo ""
            for err in "${errors[@]}"; do echo "- $err"; done
        fi
    } > "$SUMMARY_FILE"

    rclone copy "$SUMMARY_FILE" "gdrive:$GDRIVE_FOLDER/" --log-file=logs/rclone.log 2>&1
    log "   OK: import_summary.md → Google Drive"
else
    log "4. Uusi faile pole — väljundid jäävad samaks"
fi

# ==========================================
# JSON väljund (n8n parsib seda)
# ==========================================
log "PIPELINE LÕPP: $zip_count ZIP, $fit_count FIT, $gpx_count GPX, ${#errors[@]} viga"
log "=========================================="

error_json="[]"
if (( ${#errors[@]} > 0 )); then
    error_json=$(printf '%s\n' "${errors[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))")
fi

cat <<EOF
{"status":"ok","processed":$total,"zips":$zip_count,"fits":$fit_count,"gpxs":$gpx_count,"errors":$error_json}
EOF
