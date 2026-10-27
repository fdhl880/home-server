import sys, os, json, time
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from market_data import get_full_universe
from pipeline import run_5_layer_pipeline
from auto_trader import get_binance_client
from telegram_bot import format_pipeline_report, send_telegram_message

print("=" * 65)
print("PYROFUEL TARGET HUNTER — SCANNING FOR REAL OPPORTUNITY")
print("=" * 65)

universe = get_full_universe()
print(f"Total Universe: {len(universe)} pairs")

# Filter:
# 1. minNotional <= 10.0 (Our wallet is ~$0.96 USDT, with 20x leverage notional is ~$18)
# 2. 24h volume >= 5,000,000 USD (Good liquidity, small slippage)
# 3. Exclude dead coins or abnormal spreads
valid_pool = [
    c for c in universe 
    if float(c.get('minNotional') or 5.0) <= 10.0 
    and float(c.get('volume_24h_usd') or 0) >= 5_000_000
    and c.get('pair', '').endswith('USDT')
]

print(f"Valid pool (minNotional <= 10, vol >= $5M): {len(valid_pool)} pairs")

# Top Gainers (Potential LONG momentum/breakout)
gainers = sorted(valid_pool, key=lambda x: float(x.get('price_change_24h_pct') or 0), reverse=True)[:8]
# Top Losers (Potential SHORT momentum/breakdown)
losers = sorted(valid_pool, key=lambda x: float(x.get('price_change_24h_pct') or 0))[:8]

print("\n--- Top Gainers ---")
for g in gainers:
    chg = float(g.get('price_change_24h_pct') or 0)
    vol = float(g.get('volume_24h_usd') or 0)
    notional = g.get('minNotional')
    print(f"  {g['symbol']} ({g['pair']}): {chg:+.2f}% | Vol: ${vol:,.0f} | minNotional: {notional}")

print("\n--- Top Losers ---")
for l in losers:
    chg = float(l.get('price_change_24h_pct') or 0)
    vol = float(l.get('volume_24h_usd') or 0)
    notional = l.get('minNotional')
    print(f"  {l['symbol']} ({l['pair']}): {chg:+.2f}% | Vol: ${vol:,.0f} | minNotional: {notional}")

# Also include top popular active futures: SOL, XRP, DOGE, NEAR, SUI
popular = ['SOL-USD', 'XRP-USD', 'DOGE-USD', 'NEAR-USD', 'SUI-USD']

# Build queue: Top gainers, top losers, then popular
queue = []
for i in range(max(len(gainers), len(losers))):
    if i < len(gainers) and gainers[i]['symbol'] not in queue:
        queue.append(gainers[i]['symbol'])
    if i < len(losers) and losers[i]['symbol'] not in queue:
        queue.append(losers[i]['symbol'])

for p in popular:
    if p not in queue:
        queue.append(p)

print(f"\nFinal Test Queue ({len(queue)} coins): {queue[:15]}")

approved_trade = None

for idx, sym in enumerate(queue[:15], 1):
    print(f"\n[{idx}/15] >>> Running 5-Layer AI Pipeline on: {sym}...")
    t0 = time.time()
    try:
        res = run_5_layer_pipeline(sym)
    except Exception as e:
        print(f"  [ERROR] Pipeline exception on {sym}: {e}")
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
    print(f"  Reason: {reason[:100]}")

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
        # Margin sizing: Use 88% of available USDT, with minimum 0.5 USDT
        margin_to_use = round(max(0.5, avail * 0.88), 2)
        print(f"Available wallet: ${avail:.2f} USDT -> Using Margin: ${margin_to_use:.2f} USDT (20x leverage)")

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
    print("\nℹ️ Tidak ada koin yang APPROVED pada batch 15 koin ini.")
