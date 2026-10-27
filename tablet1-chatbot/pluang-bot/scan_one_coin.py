import sys, os, json, time
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from market_data import get_full_universe, get_top_movers
from pipeline import run_5_layer_pipeline
from telegram_bot import format_pipeline_report
from auto_trader import _technical_pre_filter, get_binance_client

print("=" * 60)
print("PYROFUEL COIN SCANNER — FINDING 1 TOP OPPORTUNITY COIN")
print("=" * 60)

universe = get_full_universe()
print(f"Total universe: {len(universe)} coins")

# Get pre-filtered coins
filtered = _technical_pre_filter(universe, max_ai_coins=8)
print(f"Candidates selected by Gate 0 ({len(filtered)}):")
for c in filtered:
    sym = c.get("symbol", c.get("pair", ""))
    print(f"  * {sym} (change_24h={c.get('price_change_24h_pct', 0):.2f}%, vol=${c.get('volume_24h_usd', 0):,.0f})")

target_coin = filtered[0].get("symbol", filtered[0].get("pair", "").replace("USDT", "-USD"))
print(f"\nTargeting #1 Opportunity: {target_coin}")
print("Executing 5-Layer AI Pipeline...")

t0 = time.time()
res = run_5_layer_pipeline(target_coin)
elapsed = time.time() - t0

print(f"\nPipeline finished in {elapsed:.2f}s!")
print(f"Status: {res.get('status')}")
print(f"Final Decision: {res.get('final_decision')}")
print(f"Direction: {res.get('setup', {}).get('direction')}")
print(f"Confidence: {res.get('confidence_score')}%")

plan = res.get('plan', {})
print(f"Entry: {plan.get('entry_price')}")
print(f"Take Profit: {plan.get('take_profit_target', plan.get('target_1'))}")
print(f"Stop Loss: {plan.get('stop_loss')}")
print(f"ETA TP: {plan.get('tp_eta')}")
print(f"Reason: {res.get('final_reason')}")

text, status = format_pipeline_report(res)
print("\n" + "=" * 60)
print("TELEGRAM NOTIFICATION PREVIEW:")
print("=" * 60)
print(text[:1200])

if res.get("final_decision") == "APPROVED":
    print("\n✅ TRADE APPROVED! Executing on Binance Futures...")
    bn = get_binance_client()
    if bn:
        direction = res.get('setup', {}).get('direction', 'LONG')
        pair = target_coin.replace("-USD", "USDT")
        price = plan.get('entry_price')
        sl = plan.get('stop_loss')
        tp = plan.get('take_profit_target', plan.get('target_1'))
        
        # Check balance
        bal = bn.get_balance()
        avail = float(bal.get("available_balance", 0)) if isinstance(bal, dict) else 0.95
        margin_usd = min(avail * 0.95, 0.95)
        print(f"Available balance: ${avail:.2f} USDT, using margin: ${margin_usd:.2f} USDT (20x leverage)")
        
        # Open position
        order_res = bn.open_market_order(
            pair=pair,
            direction=direction,
            margin_usdt=margin_usd,
            leverage=20,
            take_profit=tp,
            stop_loss=sl
        )
        print("Binance Order Result:\n", json.dumps(order_res, indent=2))
        
        # Notify telegram
        from telegram_bot import send_telegram_message
        chat_id = os.getenv("ALLOWED_TELEGRAM_CHAT_ID", "6794686929")
        send_telegram_message(chat_id, f"🚀 <b>PYROFUEL MANUAL TRIGGERED TRADE</b>\n\n{text}")
else:
    print(f"\n❌ Coin {target_coin} was REJECTED by Layer 5: {res.get('final_reason')}")
    print("Checking if next candidate in list can be scanned...")
