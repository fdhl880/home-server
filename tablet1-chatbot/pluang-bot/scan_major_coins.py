import sys, os
sys.path.append(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')
from market_data import get_market_indicators_fast, get_full_universe

coins = [
    'BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'XRP-USD', 
    'SUI-USD', 'ADA-USD', 'NEAR-USD', 'AVAX-USD', 'LINK-USD', 
    'BNB-USD', 'PEPE-USD', 'WIF-USD', 'ENA-USD', 'APT-USD', 
    'RENDER-USD', 'FET-USD', 'TAO-USD', 'TIA-USD', 'SEI-USD'
]

print(f"{'Symbol':<12} | {'Price':<12} | {'RSI14':<8} | {'EMA Trend':<16} | {'Status'}")
print("-" * 65)
for s in coins:
    try:
        ind = get_market_indicators_fast(s, '1h')
        rsi = ind.get('rsi_14', 0)
        ema = ind.get('ema_trend', 'N/A')
        p = ind.get('current_price', 0)
        print(f"{s:<12} | {p:<12.4f} | {rsi:<8.2f} | {ema:<16} | OK")
    except Exception as e:
        print(f"{s:<12} | Error: {e}")
