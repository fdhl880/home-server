"""
PYROFUEL BOT - HISTORICAL MULTI-TIMEFRAME & DERIVATIVES DATA FETCHER (Task T1.2 / WP-6)
Mengunduh data historis 12+ bulan (default 365 hari, 1h & 15m) menggunakan paginasi startTime/endTime
lengkap dengan kolom `taker_buy_base` dan `taker_buy_quote` (indeks 9 & 10 dari /fapi/v1/klines)
untuk rekonstruksi eksak Historical TFI & CVD, serta histori Funding Rate (`/fapi/v1/fundingRate`).
"""
import argparse
import csv
import os
import time
from typing import Any, Dict, List, Optional, Sequence
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_DAYS = 365
DEFAULT_INTERVALS = ("1h", "15m")

KLINE_ENDPOINTS = [
    "https://fapi.binance.com/fapi/v1/klines",
    "https://fapi1.binance.com/fapi/v1/klines",
    "https://data-api.binance.vision/api/v3/klines",
]

FUNDING_ENDPOINTS = [
    "https://fapi.binance.com/fapi/v1/fundingRate",
    "https://fapi1.binance.com/fapi/v1/fundingRate",
]

OI_ENDPOINTS = [
    "https://fapi.binance.com/futures/data/openInterestHist",
]

DEFAULT_SYMBOLS_20 = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "SUIUSDT", "AVAXUSDT", "LINKUSDT",
    "DOTUSDT", "NEARUSDT", "LTCUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "INJUSDT", "FETUSDT", "FILUSDT", "ATOMUSDT",
]

CSV_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote",
]

FUNDING_CSV_COLUMNS = ["funding_time", "symbol", "funding_rate", "mark_price"]

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def _fetch_kline_batch(
    symbol: str,
    interval: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    limit: int = 1500,
) -> Optional[List[List[Any]]]:
    params: Dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "limit": min(1500, max(1, int(limit))),
    }
    if start_time is not None:
        params["startTime"] = int(start_time)
    if end_time is not None:
        params["endTime"] = int(end_time)

    for ep in KLINE_ENDPOINTS:
        try:
            r = requests.get(ep, params=params, timeout=(3.5, 10.0))
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            continue
    return None


def normalize_kline_row(row: List[Any]) -> List[Any]:
    """
    Extract the 11 standard columns including `taker_buy_base` (idx 9) and `taker_buy_quote` (idx 10).
    """
    return [
        int(row[0]),
        row[1],
        row[2],
        row[3],
        row[4],
        row[5],
        int(row[6]),
        row[7] if len(row) > 7 else "0",
        int(row[8]) if len(row) > 8 else 0,
        row[9] if len(row) > 9 else "0",
        row[10] if len(row) > 10 else "0",
    ]


def fetch_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 1000,
    days: Optional[int] = None,
    data_dir: Optional[str] = None,
    sleep_sec: float = 0.15,
) -> Optional[str]:
    """
    Fetch historical closed klines with pagination support (`days` up to 365+ days)
    and write clean deduplicated CSV to `{data_dir}/{symbol}_{interval}.csv`.
    """
    target_dir = data_dir or DATA_DIR
    os.makedirs(target_dir, exist_ok=True)

    now_ms = int(time.time() * 1000)
    step_ms = INTERVAL_MS.get(interval, 3_600_000)

    if days is not None and days > 0:
        total_bars = int((int(days) * 86_400_000) // step_ms)
    else:
        total_bars = int(limit)

    start_ms = now_ms - total_bars * step_ms
    collected: Dict[int, List[Any]] = {}
    cursor = start_ms

    while cursor < now_ms - step_ms:
        batch_limit = min(1500, max(100, (now_ms - cursor) // step_ms + 2))
        raw = _fetch_kline_batch(symbol, interval, start_time=cursor, limit=batch_limit)
        if not raw:
            break

        for row in raw:
            open_t = int(row[0])
            close_t = int(row[6])
            # Strictly keep only closed bars (no forming candle lookahead!)
            if close_t <= now_ms:
                collected[open_t] = normalize_kline_row(row)

        last_open = int(raw[-1][0])
        if last_open <= cursor:
            break
        cursor = last_open + step_ms
        if len(collected) >= total_bars:
            break
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    if not collected:
        print(f"[FAIL] Gagal mengunduh {symbol} {interval}")
        return None

    sorted_times = sorted(collected.keys())
    out_path = os.path.join(target_dir, f"{symbol}_{interval}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for t in sorted_times:
            writer.writerow(collected[t])

    print(f"[OK] {symbol} {interval}: {len(sorted_times)} closed candles -> {out_path}")
    return out_path


def fetch_funding_history(
    symbol: str = "BTCUSDT",
    days: int = DEFAULT_DAYS,
    data_dir: Optional[str] = None,
    sleep_sec: float = 0.1,
) -> Optional[str]:
    """
    Fetch historical fundingRate records via pagination from `FUNDING_ENDPOINTS`
    and persist to `{data_dir}/{symbol}_funding.csv`.
    """
    target_dir = data_dir or DATA_DIR
    os.makedirs(target_dir, exist_ok=True)

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - int(days) * 86_400_000
    rows_map: Dict[int, Dict[str, Any]] = {}
    cursor = start_ms

    while cursor < now_ms:
        fetched = None
        for ep in FUNDING_ENDPOINTS:
            try:
                r = requests.get(
                    ep,
                    params={"symbol": symbol, "startTime": cursor, "endTime": now_ms, "limit": 1000},
                    timeout=(3.5, 10.0),
                )
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0:
                        fetched = data
                        break
            except Exception:
                continue
        if not fetched:
            break
        for item in fetched:
            ft = int(item.get("fundingTime", 0) or 0)
            if 0 < ft <= now_ms:
                rows_map[ft] = item
        last_ft = int(fetched[-1].get("fundingTime", 0) or 0)
        if last_ft <= cursor:
            break
        cursor = last_ft + 1000
        if len(fetched) < 1000:
            break
        if sleep_sec > 0:
            time.sleep(sleep_sec)

    if not rows_map:
        return None

    out_path = os.path.join(target_dir, f"{symbol}_funding.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(FUNDING_CSV_COLUMNS)
        for ft in sorted(rows_map.keys()):
            it = rows_map[ft]
            writer.writerow([ft, symbol, it.get("fundingRate", "0"), it.get("markPrice", "0")])
    print(f"[OK] {symbol} funding: {len(rows_map)} records -> {out_path}")
    return out_path


def load_funding_history(csv_path: str) -> Dict[int, float]:
    """Load `{symbol}_funding.csv` into a sorted `{funding_time_ms: decimal_funding_rate}` dict."""
    if not csv_path or not os.path.exists(csv_path):
        return {}
    out: Dict[int, float] = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                ft = int(float(row.get("funding_time") or row.get("fundingTime") or 0))
                rate = float(row.get("funding_rate") or row.get("fundingRate") or 0.0)
                if ft > 0:
                    out[ft] = rate
            except (TypeError, ValueError):
                continue
    return dict(sorted(out.items()))


def fetch_all_symbols(
    symbols: Optional[Sequence[str]] = None,
    days: int = DEFAULT_DAYS,
    intervals: Sequence[str] = DEFAULT_INTERVALS,
    include_funding: bool = True,
    data_dir: Optional[str] = None,
    sleep_sec: float = 0.2,
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Download 12+ months (`days=365` default) of multi-timeframe klines (`1h`, `15m`)
    and historical funding rates (`{sym}_funding.csv`) for the symbol universe.
    """
    sym_list = list(symbols) if symbols is not None else list(DEFAULT_SYMBOLS_20)
    iv_list = [str(iv).strip() for iv in intervals if str(iv).strip()]
    results: Dict[str, Dict[str, Optional[str]]] = {}

    for sym in sym_list:
        sym_res: Dict[str, Optional[str]] = {}
        for iv in iv_list:
            sym_res[iv] = fetch_klines(
                sym,
                interval=iv,
                days=int(days),
                data_dir=data_dir,
                sleep_sec=sleep_sec,
            )
            if sleep_sec > 0:
                time.sleep(sleep_sec)
        if include_funding:
            sym_res["funding"] = fetch_funding_history(
                sym,
                days=int(days),
                data_dir=data_dir,
                sleep_sec=sleep_sec,
            )
            if sleep_sec > 0:
                time.sleep(sleep_sec)
        results[sym] = sym_res
    return results


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pyrofuel v3 Historical Data Fetcher (12+ Months & Funding)")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of historical days to fetch (default 365)")
    parser.add_argument("--symbols", type=int, default=5, help="Number of top liquid symbols to fetch")
    parser.add_argument(
        "--interval",
        type=str,
        default="1h,15m",
        help="Candle timeframe(s), comma-separated (default '1h,15m')",
    )
    parser.add_argument("--no-funding", action="store_true", help="Skip downloading historical fundingRate CSVs")
    return parser


if __name__ == "__main__":
    args = build_cli_parser().parse_args()
    selected_symbols = DEFAULT_SYMBOLS_20[: max(1, min(args.symbols, len(DEFAULT_SYMBOLS_20)))]
    iv_tokens = [x.strip() for x in str(args.interval).split(",") if x.strip()] or list(DEFAULT_INTERVALS)
    fetch_all_symbols(
        symbols=selected_symbols,
        days=args.days,
        intervals=iv_tokens,
        include_funding=not args.no_funding,
    )
