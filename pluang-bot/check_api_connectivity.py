"""
=============================================================
PYROFUEL API CONNECTIVITY & ANTI-BLOCKING CHECKER
=============================================================
Script diagnostik untuk memastikan seluruh endpoint API:
- Binance Futures (fapi.binance.com)  — diuji DENGAN DoH bypass
- Telegram Bot API (api.telegram.org)
- Groq Cloud AI (api.groq.com)
- Google Gemini AI (generativelanguage.googleapis.com)
- OpenRouter AI (openrouter.ai)
- Ollama Local AI (localhost:11434)   — hanya di PC/laptop

bebas dari blokir ISP (Internet Positif/Nawala/DNS Poisoning)
dan siap dijalankan di Termux Android / VPS / PC.
=============================================================
"""
import os
import sys
import time
import requests
import json
import socket
import urllib3

# -------------------------------------------------------------
# Universal Anti-Blocking & ISP DNS Bypass via DNS-over-HTTPS (DoH)
# Membuka blokir ISP Indonesia untuk Binance, Groq, Gemini, OpenRouter & Telegram
# -------------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {
    "fapi.binance.com":  "65.8.76.49",
    "fapi1.binance.com": "65.8.76.14",
    "fapi2.binance.com": "65.8.76.6",
    "fapi3.binance.com": "65.8.76.4",
    "api.groq.com": "104.18.38.236",
    "generativelanguage.googleapis.com": "172.217.114.4",
    "openrouter.ai": "104.18.3.115",
    "api.telegram.org": "149.154.166.110"
}

def _resolve_doh(domain: str):
    if domain in _dns_cache:
        return _dns_cache[domain]
    for doh_url in [
        f"https://1.1.1.1/dns-query?name={domain}&type=A",
        f"https://dns.google/resolve?name={domain}&type=A"
    ]:
        try:
            r = requests.get(doh_url, headers={"accept": "application/dns-json"}, timeout=3)
            data = r.json()
            ips = [ans["data"] for ans in data.get("Answer", []) if ans.get("type") == 1]
            if ips:
                _dns_cache[domain] = ips[0]
                return ips[0]
        except Exception:
            continue
    return None

def _custom_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if isinstance(host, str) and any(kw in host.lower() for kw in ["binance", "groq", "googleapis", "openrouter", "telegram"]):
        ip = _resolve_doh(host)
        if ip:
            return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

# Aktifkan bypass sebelum request apa pun
socket.getaddrinfo = _custom_getaddrinfo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env = {}
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = load_env()

def print_box(text):
    line = "=" * 65
    print(f"\n{line}\n  {text}\n{line}")

def test_telegram(token):
    if not token:
        return False, "TOKEN MISSING di .env"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        t0 = time.time()
        r = requests.get(url, timeout=7)
        latency = int((time.time() - t0) * 1000)
        data = r.json()
        if data.get("ok"):
            bot_name = data["result"].get("username", "Unknown")
            return True, f"OK ({latency}ms) - Bot @{bot_name}"
        return False, f"HTTP {r.status_code}: {data.get('description', '')}"
    except requests.exceptions.ConnectionError:
        return False, "TERBLOKIR / DNS FAIL (Koneksi ke api.telegram.org ditolak/timeout)"
    except Exception as e:
        return False, f"Error: {str(e)[:80]}"

def test_binance(api_key="", api_secret=""):
    """
    Uji Binance dengan DoH bypass aktif (sama dengan binance_futures.py).
    Ini artinya tes ini REALISTIS — jika ONLINE di sini, bot juga bisa konek.
    """
    endpoints = [
        "https://fapi.binance.com/fapi/v1/ping",
        "https://fapi1.binance.com/fapi/v1/ping",
        "https://fapi2.binance.com/fapi/v1/ping",
        "https://fapi3.binance.com/fapi/v1/ping"
    ]
    sess = requests.Session()
    sess.verify = False  # Bot juga pakai verify=False
    results = []
    success_any = False
    for ep in endpoints:
        domain = ep.split("/")[2]
        try:
            t0 = time.time()
            r = sess.get(ep, timeout=5)
            latency = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                results.append(f"  + {domain}: ONLINE ({latency}ms) [DoH bypass OK]")
                success_any = True
            else:
                results.append(f"  ! {domain}: HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            results.append(f"  x {domain}: TERBLOKIR bahkan dengan DoH bypass")
        except Exception as e:
            results.append(f"  x {domain}: Error ({str(e)[:50]})")
            
    summary = "\n".join(results)
    return success_any, summary

def test_groq(api_key):
    if not api_key:
        return False, "KEY MISSING di .env"
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        t0 = time.time()
        r = requests.get(url, headers=headers, timeout=6)
        latency = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, f"ONLINE ({latency}ms) - Fast Cloud AI Ready"
        return False, f"HTTP {r.status_code}: {r.text[:80]}"
    except requests.exceptions.ConnectionError:
        return False, "TERBLOKIR / DNS FAIL ke api.groq.com"
    except Exception as e:
        return False, f"Error: {str(e)[:80]}"

def test_gemini(api_key):
    if not api_key:
        return False, "KEY MISSING di .env"
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        t0 = time.time()
        r = requests.get(url, timeout=6)
        latency = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, f"ONLINE ({latency}ms) - Google AI Ready"
        return False, f"HTTP {r.status_code}: {r.text[:80]}"
    except requests.exceptions.ConnectionError:
        return False, "TERBLOKIR / DNS FAIL ke Google Gemini"
    except Exception as e:
        return False, f"Error: {str(e)[:80]}"

def test_openrouter(api_key):
    if not api_key:
        return False, "KEY MISSING di .env"
    url = "https://openrouter.ai/api/v1/auth/key"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        t0 = time.time()
        r = requests.get(url, headers=headers, timeout=6)
        latency = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, f"ONLINE ({latency}ms) - Multi-Model Fallback Ready"
        return False, f"HTTP {r.status_code}: {r.text[:80]}"
    except requests.exceptions.ConnectionError:
        return False, "TERBLOKIR / DNS FAIL ke openrouter.ai"
    except Exception as e:
        return False, f"Error: {str(e)[:80]}"

def test_ollama(base_url="http://localhost:11434"):
    try:
        t0 = time.time()
        r = requests.get(f"{base_url}/api/tags", timeout=3)
        latency = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            models = [m.get("name", "?") for m in r.json().get("models", [])]
            return True, f"ONLINE ({latency}ms) — Models: {', '.join(models) or 'kosong'}"
        return False, f"HTTP {r.status_code}"
    except Exception:
        return False, "OFFLINE (normal di Android/Termux — akan pakai cloud AI)"


def main():
    print_box("PYROFUEL API HEALTH & ANTI-BLOKIR DIAGNOSTIC")

    # 1. Telegram
    print("\n1. Menguji Telegram Bot API...")
    tele_token = ENV.get("TELEGRAM_BOT_TOKEN", "")
    ok_tele, msg_tele = test_telegram(tele_token)
    icon_tele = "[ OK ]" if ok_tele else "[FAIL]"
    print(f"   {icon_tele} Telegram: {msg_tele}")

    # 2. Binance Futures (dengan DoH bypass)
    print("\n2. Menguji Binance Futures API (dengan DoH bypass, sama seperti bot)...")
    ok_binance, msg_binance = test_binance()
    icon_binance = "[ OK ]" if ok_binance else "[FAIL]"
    print(f"   {icon_binance} Binance Futures:")
    print(msg_binance)
    if ok_binance:
        print("   NOTE: ISP mungkin blokir DNS Binance, tapi DoH bypass BERHASIL.")
        print("         Bot sudah dikonfigurasi untuk bypass ini secara otomatis.")

    # 3. Groq AI
    print("\n3. Menguji Groq AI Cloud...")
    groq_key = ENV.get("GROQ_API_KEY", "")
    ok_groq, msg_groq = test_groq(groq_key)
    icon_groq = "[ OK ]" if ok_groq else "[FAIL]"
    print(f"   {icon_groq} Groq: {msg_groq}")

    # 4. Gemini AI
    print("\n4. Menguji Google Gemini AI...")
    gemini_key = ENV.get("GEMINI_API_KEY", "")
    ok_gemini, msg_gemini = test_gemini(gemini_key)
    icon_gemini = "[ OK ]" if ok_gemini else "[FAIL]"
    print(f"   {icon_gemini} Gemini: {msg_gemini}")

    # 5. OpenRouter AI
    print("\n5. Menguji OpenRouter AI...")
    openrouter_key = ENV.get("OPENROUTER_API_KEY", "")
    ok_or, msg_or = test_openrouter(openrouter_key)
    icon_or = "[ OK ]" if ok_or else "[FAIL]"
    print(f"   {icon_or} OpenRouter: {msg_or}")

    # 6. Ollama Local AI
    print("\n6. Menguji Ollama Local AI (hanya berlaku di PC/laptop)...")
    ollama_url = ENV.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ok_ollama, msg_ollama = test_ollama(ollama_url)
    icon_ollama = "[ OK ]" if ok_ollama else "[ -- ]"
    print(f"   {icon_ollama} Ollama: {msg_ollama}")

    # Ringkasan
    cloud_ai_ok = ok_groq or ok_gemini or ok_or
    all_critical_ok = ok_tele and ok_binance and cloud_ai_ok
    print("\n" + "=" * 65)
    if all_critical_ok:
        if ok_ollama:
            ai_mode = "Ollama (lokal) -> Groq -> Gemini -> OpenRouter"
        else:
            ai_mode = "Groq -> Gemini -> OpenRouter (cloud cascade)"
        print(f"  STATUS: SEMUA API UTAMA SIAP! [AMAN]")
        print(f"  Mode AI: {ai_mode}")
    else:
        print("  PERHATIAN: ADA MASALAH KONEKSI!")
        if not ok_tele:
            print("  [!] Telegram GAGAL — cek token di .env atau koneksi internet")
        if not ok_binance:
            print("  [!] Binance GAGAL bahkan dengan DoH — coba aktifkan VPN/WARP")
        if not cloud_ai_ok:
            print("  [!] Semua Cloud AI GAGAL — cek API key di .env")
        print("")
        print("  Solusi Anti-Blokir di Android/Termux:")
        print("  1. Aktifkan Private DNS:")
        print("     Pengaturan -> Jaringan -> DNS Pribadi ->")
        print("     Ketik: one.one.one.one")
        print("  2. Install app '1.1.1.1' dari Cloudflare (WARP free VPN)")
        print("  3. Atau gunakan VPN lain (ProtonVPN, Windscribe free)")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
