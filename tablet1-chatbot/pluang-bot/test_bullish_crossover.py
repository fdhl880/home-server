import sys, os, json, time
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from pipeline import run_5_layer_pipeline
from auto_trader import get_binance_client
from telegram_bot import format_pipeline_report, send_telegram_message

candidates = ['ENA-USD', 'WIF-USD', 'XRP-USD', 'DOGE-USD', 'TIA-USD', 'ADA-USD']

print("=" * 65)
print("TESTING CANDIDATES WITH BULLISH CROSSOVER / HEALTHY RSI")
print("=" * 65)

approved_trade = None

for sym in candidates:
    print(f"\n>>> Running 5-Layer AI Pipeline on: {sym}...")
    t0 = time.time()
    try:
        res = run_5_layer_pipeline(sym)
    except Exception as e:
        print(f"  [ERROR] {sym}: {e}")
        continue
    elapsed = time.time() - t0

    final_call = res.get("layer5_final_call", {})
    fc_status = final_call.get("status", "REJECTED")
    setup = res.get("layer2_setup", {})
    direction = final_call.get("direction") or setup.get("direction", "NONE")
    setup_name = setup.get("setup_name", "NO_CLEAR_SETUP")
    conf = final_call.get("confidence_score") or setup.get("probability_pct", 0)
    reason = final_call.get("final_reason") or res.get("final_reason", "")
    risk = res.get("layer4_risk", {})
    risk_score = risk.get("total_score", 0)
    risk_max = risk.get("max_score", 10)

    print(f"  Result ({elapsed:.1f}s): {fc_status} | Setup: {setup_name} | Dir: {direction} | Conf: {conf}% | Risk: {risk_score}/{risk_max}")
    print(f"  Reason: {reason[:120]}")

    if fc_status == "APPROVED" and direction in ("LONG", "SHORT"):
        approved_trade = res
        print(f"\n🎯 TARGET LOCKED: {sym} APPROVED FOR TRADE!")
        break

if approved_trade:
    final_call = approved_trade.get("layer5_final_call", {})
    plan = approved_trade.get("layer3_plan", {})
    setup = approved_trade.get("layer2_setup", {})
    sym = approved_trade.get("symbol")
    direction = final_call.get("direction") or setup.get("direction")
    pair = sym.replace("-USD", "USDT")
    tp = final_call.get("take_profit") or plan.get("take_profit_target") or plan.get("take_profit_2")
    sl = final_call.get("stop_loss") or plan.get("stop_loss")
    entry = final_call.get("entry_price") or plan.get("entry_price")

    print("\n" + "=" * 65)
    print(f"EXECUTING TRADE ON BINANCE FUTURES: {pair} ({direction} 20x)")
    print(f"Entry: {entry} | TP: {tp} | SL: {sl}")
    print("=" * 65)

    bn = get_binance_client()
    if bn:
        bal = bn.get_balance()
        avail = float(bal.get("available_balance", 0)) if isinstance(bal, dict) else 0.95
        # Margin: 88% of wallet balance, ~0.85 USDT. 20x leverage = ~$17 notional (> $5 min)
        margin_to_use = round(max(0.5, avail * 0.88), 2)
        print(f"Available wallet: ${avail:.2f} USDT -> Using Margin: ${margin_to_use:.2f} USDT (20x)")

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
        try:
            text, _ = format_pipeline_report(approved_trade)
            chat_id = os.getenv("ALLOWED_TELEGRAM_CHAT_ID", "6794686929")
            send_telegram_message(chat_id, f"🚀 <b>PYROFUEL LIVE TRADE EXECUTED!</b>\n\n{text}")
            print("Telegram alert sent!")
        except Exception as e:
            print(f"Telegram alert error: {e}")
else:
    print("\nBatch evaluation finished.")
