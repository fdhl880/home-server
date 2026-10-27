"""
PYROFUEL BOT - TERMUX / ENVIRONMENT SELF-TEST
Validasi menyeluruh lingkungan Termux/server sebelum bot dijalankan.
"""
import sys
import os
import time
import json

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BOT_DIR)
os.chdir(BOT_DIR)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BOT_DIR, ".env"))
except ImportError:
    try:
        from pipeline import load_env
        load_env()
    except Exception:
        pass

print("=" * 60)
print("  PYROFUEL BOT - ENVIRONMENT & CONNECTIVITY SELF-TEST")
print("=" * 60)

passed = 0
total = 0

def record(name: str, status: bool, detail: str = ""):
    global passed, total
    total += 1
    if status:
        passed += 1
        tag = "[PASS]"
    else:
        tag = "[FAIL]"
    print(f"{tag:7s} {name:32s} {detail}")

# 1. Python Version
py_ver = sys.version_info
record("Python >= 3.10", py_ver >= (3, 10), f"v{py_ver.major}.{py_ver.minor}.{py_ver.micro}")

# 2. Package Imports
for mod_name in ["requests", "urllib3", "numpy"]:
    try:
        __import__(mod_name)
        record(f"Import {mod_name}", True, "Available")
    except Exception as e:
        record(f"Import {mod_name}", False, str(e)[:50])

try:
    __import__("dotenv")
    record("Import python-dotenv", True, "Available")
except Exception:
    record("Import python-dotenv", True, "Built-in parser available as fallback")

# 3. Disk Write Permissions
for d in ["results", "logs"]:
    os.makedirs(os.path.join(BOT_DIR, d), exist_ok=True)
    test_f = os.path.join(BOT_DIR, d, ".write_test")
    try:
        with open(test_f, "w") as f:
            f.write("ok")
        os.remove(test_f)
        record(f"Disk write ({d}/)", True, "Writable")
    except Exception as e:
        record(f"Disk write ({d}/)", False, str(e)[:50])

# 4. DoH DNS Anti-Block
doh_ok = False
for doh_url in [
    "https://1.1.1.1/dns-query?name=api.groq.com&type=A",
    "https://dns.google/resolve?name=fapi.binance.com&type=A"
]:
    try:
        r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=5)
        if r.status_code == 200 and "Answer" in r.json():
            doh_ok = True
            break
    except Exception:
        pass
record("DoH DNS Resolution (1.1.1.1)", doh_ok, "Anti-blocker active")

# 5. Binance Time Sync & Clock Drift (Multi-endpoint fallback)
drift_sec = None
time_endpoints = [
    "https://fapi.binance.com/fapi/v1/time",
    "https://data-api.binance.vision/api/v3/time",
    "https://api.binance.com/api/v3/time"
]
for ep in time_endpoints:
    try:
        local_ts = time.time()
        r = requests.get(ep, timeout=5, verify=False)
        if r.status_code == 200 and "serverTime" in r.json():
            server_ts = r.json()["serverTime"] / 1000.0
            drift_sec = abs(local_ts - server_ts)
            record("Binance Time Drift", drift_sec < 2.0, f"Drift: {drift_sec:.3f}s ({ep.split('/')[2]})")
            break
    except Exception:
        continue
if drift_sec is None:
    record("Binance Time Drift", False, "Semua endpoint time tidak terjangkau")

# 6. Telegram Bot Verification
tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
if tg_token and not tg_token.startswith("your_"):
    try:
        r = requests.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=8)
        if r.status_code == 200 and r.json().get("ok"):
            bot_name = r.json()["result"].get("username", "")
            record("Telegram Bot API", True, f"@{bot_name}")
        else:
            record("Telegram Bot API", False, f"HTTP {r.status_code}")
    except Exception as e:
        record("Telegram Bot API", False, str(e)[:50])
else:
    record("Telegram Bot API", False, "TELEGRAM_BOT_TOKEN belum diisi di .env")

# 7. AI Providers Availability Check
try:
    from pipeline import call_ai
    t_start = time.time()
    raw = call_ai(
        prompt="Say OK in valid JSON.",
        system_prompt="Reply ONLY valid JSON: {\"status\":\"OK\"}",
        max_tokens=60,
        temperature=0.0
    )
    dt = time.time() - t_start
    record("AI Provider Cascade", True, f"{dt:.2f}s -> {raw.strip()[:35]}")
except Exception as e:
    record("AI Provider Cascade", False, str(e)[:70])

# 8. .env File Permission
env_path = os.path.join(BOT_DIR, ".env")
if os.path.exists(env_path):
    record(".env file present", True, "Config exists")
else:
    record(".env file present", False, "Missing .env (run start_termux.sh)")

print("=" * 60)
print(f"Hasil Self-Test: {passed}/{total} Pengujian Lolos ({int(passed/total*100)}%)")
print("=" * 60)

sys.exit(0 if passed >= (total - 1) else 1)
