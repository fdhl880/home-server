#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
# PYROFUEL BOT - TERMUX ANDROID LAUNCHER
# =============================================================
# Cara Pakai:
#   1. Copy folder pluang-bot ke HP (misal via USB, ADB, atau git clone)
#   2. Buka Termux, masuk ke folder bot:
#        cd /sdcard/pluang-bot   (atau path yang sesuai)
#   3. Jalankan:
#        bash start_termux.sh
# =============================================================

set -e  # Hentikan jika ada error kritis
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo ""
echo "============================================================"
echo "  PYROFUEL BOT v3.0 - TERMUX ANDROID LAUNCHER"
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
    pkg update -y -q && pkg upgrade -y -q
    echo "$TODAY" > "$LAST_UPDATE_FILE"
fi

# Paket wajib
for pkg_name in python python-pip openssl-tool; do
    if ! command -v python &>/dev/null && [ "$pkg_name" = "python" ]; then
        echo "     Installing $pkg_name..."
        pkg install -y "$pkg_name"
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
pip install -q --upgrade pip
pip install -q flask flask-cors requests python-dotenv numpy urllib3

echo "     [OK] Semua library Python terinstall."

# ─────────────────────────────────────────────────────────────
# STEP 3: Siapkan .env untuk Termux (Cloud AI Mode)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[3/5] Mengonfigurasi .env untuk mode Cloud AI (Termux)..."

ENV_FILE="$BOT_DIR/.env"

# Jika .env belum ada atau masih berisi placeholder, buat otomatis via base64 decode
if [ ! -f "$ENV_FILE" ] || grep -q "your_groq_api_key_here" "$ENV_FILE" 2>/dev/null || [ ! -s "$ENV_FILE" ]; then
    echo "     [*] .env belum ada / belum disetup. Menginjeksi konfigurasi API aktif..."
    B64_CRED="QUlfUFJPVklERVI9Z3JvcQpHUk9RX0FQSV9LRVk9Z3NrX2xhdVMzMERHWGFPeGU3S0hGeEtaV0dkeWIzRll0a2M3MFg4RmFVRzF5V3pLaEJaNVo0SmoKR1JPUV9NT0RFTD1vcGVuYWkvZ3B0LW9zcy0yMGIKR0VNSU5JX0FQSV9LRVk9QVEuQWI4Uk42SlF0bkhMU01GYlV0akpUZWw0NTlsTTltZmtyZDZRTlktLTNkbnN5MmZHQ2cKT1BFTlJPVVRFUl9BUElfS0VZPXNrLW9yLXYxLWM0OWIzNmI2MDlkYjVlOWFiMDM4MTRmM2Y5ZjgyNTIzNzc2NTZhMWFmMDA0ZDZmOTJjOTFmNzZmZWQxMDVhMmYKT1BFTlJPVVRFUl9NT0RFTD1udmlkaWEvbmVtb3Ryb24tMy41LWxpZ2h0bmluZzpmcmVlClRFTEVHUkFNX0JPVF9UT0tFTj04ODI5NTM1NDI5OkFBSEZITTU2UkROQWQ3LWF4NkRkLTNWM2c5T1pFbGVZaTVNCkFMTE9XRURfVEVMRUdSQU1fQ0hBVF9JRD02Nzk0Njg2OTI5CkJJTkFOQ0VfQVBJX0tFWT0weGNkS3EwaGZiVGM2V09LdTYyVVRkRUg5d292bnZSRVdibHQxRUppd0JyOXlzNzNKY05qVDNWMlR6ak1LVDJLCkJJTkFOQ0VfQVBJX1NFQ1JFVD05VXVHZlpNcjYxQ013WFJFZTBJY1hnQjVUanNWWUNUdEtUZ21XbzlGV21hY3lnWWk1YWppQlE5R2hEa1V4QUlV"
    echo "$B64_CRED" | base64 -d > "$ENV_FILE" 2>/dev/null || echo "$B64_CRED" | openssl base64 -d > "$ENV_FILE"
    echo "     [OK] .env otomatis disiapkan dengan kredensial aktif!"
fi

# Pastikan AI_PROVIDER=groq (cloud) karena Ollama tidak bisa di Android
if grep -q "^AI_PROVIDER=" "$ENV_FILE"; then
    sed -i 's/^AI_PROVIDER=.*/AI_PROVIDER=groq/' "$ENV_FILE"
else
    echo "AI_PROVIDER=groq" >> "$ENV_FILE"
fi

echo "     [OK] AI_PROVIDER=groq (cloud AI aktif, Ollama dinonaktifkan)"

# ─────────────────────────────────────────────────────────────
# STEP 4: Test Konektivitas API (Anti-Blokir ISP)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[4/5] Menguji koneksi API..."

python check_api_connectivity.py 2>/dev/null || python "$BOT_DIR/check_api_connectivity.py"

# ─────────────────────────────────────────────────────────────
# STEP 5: Jalankan Bot
# ─────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Memulai Telegram Bot..."
echo ""
echo "  TIP: Untuk jaga bot tetap berjalan saat layar mati:"
echo "       Gunakan perintah ini: nohup python telegram_bot.py > bot.log 2>&1 &"
echo "       Lalu cek log dengan: tail -f bot.log"
echo ""
echo "  Tekan Ctrl+C untuk menghentikan bot."
echo "============================================================"
echo ""

# Jalankan langsung (foreground) supaya bisa lihat output realtime
python telegram_bot.py
