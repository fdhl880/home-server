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

# 3. Initialize results directory and active positions if missing
mkdir -p pluang-bot/results
if [ ! -f "pluang-bot/results/active_positions.json" ]; then
    echo "[]" > pluang-bot/results/active_positions.json
fi

# 4. Clean up any zombie process holding port 4000
echo "[*] Ensuring Port 4000 & previous bot processes are clean..."
if command -v fuser &> /dev/null; then
    fuser -k 4000/tcp 2>/dev/null || true
fi
pkill -9 -f "node server.js" 2>/dev/null || true
pkill -9 -f "telegram_bot.py" 2>/dev/null || true
sleep 1

# 5. Launch Telegram Bot in background
if [ -f "pluang-bot/telegram_bot.py" ]; then
    echo "[*] Launching Pyrofuel Telegram Bot (@idrisginting_bot) in background..."
    $PY_BIN pluang-bot/telegram_bot.py > telegram_bot.log 2>&1 &
fi

# 6. Start Unified Bloomberg & Crypto Futures Engine
echo "[*] Launching Unified Bloomberg Terminal & Crypto Futures Engine on Port 4000..."
exec node server.js
