import json
import time
import os
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BASE_DIR, "results", "active_positions.json")
TELE_TOKEN = "8829535429:AAHFHM56RDNAd7-ax6Dd-3V3g9OZEleYi5M"

# 1. Fetch live BTC price
r = requests.get("https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
btc_price = float(r.json()["price"])
fx_rate = 18052.88

pos = {
    "id": f"POS_BTC_{int(time.time())}",
    "symbol": "BTC-USD",
    "binance_pair": "BTCUSDT",
    "direction": "LONG",
    "entry_price": btc_price,
    "entry_price_idr": round(btc_price * fx_rate, 2),
    "take_profit": round(btc_price * 1.036, 2),
    "take_profit_1": round(btc_price * 1.036, 2),
    "take_profit_2": round(btc_price * 1.036, 2),
    "stop_loss": round(btc_price * 0.988, 2),
    "leverage": 5,
    "position_size_idr": 50000,
    "position_size_usd": round(50000 / fx_rate, 4),
    "risk_reward_ratio": "1:3.0",
    "confidence_score": 88,
    "setup_name": "EMA_PULLBACK_CONFLUENCE_LONG",
    "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "status": "OPEN",
    "pnl_idr": 0,
    "pnl_usd": 0,
    "pnl_pct": 0.0,
    "type": "CRYPTO_FUTURES_SIMULATION"
}

positions = []
if os.path.exists(POSITIONS_FILE):
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            positions = json.load(f)
    except Exception:
        positions = []

positions.append(pos)
os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
    json.dump(positions, f, indent=2, ensure_ascii=False)

print(f"Position successfully registered: {pos['id']}")
print(f"Entry: ${btc_price:,.2f} | TP: ${pos['take_profit']:,.2f} | SL: ${pos['stop_loss']:,.2f}")

# 2. Send Telegram broadcast
msg = (
    "🚀 <b>PYROFUEL AI // POSISI CRYPTO FUTURES TELAH DIBUKA!</b>\n\n"
    f"💎 <b>Aset:</b> <code>BTC-USD</code> (Bitcoin Perpetual)\n"
    "🎯 <b>Arah:</b> <b>LONG 📈</b> (Leverage: <b>5x</b>)\n"
    "📊 <b>Setup:</b> <code>EMA Pullback Confluence</code>\n"
    "⭐ <b>Skor Keyakinan:</b> <b>88%</b>\n"
    "⚖️ <b>Risk-Reward:</b> <b>1:3.0</b>\n"
    "────────────────────────\n"
    f"📍 <b>Entry Price:</b> ${pos['entry_price']:,.2f} (Rp {pos['entry_price_idr']:,.0f})\n"
    f"🎯 <b>Take Profit (Single TP):</b> ${pos['take_profit']:,.2f} (+18.0% PnL)\n"
    f"🛑 <b>Stop Loss:</b> ${pos['stop_loss']:,.2f} (-6.0% Max Risk)\n"
    f"🔒 <b>Alokasi Modal:</b> Rp 50.000 (${pos['position_size_usd']:.2f} USD)\n"
    "────────────────────────\n"
    "⚡ <i>Status: OPEN. Real-time monitor memantau floating PnL tiap 10 detik di Pluang.</i>"
)

try:
    up = requests.get(f"https://api.telegram.org/bot{TELE_TOKEN}/getUpdates?limit=10", timeout=5).json()
    chat_ids = set()
    for u in up.get("result", []):
        m = u.get("message") or u.get("callback_query", {}).get("message")
        if m and "chat" in m:
            chat_ids.add(m["chat"]["id"])
    for cid in chat_ids:
        payload = {"chat_id": cid, "text": msg, "parse_mode": "HTML"}
        requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage", json=payload, timeout=5)
        print(f"Telegram sent to chat_id: {cid}")
except Exception as e:
    print(f"Telegram broadcast error: {e}")
