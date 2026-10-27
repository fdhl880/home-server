"""
PYROFUEL BOT - HISTORICAL DATA FETCHER
Mengunduh data candle 1h untuk backtesting dan kalibrasi probabilitas.
"""
import os
import sys
import time
import json
import csv
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

ENDPOINTS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://fapi.binance.com/fapi/v1/klines"
]


def fetch_klines(symbol="BTCUSDT", interval="1h", limit=1000):
    for ep in ENDPOINTS:
        try:
            url = f"{ep}?symbol={symbol}&interval={interval}&limit={limit}"
            r = requests.get(url, timeout=10, verify=False)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) > 0:
                    out_path = os.path.join(DATA_DIR, f"{symbol}_{interval}.csv")
                    with open(out_path, "w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "close_time"])
                        for row in raw:
                            writer.writerow([row[0], row[1], row[2], row[3], row[4], row[5], row[6]])
                    print(f"[OK] {symbol} {interval}: {len(raw)} candles -> {out_path}")
                    return out_path
        except Exception as e:
            continue
    print(f"[FAIL] Gagal mengunduh {symbol}")
    return None


if __name__ == "__main__":
    coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    for c in coins:
        fetch_klines(c, "1h", limit=500)
        time.sleep(0.5)
