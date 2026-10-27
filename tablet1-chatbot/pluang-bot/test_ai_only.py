"""
AI-ONLY guarantees (user mandate): trading decisions come from AI, never from rule-based math.

  python test_ai_only.py            -> offline guarantees (no network, no API quota used)
  python test_ai_only.py --live     -> also runs 1 real Layer-2 AI call per run (uses a little quota)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pipeline as p

FAKE_MD = {"current_price": 100.0, "rsi_14": 28, "ema_trend": "STRONG_BULLISH", "atr_pct": 1.0}
FAKE_SCAN = {"symbol": "TEST-USD", "price": 100.0, "rsi_14_1h": 28, "ema_trend_1h": "STRONG_BULLISH"}
fails = []

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not cond:
        fails.append(name)

# 1. rule-based generators can NEVER produce a trade
for fn, args in [(p._rule_based_setup, (FAKE_SCAN,)),
                 (p._rule_based_plan, (FAKE_SCAN, {}, FAKE_MD)),
                 (p._rule_based_risk, (FAKE_SCAN, {}, {}, FAKE_MD))]:
    try:
        fn(*args)
        check(f"{fn.__name__} disabled", False, "returned a result!")
    except p.AIUnavailable:
        check(f"{fn.__name__} disabled", True)

# 2. all AI providers failing => FAILED + ai_unavailable, NEVER APPROVED
orig_l1, orig_call = p.layer1_scanning, p.call_ai
p.layer1_scanning = lambda sym: (FAKE_MD, FAKE_SCAN)
def _boom(*a, **k): raise Exception("ALL_AI_FAILED:3:x > y > z:LAST_ERROR:simulated")
p.call_ai = _boom
r = p.run_5_layer_pipeline("TEST-USD")
check("all-AI-down => no trade", r.get("status") == "FAILED" and r.get("ai_unavailable") is True, str(r.get("status")))
check("all-AI-down => never APPROVED", r.get("status") != "APPROVED")

# 3. AI returns prose (not JSON) twice => AIUnavailable => no trade
p.call_ai = lambda *a, **k: "The user says: analyze this. I think we should go long because RSI is low."
r = p.run_5_layer_pipeline("TEST-USD")
check("non-JSON AI => no trade", r.get("status") == "FAILED" and r.get("ai_unavailable") is True, str(r.get("error", ""))[:80])

# 4. AI returns valid JSON NO_CLEAR_SETUP => REJECTED (AI decided, not math)
p.call_ai = lambda *a, **k: '{"setup_name":"NO_CLEAR_SETUP","direction":"NONE","confluence_count":0,"confluences":[],"probability_pct":30,"explanation_id":"flat"}'
r = p.run_5_layer_pipeline("TEST-USD")
check("AI says no setup => REJECTED", r.get("status") == "REJECTED", str(r.get("status")))
p.layer1_scanning, p.call_ai = orig_l1, orig_call

# 5. cooldown logic is per model and parses 'try again in'
p._PROVIDER_COOLDOWN.clear()
secs = p._cooldown_from_error("Rate limit reached ... tokens per day (TPD) ... Please try again in 2m38.4s.")
check("TPD cooldown parsed from message", 150 < secs < 175, f"{secs:.0f}s")
check("404 => long cooldown", p._cooldown_from_error("HTTP 404: model does not exist") >= 3600)
p._cooldown("Groq-20B", 60)
check("cooldown is per-model", p._in_cooldown("Groq-20B") and not p._in_cooldown("Groq-120B"))
p._PROVIDER_COOLDOWN.clear()

# 6. live: real AI call returns parseable JSON
if "--live" in sys.argv:
    sysm = ('Crypto futures setup analyst. Respond ONLY in valid JSON. Start with "{". Output: {"setup_name":"",'
            '"direction":"LONG/SHORT/NONE","confluence_count":0,"confluences":[],"probability_pct":50,"explanation_id":""}')
    usr = ('Analyze SOL-USD. Data:\n{"price":100.5,"chg24h":-1.2,"rsi14":38,"ema":"BEARISH","macd_hist":-0.3,'
           '"bb_pct_b":0.18,"atr_pct":1.1,"vol_ratio":1.4}\nOutput ONLY JSON setup.')
    n_ok, N = 0, 3
    for i in range(N):
        try:
            res = p._ai_json(usr, sysm, 600, 0.1, "live-test")
            n_ok += 1
            print(f"   live#{i}: {res.get('setup_name')} {res.get('direction')} p={res.get('probability_pct')}")
        except Exception as e:
            print(f"   live#{i}: FAIL {str(e)[:160]}")
    check("live AI JSON success", n_ok == N, f"{n_ok}/{N}")

print("\n" + ("ALL PASS" if not fails else f"FAILED: {fails}"))
sys.exit(1 if fails else 0)
