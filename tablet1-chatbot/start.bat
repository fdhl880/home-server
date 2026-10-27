@echo off
title BLOOMBERG TERMINAL & PYROFUEL AI TRADING ENGINE
cd /d "%~dp0"

echo ==================================================================
echo BLOOMBERG TERMINAL & PYROFUEL 5-LAYER AI TRADING ENGINE
echo ==================================================================

if not exist node_modules (
    echo [*] Installing Node.js dependencies...
    call npm install
)

echo [*] Checking Python dependencies...
python -m pip install -r requirements.txt --quiet >nul 2>&1

echo [*] Launching Unified Bloomberg & Binance Futures Engine...
start "Pyrofuel Telegram Bot" /B python pluang-bot\telegram_bot.py
start "Pyrofuel Auto Trader" /B python pluang-bot\auto_trader.py
node server.js
pause
