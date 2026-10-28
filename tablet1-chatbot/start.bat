@echo off
title TABLET1-CHATBOT: BLOOMBERG TERMINAL & PYROFUEL 28-PILLAR ENGINE
cd /d "%~dp0"

echo ==================================================================
echo TABLET1-CHATBOT: BLOOMBERG TERMINAL ^& PYROFUEL 28-PILLAR AI ENGINE
echo ==================================================================

if not exist node_modules (
    echo [*] Installing Node.js dependencies...
    call npm install
)

echo [*] Checking Python dependencies...
python -m pip install -r requirements.txt --quiet >nul 2>&1

echo [*] Launching Unified Bloomberg ^& Binance Futures Engine (Single-Instance)...
start "Pyrofuel Telegram Bot" /B python pluang-bot\telegram_bot.py
node server.js
pause
