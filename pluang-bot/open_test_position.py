"""
===========================================================================
OPEN REAL TEST POSITION ON BINANCE FUTURES + NOTIFY TELEGRAM
===========================================================================
Security (T0.8): Zero hardcoded credentials. All keys/tokens loaded from .env.
===========================================================================
"""
import os
import json
import requests
from datetime import datetime, timezone
from pipeline import load_env
from binance_futures import BinanceFuturesClient

ENV = load_env()
TELEGRAM_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = int(ENV.get("ALLOWED_TELEGRAM_CHAT_ID", "6794056929"))
TELE_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE_DIR, "results", "active_positions.json")
os.makedirs(os.path.join(BASE_DIR, "results"), exist_ok=True)


def send_tg(text: str):
    if not TELEGRAM_TOKEN:
        print("[-] TELEGRAM_BOT_TOKEN belum diset di .env")
        return False
    try:
        r = requests.post(
            f"{TELE_API}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        res = r.json()
        print(f"Telegram sent: ok={res.get('ok')}")
        return res.get("ok")
    except Exception as e:
        print(f"Telegram error: {e}")
        return False
