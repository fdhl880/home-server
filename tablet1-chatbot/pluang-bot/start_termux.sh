#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
# PYROFUEL BOT - TERMUX ANDROID LAUNCHER v3.1
# =============================================================
# Cara Pakai:
#   1. Copy folder pluang-bot ke HP (via USB, ADB, atau git clone)
#        git clone https://github.com/fdhl880/home-server.git
#        cd home-server/tablet-dashboards/tablet1-chatbot/pluang-bot
#   2. Buka Termux, masuk ke folder bot
#   3. Jalankan:
#        bash start_termux.sh
# =============================================================

set -e  # Hentikan jika ada error kritis
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo ""
echo "============================================================"
echo "  PYROFUEL BOT v3.1 - TERMUX ANDROID LAUNCHER"
echo "============================================================"

# ─────────────────────────────────────────────────────────────
# STEP 1: Cek & Install Dependensi Termux
# ─────────────────────────────────────────────────────────────
echo ""
echo "[1/5] Mengecek paket sistem Termux..."

# Update pkg jika belum pernah dilakukan hari ini
LAST_UPDATE_FILE="$HOME/.termux_last_update"
TODAY=$(date +%Y%m%d)
if [ ! -f "$LAST_UPDATE_FILE" ] || [ "$(cat $LAST_UPDATE_FILE)" != "$TODAY" ]; then
    echo "     Memperbarui repositori Termux..."
    pkg update -y -q && pkg upgrade -y -q 2>/dev/null || true
    echo "$TODAY" > "$LAST_UPDATE_FILE"
fi

# Paket wajib
for pkg_name in python python-pip openssl-tool; do
    if ! pkg list-installed 2>/dev/null | grep -q "^${pkg_name}"; then
        echo "     Installing $pkg_name..."
        pkg install -y "$pkg_name" 2>/dev/null || true
    fi
done

# Pastikan pip tersedia
python -m ensurepip --quiet 2>/dev/null || true

echo "     [OK] Python: $(python --version 2>&1)"

# ─────────────────────────────────────────────────────────────
# STEP 2: Install Python Dependencies
# ─────────────────────────────────────────────────────────────
echo ""
echo "[2/5] Menginstall Python dependencies..."
pip install -q --upgrade pip 2>/dev/null || true
pip install -q flask flask-cors requests python-dotenv numpy urllib3

echo "     [OK] Semua library Python terinstall."

# ─────────────────────────────────────────────────────────────
# STEP 3: Siapkan .env untuk Termux (Cloud AI Mode)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[3/5] Mengonfigurasi .env untuk mode Cloud AI (Termux)..."

ENV_FILE="$BOT_DIR/.env"

# Jika .env belum ada atau masih berisi placeholder, inject otomatis
if [ ! -f "$ENV_FILE" ] || grep -q "your_groq_api_key_here" "$ENV_FILE" 2>/dev/null || [ ! -s "$ENV_FILE" ]; then
    echo "     [*] .env belum ada / belum disetup. Menginjeksi konfigurasi API aktif..."
    # Credentials: Groq + Gemini + OpenRouter + Telegram + Binance (updated 2026-10-27)
    B64_CRED="QUlfUFJPVklERVI9Z3JvcQpPTExBTUFfTU9ERUw9bGxhbWEzLjI6MWIKT0xMQU1BX0JBU0VfVVJMPWh0dHA6Ly9sb2NhbGhvc3Q6MTE0MzQKR1JPUV9BUElfS0VZPWdza19sYXVTMzBER1hhT3hlN0tIRnhLWldHZHliM0ZZdGtjNzBYOEZhVUcxeVd6S2hCWjVaNEpqCkdST1FfTU9ERUw9b3BlbmFpL2dwdC1vc3MtMjBiCkdFTUlOSV9BUElfS0VZPUFRLkFiOFJONkpRdG5ITFNNRmJVdGpKVGVsNDU5bE05bWZrcmQ2UU5ZLS0zZG5zeTJmR0NnCk9QRU5ST1VURVJfQVBJX0tFWT1zay1vci12MS1jNDliMzZiNjA5ZGI1ZTlhYjAzODE0ZjNmOWY4MjUyMzc3NjU2YTFhZjAwNGQ2ZjkyYzkxZjc2ZmVkMTA1YTJmCk9QRU5ST1VURVJfTU9ERUw9b3BlbnJvdXRlci9hdXRvClRFTEVHUkFNX0JPVF9UT0tFTj04ODI5NTM1NDI5OkFBSEZITTU2UkROQWQ3LWF4NkRkLTNWM2c5T1pFbGVZaTVNCkFMTE9XRURfVEVMRUdSQU1fQ0hBVF9JRD02Nzk0Njg2OTI5CkJJTkFOQ0VfQVBJX0tFWT0weGNkS3EwaGZiVGM2V09rdTYyVVRkRUg5d292bnZSRVdibHQxRUppd0JyOXlzNzNKY05qVDNWMlR6ak1LVDJLCkJJTkFOQ0VfQVBJX1NFQ1JFVD05VXVHZlpNcjYxQ013WFJFZTBJY1hnQjVUanNWWUNUdEtUZ21XbzlGV21hY3lnWWk1YWppQlE5R2hEa1V4QUlV"
    echo "$B64_CRED" | base64 -d > "$ENV_FILE" 2>/dev/null || \
        echo "$B64_CRED" | openssl base64 -d > "$ENV_FILE" 2>/dev/null || \
        python3 -c "import base64,sys; open('$ENV_FILE','wb').write(base64.b64decode('$B64_CRED'))"
    echo "     [OK] .env otomatis disiapkan dengan kredensial aktif!"
fi

# Pastikan AI_PROVIDER=groq (cloud) karena Ollama tidak bisa di Android
if grep -q "^AI_PROVIDER=" "$ENV_FILE"; then
    sed -i 's/^AI_PROVIDER=.*/AI_PROVIDER=groq/' "$ENV_FILE"
else
    echo "AI_PROVIDER=groq" >> "$ENV_FILE"
fi

# Pastikan OPENROUTER_MODEL=openrouter/auto (model lama deprecated)
if grep -q "^OPENROUTER_MODEL=" "$ENV_FILE"; then
    # Ganti model lama yang deprecated
    sed -i 's|^OPENROUTER_MODEL=nvidia/nemotron.*|OPENROUTER_MODEL=openrouter/auto|' "$ENV_FILE"
    sed -i 's|^OPENROUTER_MODEL=liquid/.*|OPENROUTER_MODEL=openrouter/auto|' "$ENV_FILE"
    sed -i 's|^OPENROUTER_MODEL=minimax/.*|OPENROUTER_MODEL=openrouter/auto|' "$ENV_FILE"
else
    echo "OPENROUTER_MODEL=openrouter/auto" >> "$ENV_FILE"
fi

echo "     [OK] AI_PROVIDER=groq + Gemini + OpenRouter/auto (cloud cascade aktif)"

# ─────────────────────────────────────────────────────────────
# STEP 4: Test Konektivitas API (Anti-Blokir ISP)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[4/5] Menguji koneksi API..."

# Test cepat: Groq API (paling reliabel)
python3 -c "
import requests, sys
try:
    r = requests.get('https://api.groq.com', timeout=5)
    print('     [OK] api.groq.com terjangkau')
except Exception as e:
    print(f'     [WARN] api.groq.com: {e}')
try:
    r = requests.get('https://1.1.1.1/dns-query?name=api.groq.com&type=A',
        headers={'accept': 'application/dns-json'}, timeout=5)
    if r.status_code == 200:
        print('     [OK] DoH 1.1.1.1 aktif (anti-blokir ISP)')
except Exception as e:
    print(f'     [WARN] DoH: {e}')
" 2>/dev/null || true

# ─────────────────────────────────────────────────────────────
# STEP 5: Jalankan Bot
# ─────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Memulai Telegram Bot..."
echo ""
echo "  Urutan AI Fallback:"
echo "    Groq (20B/27B/120B) -> Gemini Flash Lite -> OpenRouter Auto -> Rule-Based Quant"
echo ""
echo "  TIP: Untuk jaga bot tetap berjalan saat layar mati:"
echo "       nohup python telegram_bot.py > bot.log 2>&1 &"
echo "       tail -f bot.log"
echo ""
echo "  Tekan Ctrl+C untuk menghentikan bot."
echo "============================================================"
echo ""

# Jalankan langsung (foreground) supaya bisa lihat output realtime
python telegram_bot.py
