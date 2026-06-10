#!/bin/bash
set -euo pipefail

# ==========================================
# Trenn v2 Pipeline - ainult SQLite/v2 voog
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/tmp/trenn_pipeline.lock"
LOG_FILE="$SCRIPT_DIR/logs/pipeline.log"
PROCESSED_LOG="$SCRIPT_DIR/logs/processed_files.log"

exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo '{"status":"locked","message":"Teine pipeline jookseb juba"}'
    exit 0
fi

cd "$SCRIPT_DIR"

if [[ -d "venv" ]]; then
    source venv/bin/activate
fi

mkdir -p data/{incoming,temp_import,processed/{csv,fit,gpx}} logs

if [[ ! -f .env ]]; then
    echo '{"status":"error","message":".env fail puudub"}'
    exit 1
fi
set -a; source .env; set +a

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

if [[ -f "$LOG_FILE" ]]; then
    size=$(stat -c%s "$LOG_FILE" 2>/dev/null || echo 0)
    if (( size > 5242880 )); then
        tail -5000 "$LOG_FILE" > "${LOG_FILE}.tmp"
        mv "${LOG_FILE}.tmp" "$LOG_FILE"
        log "Logi roteeritud"
    fi
fi

log "========== PIPELINE ALGUS (v2) =========="

# Ootamatu katkestus (set -e) peab andma korrektse error-JSON-i,
# mida Kratt saab Discordi edastada.
pipeline_done=0
on_exit() {
    if (( pipeline_done == 0 )); then
        log "ERROR: pipeline katkes ootamatult (exit $?)"
        echo '{"status":"error","message":"pipeline katkes ootamatult, vaata logs/pipeline.log"}'
    fi
}
trap on_exit EXIT

zip_count=0
fit_count=0
gpx_count=0
errors=()
zip_names=()
fit_names=()
gpx_names=()

# 1) Sisend: Kratt paneb failid otse data/incoming/ (Google Drive voog on pensionil)

# 2) Gymaholic ZIP -> CSV -> v2/parse_gymaholic_csv.py
log "2. Gymaholic ZIP-id..."
while IFS= read -r -d '' zipfile; do
    filename=$(basename "$zipfile")
    file_hash=$(sha256sum "$zipfile" | cut -d' ' -f1)

    if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
        continue
    fi

    log "   Uus ZIP: $filename"
    tmpdir="data/temp_import/${filename%.zip}_$$"
    rm -rf "$tmpdir"
    mkdir -p "$tmpdir"

    if ! unzip -o -q "$zipfile" -d "$tmpdir" 2>>"$LOG_FILE"; then
        log "   VIGA: $filename lahti pakkimine ebaõnnestus"
        errors+=("ZIP unzip: $filename")
        rm -rf "$tmpdir"
        continue
    fi

    mapfile -d '' csvs < <(find "$tmpdir" -type f -iname "*.csv" -print0 2>/dev/null)
    if (( ${#csvs[@]} == 0 )); then
        log "   VIGA: ZIP-is pole CSV faile ($filename)"
        errors+=("ZIP CSV puudub: $filename")
        rm -rf "$tmpdir"
        continue
    fi

    if python3 v2/parse_gymaholic_csv.py "${csvs[@]}" >> "$LOG_FILE" 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ZIP_IMPORTED_V2|$file_hash" >> "$PROCESSED_LOG"
        zip_count=$((zip_count + 1))
        zip_names+=("$filename")
        log "   OK: $filename"
    else
        log "   VIGA: v2/parse_gymaholic_csv.py ($filename)"
        errors+=("ZIP parse: $filename")
    fi

    rm -rf "$tmpdir"
done < <(find data/incoming/ -type f -name "gym_*.zip" -print0 2>/dev/null)

if (( zip_count == 0 )); then
    log "   Uusi ZIP-e pole"
fi

# 3) FIT -> v2/parse_fit.py
log "3. FIT failid..."
while IFS= read -r -d '' file; do
    filename=$(basename "$file")
    file_hash=$(sha256sum "$file" | cut -d' ' -f1)

    if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
        continue
    fi

    log "   Uus FIT: $filename"
    if python3 v2/parse_fit.py "$file" >> "$LOG_FILE" 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|FIT_IMPORTED_V2|$file_hash" >> "$PROCESSED_LOG"
        fit_count=$((fit_count + 1))
        fit_names+=("$filename")
        log "   OK: $filename"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ERROR|$file_hash" >> "$PROCESSED_LOG"
        errors+=("FIT: $filename")
        log "   VIGA: $filename"
    fi
done < <(find data/incoming/ -type f -iname "*.fit" -print0 2>/dev/null)

if (( fit_count == 0 )); then
    log "   Uusi FIT-e pole"
fi

# 3b) GPX/XML -> v2/parse_gpx.py
log "3b. GPX/XML failid..."
while IFS= read -r -d '' file; do
    filename=$(basename "$file")
    file_hash=$(sha256sum "$file" | cut -d' ' -f1)

    if [[ -f "$PROCESSED_LOG" ]] && grep -q "$file_hash" "$PROCESSED_LOG" 2>/dev/null; then
        continue
    fi

    log "   Uus GPX/XML: $filename"
    if python3 v2/parse_gpx.py "$file" >> "$LOG_FILE" 2>&1; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|GPX_IMPORTED_V2|$file_hash" >> "$PROCESSED_LOG"
        gpx_count=$((gpx_count + 1))
        gpx_names+=("$filename")
        log "   OK: $filename"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S')|$filename|ERROR|$file_hash" >> "$PROCESSED_LOG"
        errors+=("GPX/XML: $filename")
        log "   VIGA: $filename"
    fi
done < <(find data/incoming/ -type f \( -iname "*.gpx" -o -iname "*.xml" \) -print0 2>/dev/null)

if (( gpx_count == 0 )); then
    log "   Uusi GPX/XML-e pole"
fi

# 4) Analüüs + HTML render
total=$((zip_count + fit_count + gpx_count))
if (( total > 0 )); then
    log "4. Genereerin v2 väljundid ($total uut faili)..."
    if python3 v2/analyze.py >> "$LOG_FILE" 2>&1; then
        log "   OK: v2/analyze.py"
    else
        errors+=("v2/analyze.py")
        log "   HOIATUS: v2/analyze.py ebaõnnestus"
    fi

    if python3 v2/render_html.py >> "$LOG_FILE" 2>&1; then
        log "   OK: v2/render_html.py"
    else
        errors+=("v2/render_html.py")
        log "   VIGA: v2/render_html.py"
    fi
else
    log "4. Uusi faile pole — väljundid jäävad samaks"
fi

# 5) Nädala kokkuvõte (pühapäeviti, kord nädalas, ainult kui uusi faile tuli)
STAMP="logs/last_weekly_summary"
if (( total > 0 )) && [[ "$(date +%u)" == "7" ]] \
   && [[ "$(cat "$STAMP" 2>/dev/null)" != "$(date +%G-W%V)" ]] \
   && [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    log "5. Nädala kokkuvõte (weekly_summary.py)..."
    if python3 weekly_summary.py >> "$LOG_FILE" 2>&1; then
        date +%G-W%V > "$STAMP"
        log "   OK: weekly_summary"
    else
        errors+=("weekly_summary")
        log "   HOIATUS: weekly_summary ebaõnnestus"
    fi
fi

log "PIPELINE LÕPP: $zip_count ZIP, $fit_count FIT, $gpx_count GPX/XML, ${#errors[@]} viga"
log "=========================================="

error_json="[]"
if (( ${#errors[@]} > 0 )); then
    error_json=$(printf '%s\n' "${errors[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))")
fi

pipeline_done=1
cat <<EOF
{"status":"ok","processed":$total,"zips":$zip_count,"fits":$fit_count,"gpxs":$gpx_count,"errors":$error_json}
EOF
