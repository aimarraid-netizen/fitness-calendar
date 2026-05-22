#!/bin/bash
set -euo pipefail

# ==========================================
# Tark git commit - ainult kui on muudatusi
# ==========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

FILE="$1"
MESSAGE="${2:-Update calendar}"

# Kontrolli kas fail on muutunud
if ! git diff --quiet "$FILE" 2>/dev/null; then
    echo "✓ Muudatused leitud: $FILE"

    git add "$FILE"
    git commit -m "$MESSAGE

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

    # Push (võib ebaõnnestuda, kui network pole)
    if git push origin main 2>&1; then
        echo "✓ Pushed to GitHub"
    else
        echo "⚠ Push ebaõnnestus (proovib järgmine kord)"
    fi
else
    echo "ℹ Muudatusi pole: $FILE - jätan commiti vahele"
fi
