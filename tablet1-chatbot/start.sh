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
    echo "[*] Checking Python dependencies..."
    pip3 install -r requirements.txt --quiet || pip install -r requirements.txt --quiet || true
elif command -v pip &> /dev/null; then
    pip install -r requirements.txt --quiet || true
fi

# 3. Start Unified Bloomberg & Pluang Server
echo "[*] Launching Node.js Bloomberg Terminal on Port 4000..."
echo "[*] Node will automatically spawn Pluang Python Server (Port 5000), Auto-Trader & Telegram Bot!"
exec node server.js
