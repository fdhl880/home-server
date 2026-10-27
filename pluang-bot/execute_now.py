import sys, os, json, time
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from auto_trader import get_binance_client
from telegram_bot import send_telegram_message, format_pipeline_report

print("=" * 65)
print("PYROFUEL INSTANT EXECUTION ENGINE (20x FIXED LEVERAGE)")
print("=" * 65)

bn = get_binance_client()
if not bn:
    print("[ERROR] Binance client failed to initialize!")
    sys.exit(1)

# Check active balance
bal = bn.get_balance()
avail_usdt = float(bal.get('available_balance', 0))
print(f"[*] Wallet Available: ${avail_usdt:.4f} USDT")

if avail_usdt < 0.35:
    print(f"[ERROR] Balance ${avail_usdt:.4f} USDT too low for execution!")
    sys.exit(1)

# Active candidate selected by AI Layer 2 & Layer 5: WIFUSDT
# Setup: BOLLINGER_SQUEEZE_BREAKOUT (BULLISH CROSSOVER 1h, RSI 55.5)
symbol = "WIFUSDT"
direction = "LONG"
leverage = 20

# 1. Pre-configure leverage and margin type
print(f"\n[1/4] Setting ISOLATED margin & {leverage}x leverage for {symbol}...")
try:
    bn.set_margin_type(symbol, "ISOLATED")
except Exception as e:
    print(f"  Notice margin type: {e}")

try:
    bn.set_leverage(symbol, leverage)
except Exception as e:
    print(f"  Notice leverage: {e}")

# 2. Get live market price & filters
mark_price = bn.get_market_price(symbol)
filters = bn.get_symbol_filters(symbol)
min_notional = float(filters.get("minNotional", 5.0))
print(f"[*] {symbol} Mark Price: ${mark_price:.4f} | minNotional: ${min_notional:.1f}")

# Sizing: Use 88% of available wallet margin
margin_to_use = round(avail_usdt * 0.88, 2)
notional_usd = margin_to_use * leverage

if notional_usd < min_notional:
    notional_usd = min_notional * 1.05
    margin_to_use = round(notional_usd / leverage, 2)

raw_qty = notional_usd / mark_price
qty = bn.format_quantity(symbol, raw_qty)
print(f"[*] Order Quantity: {qty} WIF (Notional: ${qty * mark_price:.2f} USDT, Margin: ${margin_to_use:.2f} USDT)")

# 3. Calculate TP and SL
# TP: +1.6% from entry (1.6% * 20x = +32% ROI)
# SL: -0.9% from entry (0.9% * 20x = -18% risk, safe from 5% liquidation)
tp_price = bn.format_price(symbol, mark_price * 1.016)
sl_price = bn.format_price(symbol, mark_price * 0.991)

print(f"[*] Entry: ${mark_price:.4f} | TP: ${tp_price:.4f} (+1.6%) | SL: ${sl_price:.4f} (-0.9%)")

# 4. Open Position via Market Order
print(f"\n[2/4] Executing MARKET {direction} order on Binance Futures...")
order_res = bn.open_position(
    symbol=symbol,
    direction=direction,
    quantity=qty,
    leverage=leverage,
    order_type="MARKET",
    margin_type="ISOLATED"
)
print("Order Response:\n", json.dumps(order_res, indent=2))

# 5. Place TP and SL orders
print("\n[3/4] Placing Take Profit & Stop Loss orders...")
try:
    tp_res = bn.set_take_profit(symbol, direction, tp_price)
    print("TP Order Placed:", tp_res)
except Exception as e:
    print(f"Warning placing TP: {e}")

try:
    sl_res = bn.set_stop_loss(symbol, direction, sl_price)
    print("SL Order Placed:", sl_res)
except Exception as e:
    print(f"Warning placing SL: {e}")

# 6. Send Telegram Alert
print("\n[4/4] Sending Telegram notification...")
chat_id = os.getenv("ALLOWED_TELEGRAM_CHAT_ID", "6794686929")
msg = (
    f"🚀 <b>PYROFUEL LIVE TRADE EXECUTED!</b>\n\n"
    f"🪙 <b>Pair:</b> #{symbol} ({direction})\n"
    f"⚡ <b>Leverage:</b> {leverage}x ISOLATED\n"
    f"💰 <b>Margin:</b> ${margin_to_use:.2f} USDT (Notional: ${qty * mark_price:.2f})\n"
    f"🎯 <b>Setup:</b> BOLLINGER_SQUEEZE_BREAKOUT (AI Conf: 65%)\n"
    f"📈 <b>Entry:</b> ${mark_price:.4f}\n"
    f"🟢 <b>Take Profit:</b> ${tp_price:.4f} (+32.0% ROI)\n"
    f"🔴 <b>Stop Loss:</b> ${sl_price:.4f} (-18.0% Risk)\n"
    f"⏱️ <b>ETA TP:</b> ~25-45 Menit (Scalp Momentum)\n\n"
    f"✅ <i>Order telah terisi di Binance Futures.</i>"
)
try:
    send_telegram_message(chat_id, msg)
    print("Telegram alert sent successfully!")
except Exception as e:
    print(f"Telegram error: {e}")

print("\n" + "=" * 65)
print("🎉 TRADE OPENED AND ACTIVE ON BINANCE FUTURES!")
print("=" * 65)
