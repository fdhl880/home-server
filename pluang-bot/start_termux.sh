#!/data/data/com.termux/files/usr/bin/env bash
# =============================================================
# T0.8 & T0.9: Consolidated Launcher (Zero Hardcoded/Base64 Secrets)
# Delegates to canonical tablet1-chatbot/pluang-bot/start_termux.sh
# =============================================================
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_DIR="$SCRIPT_DIR/../tablet1-chatbot/pluang-bot"

if [ -f "$CANONICAL_DIR/start_termux.sh" ]; then
    exec bash "$CANONICAL_DIR/start_termux.sh" "$@"
else
    echo "Canonical directory not found at $CANONICAL_DIR"
    exit 1
fi
