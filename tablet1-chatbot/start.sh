#!/bin/bash
# ==============================================================================
# PYROFUEL & BLOOMBERG TERMINAL - ZERO SETUP UNIFIED RUNNER (HOME SERVER / LINUX)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=================================================================="
echo "🏛️ STARTING BLOOMBERG TERMINAL & PYROFUEL 5-LAYER AI TRADING ENGINE"
echo "📂 Location: $DIR"
echo "=================================================================="

# 1. Install Node.js dependencies if node_modules missing
if [ ! -d "node_modules" ]; then
    echo "[*] Installing Node.js dependencies..."
    npm install --silent || echo "[!] npm install skipped or minimal"
fi

# 2. Check Python & install requirements if pip available
PY_BIN="python3"
if ! command -v python3 &> /dev/null; then
    PY_BIN="python"
fi

if command -v pip3 &> /dev/null; then
    pip3 install requests python-dotenv --quiet || true
elif command -v pip &> /dev/null; then
    pip install requests python-dotenv --quiet || true
fi

# 3. Clean up stale mock positions so tables start fresh
rm -f pluang-bot/results/active_positions.json
mkdir -p pluang-bot/results
echo "[]" > pluang-bot/results/active_positions.json

# 4. Start Unified Bloomberg & Crypto Futures Engine
echo "[*] Launching Unified Bloomberg Terminal & Crypto Futures Engine on Port 4000..."
exec node server.js
