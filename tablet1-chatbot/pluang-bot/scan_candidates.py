import sys, os, json, time
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from market_data import get_full_universe
from pipeline import run_5_layer_pipeline
from telegram_bot import format_pipeline_report, send_telegram_message
from auto_trader import _technical_pre_filter, get_binance_client

print("=" * 65)
print("PYROFUEL LIVE COIN SCAN & TRADE EXECUTION")
print("=" * 65)

universe = get_full_universe()
candidates = _technical_pre_filter(universe, max_ai_coins=8)
print(f"Gate 0 Candidates ({len(candidates)} coins):")
for i, c in enumerate(candidates, 1):
    sym = c.get("symbol", c.get("pair", "")).replace("USDT", "-USD")
    chg = c.get("price_change_24h_pct", 0)
    vol = c.get("volume_24h_usd", 0)
    print(f"  {i}. {sym} | 24h: {chg:+.2f}% | Vol: ${vol:,.0f}")

approved_trade = None

for c in candidates:
    sym = c.get("symbol", c.get("pair", "")).replace("USDT", "-USD")
    print(f"\n>>> Running 5-Layer AI Pipeline on: {sym}...")
    t0 = time.time()
    try:
        res = run_5_layer_pipeline(sym)
    except Exception as e:
        print(f"  [ERROR] Pipeline failed on {sym}: {e}")
        continue
    elapsed = time.time() - t0
    
    decision = res.get("final_decision", "REJECTED")
    direction = res.get("setup", {}).get("direction", "NONE")
    conf = res.get("confidence_score", 0)
    reason = res.get("final_reason", "")
    plan = res.get("plan", {})
    
    print(f"  Result ({elapsed:.1f}s): {decision} | Direction: {direction} | Conf: {conf}% | Reason: {reason[:80]}")
    
    if decision == "APPROVED" and direction in ("LONG", "SHORT"):
        approved_trade = res
        print(f"\n🎯 TARGET LOCKED: {sym} APPROVED FOR TRADE!")
        break

if approved_trade:
    plan = approved_trade.get("plan", {})
    setup = approved_trade.get("setup", {})
    sym = approved_trade.get("symbol")
    direction = setup.get("direction")
    pair = sym.replace("-USD", "USDT")
    tp = plan.get("take_profit_target", plan.get("target_1"))
    sl = plan.get("stop_loss")
    entry = plan.get("entry_price")
    
    print("\n" + "=" * 65)
    print(f"EXECUTING TRADE ON BINANCE FUTURES: {pair} ({direction} 20x)")
    print(f"Entry: {entry} | TP: {tp} | SL: {sl}")
    print("=" * 65)
    
    bn = get_binance_client()
    if bn:
        bal = bn.get_balance()
        avail = float(bal.get("available_balance", 0)) if isinstance(bal, dict) else 0.95
        # Use available USDT balance with 20x leverage
        margin_to_use = max(0.5, avail * 0.90)
        print(f"Available wallet: ${avail:.2f} USDT -> Using Margin: ${margin_to_use:.2f} USDT")
        
        order = bn.open_market_order(
            pair=pair,
            direction=direction,
            margin_usdt=margin_to_use,
            leverage=20,
            take_profit=tp,
            stop_loss=sl
        )
        print("Binance Execution Result:")
        print(json.dumps(order, indent=2))
        
        # Send Telegram notification
        text, _ = format_pipeline_report(approved_trade)
        chat_id = os.getenv("ALLOWED_TELEGRAM_CHAT_ID", "6794686929")
        send_telegram_message(chat_id, f"🚀 <b>PYROFUEL AUTO-TRADE EXECUTED!</b>\n\n{text}")
        print("Telegram alert sent!")
else:
    print("\nℹ️ Sesi scan selesai. Belum ada koin dengan konfluensi 3+ yang lolos audit risiko 5-layer.")
    print("Market sedang konsolidasi atau high risk. Proteksi modal aktif.")
