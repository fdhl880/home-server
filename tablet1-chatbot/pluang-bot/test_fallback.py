import sys, os
sys.path.insert(0, r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir(r'c:\Users\Asus\.antigravity\tablet-dashboards\tablet1-chatbot\pluang-bot')

from pipeline import call_ai, _rule_based_setup

print("=== Test 1: call_ai ===")
try:
    result = call_ai(
        prompt='Say OK in JSON',
        system_prompt='Reply only valid JSON: {"status": "OK"}',
        max_tokens=50,
        temperature=0.0,
        is_json=True
    )
    print(f"call_ai OK: {result[:100]}")
except Exception as e:
    e_str = str(e)
    if "ALL_AI_FAILED" in e_str:
        print(f"All AI providers failed (expected - daily limit): {e_str[:200]}")
    else:
        print(f"call_ai error: {e_str[:200]}")

print("")
print("=== Test 2: Rule-Based Fallback ===")
fake_scan = {
    'rsi_14_1h': 28, 'ema_trend_1h': 'STRONG_BULLISH',
    'macd_1h': {'histogram': 0.5, 'trend': 'BULLISH'},
    'bollinger_1h': {'percent_b': 8, 'squeeze': True},
    'volume': {'volume_trend': 'STRONG_ACCUMULATION', 'volume_ratio': 1.8},
    'funding_rate': {'rate': 0.001, 'sentiment': 'SHORTS_PAY'},
    'smc': {'market_structure': 'BULLISH', 'liquidity_sweep': 'BULLISH_SELL_SIDE_LIQUIDITY_SWEEP', 'fvg': 'BULLISH'},
    'price': 65000,
    'quant_factors': {'composite_quant_score': 72, 'total_factors_evaluated': 500}
}
rb = _rule_based_setup(fake_scan)
print(f"Direction: {rb.get('direction')}")
print(f"Setup: {rb.get('setup_name')}")
print(f"Prob: {rb.get('probability_pct')}%")
print(f"Confluences ({rb.get('confluence_count')}): {rb.get('confluences')}")
print(f"ai_fallback: {rb.get('ai_fallback')}")
print("")
print("=== Rule-based fallback BERFUNGSI! ===")
