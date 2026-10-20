"""
===========================================================================
PYROFUEL CRYPTO FUTURES AI TRADING SERVER v3.0
===========================================================================
Backend server for:
1. Serving 5-Layer AI Pipeline API
2. FULL UNIVERSE Crypto Futures (~200+ pairs from Binance)
3. Smart ranking & top movers
4. Autonomous trading state and active positions
5. PLUANG EXECUTION: Leverage, Margin Type, Order Type, TP/SL
6. Currency conversion (USD ↔ IDR)
7. Glassmorphism Dashboard + Bloomberg Terminal Integration
8. Futures Settings API: configure leverage, margin, order type
===========================================================================
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from pipeline import run_5_layer_pipeline, get_trading_config, save_trading_config, load_env, RESULTS_DIR
from market_data import (
    get_market_indicators, get_market_indicators_fast,
    CRYPTO_FUTURES_WATCHLIST, get_full_universe, get_top_movers,
    get_universe_summary, get_fx_info, convert_usd_to_idr, convert_idr_to_usd,
    rank_universe_by_opportunity
)
from concurrent.futures import ThreadPoolExecutor, as_completed
from pluang_mcp import PluangMCPClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TOKEN_FILE = os.path.join(BASE_DIR, "tokens.json")
POSITIONS_FILE = os.path.join(RESULTS_DIR, "active_positions.json")
STATE_FILE = os.path.join(RESULTS_DIR, "autotrader_state.json")
QUICK_SCREEN_FILE = os.path.join(RESULTS_DIR, "quick_screen.json")
UNIVERSE_FILE = os.path.join(RESULTS_DIR, "universe_state.json")
EXECUTION_LOG_FILE = os.path.join(RESULTS_DIR, "execution_log.json")

app = Flask(__name__, static_folder=STATIC_DIR)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

def get_pluang_client():
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
            token = data.get("access_token")
            if token:
                client = PluangMCPClient(token)
                client.initialize()
                return client
        except Exception as e:
            print(f"Error loading Pluang MCP: {e}")
    return None

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")

@app.route("/api/status")
def get_status():
    env = load_env()
    has_token = os.path.exists(TOKEN_FILE)
    pluang_connected = False
    if has_token:
        try:
            with open(TOKEN_FILE, "r") as f:
                t = json.load(f)
            pluang_connected = bool(t.get("access_token"))
        except Exception:
            pass

    # Read active positions
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            pass

    # Read state
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    cfg = get_trading_config()
    universe = get_full_universe()
    fx = get_fx_info()
    
    return jsonify({
        "status": "online",
        "version": "3.0",
        "market": "CRYPTO_FUTURES_PLUANG_ONLY",
        "universe_size": len(universe),
        "core_assets_count": len(CRYPTO_FUTURES_WATCHLIST),
        "pluang_connected": pluang_connected,
        "max_budget_idr": cfg.get("max_budget_idr", 50000),
        "max_budget_usd": convert_idr_to_usd(cfg.get("max_budget_idr", 50000)),
        "max_leverage": cfg.get("max_leverage", 5),
        "min_confidence_score": cfg.get("min_confidence_score", 65),
        "min_risk_reward_ratio": cfg.get("min_risk_reward_ratio", 1.8),
        "margin_type": cfg.get("margin_type", "ISOLATED"),
        "order_type": cfg.get("order_type", "MARKET"),
        "tp_sl_mode": cfg.get("tp_sl_mode", "DUAL_TP"),
        "tp1_close_pct": cfg.get("tp1_close_pct", 50),
        "tp1_move_sl_to_breakeven": cfg.get("tp1_move_sl_to_breakeven", True),
        "max_concurrent_positions": cfg.get("max_concurrent_positions", 3),
        "max_daily_trades": cfg.get("max_daily_trades", 10),
        "auto_execute_on_pluang": cfg.get("auto_execute_on_pluang", True),
        "ai_provider": env.get("AI_PROVIDER", "groq"),
        "model": env.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        "telegram_bot": "@idrisginting_bot",
        "active_positions_count": len([p for p in positions if p.get("status") == "OPEN"]),
        "autonomous_running": state.get("is_running", True),
        "total_scans_done": state.get("total_scans_done", 0),
        "total_quick_screens": state.get("total_quick_screens", 0),
        "last_scan_time": state.get("last_scan_time", "N/A"),
        "coins_scanned_last_cycle": state.get("coins_scanned_this_cycle", 0),
        "autotrader_state": state,
        "fx": fx
    })

@app.route("/api/config", methods=["GET", "POST"])
def handle_config():
    if request.method == "POST":
        data = request.get_json() or {}
        new_cfg = save_trading_config(data)
        return jsonify({"success": True, "config": new_cfg})
    return jsonify(get_trading_config())

_WATCHLIST_CACHE = {"data": [], "timestamp": 0, "ttl": 10}

@app.route("/api/watchlist")
def get_watchlist():
    """Return live data for Pluang Crypto Futures pairs (Ultra-fast from 24h tickers + cached)"""
    now = time.time()
    if now - _WATCHLIST_CACHE["timestamp"] < _WATCHLIST_CACHE["ttl"] and _WATCHLIST_CACHE["data"]:
        return jsonify(_WATCHLIST_CACHE["data"])

    try:
        ranked = rank_universe_by_opportunity()
        results = []
        for c in ranked:
            sym = c.get("symbol", c.get("pair", "").replace("USDT", "-USD"))
            scan_file = os.path.join(RESULTS_DIR, f"{sym.replace('-', '_')}_latest.json")
            latest_scan = None
            if os.path.exists(scan_file):
                try:
                    with open(scan_file, "r", encoding="utf-8") as f:
                        latest_scan = json.load(f)
                except Exception:
                    pass

            price = c.get("last_price", 0)
            change_24h = c.get("price_change_24h_pct", 0)
            results.append({
                "symbol": sym,
                "name": c.get("name", sym),
                "pair": c.get("pair", ""),
                "category": "Crypto Futures",
                "tier": c.get("tier", "T2_LARGE"),
                "price": price,
                "price_idr": convert_usd_to_idr(price),
                "currency": "USD",
                "change_4h": round(change_24h * 0.25, 2),
                "change_24h": round(change_24h, 2),
                "rsi_14": 55 if change_24h > 3 else (45 if change_24h < -3 else 50),
                "trend": "STRONG_BULLISH" if change_24h > 5 else ("BULLISH" if change_24h > 0 else "BEARISH"),
                "volatility": "HIGH" if abs(change_24h) > 5 else "MODERATE",
                "high_24h": c.get("high_24h", price * 1.02),
                "low_24h": c.get("low_24h", price * 0.98),
                "volume_usd": c.get("volume_24h_usd", 0),
                "leverage_max": c.get("leverage_max", 10),
                "last_scan": latest_scan
            })
        if results:
            _WATCHLIST_CACHE["data"] = results
            _WATCHLIST_CACHE["timestamp"] = now
            return jsonify(results)
    except Exception as e:
        print(f"Watchlist error: {e}")

    return jsonify(_WATCHLIST_CACHE["data"] if _WATCHLIST_CACHE["data"] else [])

@app.route("/api/universe")
def get_universe():
    """Return full universe summary"""
    try:
        summary = get_universe_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/universe/full")
def get_universe_full():
    """Return all pairs in the universe"""
    try:
        universe = get_full_universe()
        return jsonify({"count": len(universe), "pairs": universe})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/movers")
def get_movers():
    """Return top movers ranked by opportunity"""
    limit = request.args.get("limit", 50, type=int)
    try:
        movers = get_top_movers(limit)
        return jsonify({"count": len(movers), "movers": movers})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/fx")
def get_fx():
    """Return exchange rate info"""
    return jsonify(get_fx_info())

@app.route("/api/convert")
def convert_currency():
    """Convert currency: ?amount=50000&from=idr or ?amount=100&from=usd"""
    amount = request.args.get("amount", 0, type=float)
    from_curr = request.args.get("from", "idr").upper()
    
    if from_curr == "IDR":
        return jsonify({
            "from": {"amount": amount, "currency": "IDR"},
            "to": {"amount": convert_idr_to_usd(amount), "currency": "USD"},
            "rate": get_fx_info()
        })
    else:
        return jsonify({
            "from": {"amount": amount, "currency": "USD"},
            "to": {"amount": convert_usd_to_idr(amount), "currency": "IDR"},
            "rate": get_fx_info()
        })

@app.route("/api/scan", methods=["POST"])
def scan_symbol():
    data = request.get_json() or {}
    symbol = data.get("symbol", "BTC-USD")
    try:
        pipeline_res = run_5_layer_pipeline(symbol)
        return jsonify(pipeline_res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/positions", methods=["GET"])
def get_positions():
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []
    return jsonify(positions)

@app.route("/api/performance")
def get_performance():
    """Consolidated performance metrics: Win Rate, Realized PnL, Floating PnL, Total Trades"""
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            positions = []

    closed_pos = [p for p in positions if str(p.get("status", "")).startswith("CLOSED")]
    open_pos = [p for p in positions if p.get("status") == "OPEN"]

    winning = [p for p in closed_pos if p.get("pnl_idr", 0) > 0 or p.get("pnl_pct", 0) > 0]
    losing = [p for p in closed_pos if p.get("pnl_idr", 0) <= 0 and p.get("pnl_pct", 0) <= 0]

    closed_count = len(closed_pos)
    win_rate = round((len(winning) / closed_count * 100), 1) if closed_count > 0 else 0.0

    realized_idr = sum(p.get("pnl_idr", 0) for p in closed_pos)
    realized_usd = sum(p.get("pnl_usd", 0) for p in closed_pos)

    unrealized_idr = sum(p.get("pnl_idr", 0) for p in open_pos)
    unrealized_usd = sum(p.get("pnl_usd", 0) for p in open_pos)

    total_pnl_idr = realized_idr + unrealized_idr
    total_pnl_usd = realized_usd + unrealized_usd

    return jsonify({
        "win_rate_pct": win_rate,
        "total_trades": len(positions),
        "open_trades": len(open_pos),
        "closed_trades": closed_count,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "realized_pnl_idr": round(realized_idr, 2),
        "realized_pnl_usd": round(realized_usd, 4),
        "unrealized_pnl_idr": round(unrealized_idr, 2),
        "unrealized_pnl_usd": round(unrealized_usd, 4),
        "net_total_pnl_idr": round(total_pnl_idr, 2),
        "net_total_pnl_usd": round(total_pnl_usd, 4),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    })

@app.route("/api/news")
def get_news():
    """Return live breaking crypto news with sentiment analysis."""
    from news_sentinel import get_news_sentiment_summary
    return jsonify(get_news_sentiment_summary())

@app.route("/api/quick-screen")
def get_quick_screen():
    """Return latest quick screen results"""
    if os.path.exists(QUICK_SCREEN_FILE):
        try:
            with open(QUICK_SCREEN_FILE, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({"alerts": [], "screened": 0})

@app.route("/api/execute", methods=["POST"])
def execute_order():
    data = request.get_json() or {}
    symbol = data.get("symbol")
    direction = data.get("direction", "LONG")
    amount_idr = float(data.get("amount_idr", 0))
    leverage = int(data.get("leverage", 1))
    margin_type = data.get("margin_type", "ISOLATED").upper()
    order_type = data.get("order_type", "MARKET").upper()
    tp_price = float(data.get("tp_price") or data.get("take_profit") or data.get("tp1_price") or data.get("tp2_price", 0))
    sl_price = float(data.get("sl_price") or data.get("stop_loss", 0))

    cfg = get_trading_config()
    MAX_BUDGET_IDR = cfg.get("max_budget_idr", 500000)
    MAX_LEVERAGE = cfg.get("max_leverage", 25)

    # HARD PYTHON SECURITY GATES (ANTI-TAMPERING)
    if amount_idr > MAX_BUDGET_IDR:
        return jsonify({
            "success": False,
            "error": f"Nominal Rp {amount_idr:,.0f} ditolak! Melebihi batas Rp {MAX_BUDGET_IDR:,.0f}."
        }), 400

    if leverage > MAX_LEVERAGE:
        return jsonify({
            "success": False,
            "error": f"Leverage {leverage}x ditolak! Melebihi batas {MAX_LEVERAGE}x."
        }), 400

    if margin_type not in ("CROSS", "ISOLATED"):
        return jsonify({"success": False, "error": "Margin type harus CROSS atau ISOLATED"}), 400

    if order_type not in ("MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"):
        return jsonify({"success": False, "error": "Order type tidak valid"}), 400

    client = get_pluang_client()
    pluang_active = client is not None
    pluang_result = None

    # Execute on Pluang if connected
    if pluang_active and cfg.get("auto_execute_on_pluang", True):
        try:
            pos_usd = convert_idr_to_usd(amount_idr)
            pluang_result = client.execute_full_trade(
                signal={
                    "binance_pair": symbol.replace("-USD", "USDT") if "-USD" in symbol else symbol,
                    "symbol": symbol,
                    "direction": direction,
                    "leverage": leverage,
                    "order_type": order_type,
                    "take_profit": tp_price,
                    "take_profit_1": tp_price,
                    "take_profit_2": tp_price,
                    "stop_loss": sl_price,
                    "position_size_idr": amount_idr,
                    "position_size_usdt": pos_usd
                },
                config={
                    "margin_type": margin_type,
                    "order_type": order_type,
                    "max_leverage": MAX_LEVERAGE
                }
            )
        except Exception as e:
            pluang_result = {"error": str(e)}

    # Record position
    positions = []
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                positions = json.load(f)
        except Exception:
            pass

    new_pos = {
        "id": f"POS_{symbol}_{int(time.time())}",
        "symbol": symbol,
        "direction": direction,
        "leverage": leverage,
        "margin_type": margin_type,
        "order_type": order_type,
        "amount_idr": amount_idr,
        "amount_usd": convert_idr_to_usd(amount_idr),
        "position_size_idr": amount_idr,
        "position_size_usd": convert_idr_to_usd(amount_idr),
        "take_profit": tp_price,
        "take_profit_1": tp_price,
        "take_profit_2": tp_price,
        "stop_loss": sl_price,
        "opened_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "status": "OPEN",
        "pluang_synced": pluang_active and pluang_result and "error" not in pluang_result,
        "pluang_execution": pluang_result
    }
    positions.append(new_pos)
    try:
        with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(positions, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "position": new_pos,
        "pluang_synced": new_pos["pluang_synced"],
        "message": f"Order {direction} {symbol} Rp {amount_idr:,.0f} {leverage}x {margin_type} {order_type} berhasil!"
    })

@app.route("/api/auto/toggle", methods=["POST"])
def toggle_auto():
    state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass
    state["is_running"] = not state.get("is_running", True)
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return jsonify({"autonomous_running": state["is_running"]})

@app.route("/api/futures/settings", methods=["GET", "POST"])
def futures_settings():
    """Get or update futures trading settings (leverage, margin, order type, TP/SL)"""
    if request.method == "POST":
        data = request.get_json() or {}
        cfg = get_trading_config()
        
        # Validate and update
        if "margin_type" in data:
            mt = data["margin_type"].upper()
            if mt in ("CROSS", "ISOLATED"):
                cfg["margin_type"] = mt
        if "order_type" in data:
            ot = data["order_type"].upper()
            if ot in ("MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"):
                cfg["order_type"] = ot
        if "max_leverage" in data:
            lev = int(data["max_leverage"])
            if 1 <= lev <= 125:
                cfg["max_leverage"] = lev
        if "tp_sl_mode" in data:
            mode = data["tp_sl_mode"].upper()
            if mode in ("SINGLE_TP", "DUAL_TP", "TRAILING"):
                cfg["tp_sl_mode"] = mode
        if "tp1_close_pct" in data:
            pct = int(data["tp1_close_pct"])
            if 10 <= pct <= 100:
                cfg["tp1_close_pct"] = pct
        if "tp1_move_sl_to_breakeven" in data:
            cfg["tp1_move_sl_to_breakeven"] = bool(data["tp1_move_sl_to_breakeven"])
        if "max_concurrent_positions" in data:
            mcp = int(data["max_concurrent_positions"])
            if 1 <= mcp <= 20:
                cfg["max_concurrent_positions"] = mcp
        if "max_daily_trades" in data:
            mdt = int(data["max_daily_trades"])
            if 1 <= mdt <= 100:
                cfg["max_daily_trades"] = mdt
        if "auto_execute_on_pluang" in data:
            cfg["auto_execute_on_pluang"] = bool(data["auto_execute_on_pluang"])
        if "max_budget_idr" in data:
            cfg["max_budget_idr"] = int(data["max_budget_idr"])
        if "min_confidence_score" in data:
            cfg["min_confidence_score"] = int(data["min_confidence_score"])
        if "min_risk_reward_ratio" in data:
            cfg["min_risk_reward_ratio"] = float(data["min_risk_reward_ratio"])
        
        new_cfg = save_trading_config(cfg)
        return jsonify({"success": True, "config": new_cfg})
    
    return jsonify(get_trading_config())

@app.route("/api/pluang/status")
def pluang_status():
    """Check Pluang MCP connection status and available tools"""
    client = get_pluang_client()
    if client:
        conn = client.check_connection()
        tools = client.get_available_tools()
        return jsonify({
            "connected": conn.get("connected", False),
            "server_info": conn.get("server_info", {}),
            "available_tools": tools,
            "last_error": conn.get("last_error")
        })
    return jsonify({
        "connected": False,
        "server_info": {},
        "available_tools": {"count": 0, "tools": []},
        "last_error": "No token file or client not initialized"
    })

@app.route("/api/pluang/balance")
def pluang_balance():
    """Get Pluang account balance"""
    client = get_pluang_client()
    if client:
        return jsonify(client.get_balance())
    return jsonify({"error": "Pluang not connected"}), 503

@app.route("/api/pluang/positions")
def pluang_positions():
    """Get positions from Pluang"""
    client = get_pluang_client()
    if client:
        return jsonify(client.get_positions())
    return jsonify({"error": "Pluang not connected"}), 503

@app.route("/api/execution-log")
def get_execution_log():
    """Get trade execution log"""
    limit = request.args.get("limit", 50, type=int)
    if os.path.exists(EXECUTION_LOG_FILE):
        try:
            with open(EXECUTION_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            return jsonify({"count": len(logs[:limit]), "logs": logs[:limit]})
        except Exception:
            pass
    return jsonify({"count": 0, "logs": []})

@app.route("/api/pluang/set-leverage", methods=["POST"])
def set_leverage():
    """Manually set leverage for a symbol"""
    data = request.get_json() or {}
    symbol = data.get("symbol")
    leverage = int(data.get("leverage", 5))
    client = get_pluang_client()
    if not client:
        return jsonify({"error": "Pluang not connected"}), 503
    result = client.set_leverage(symbol, leverage)
    return jsonify(result)

@app.route("/api/pluang/set-margin", methods=["POST"])
def set_margin():
    """Manually set margin type for a symbol"""
    data = request.get_json() or {}
    symbol = data.get("symbol")
    margin_type = data.get("margin_type", "ISOLATED")
    client = get_pluang_client()
    if not client:
        return jsonify({"error": "Pluang not connected"}), 503
    result = client.set_margin_type(symbol, margin_type)
    return jsonify(result)

@app.route("/api/pluang/close-position", methods=["POST"])
def close_pluang_position():
    """Close a position on Pluang"""
    data = request.get_json() or {}
    symbol = data.get("symbol")
    direction = data.get("direction")
    client = get_pluang_client()
    if not client:
        return jsonify({"error": "Pluang not connected"}), 503
    result = client.close_position(symbol, direction)
    return jsonify(result)

if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] PYROFUEL v3.0 Dashboard Server: http://localhost:{port}", flush=True)
    print(f"[*] Mode: FULL UNIVERSE + PLUANG EXECUTION", flush=True)
    print(f"[*] Futures Settings API: /api/futures/settings", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
