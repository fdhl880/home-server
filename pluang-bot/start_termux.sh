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
# STEP 3: Patch .env untuk Termux (Non-Ollama Mode)
# ─────────────────────────────────────────────────────────────
# Di Termux Android, Ollama tidak bisa berjalan (binary x86 only).
# Kita set AI_PROVIDER=groq agar langsung pakai cloud AI.
echo ""
echo "[3/5] Mengonfigurasi .env untuk mode Cloud AI (Termux)..."

ENV_FILE="$BOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "     [ERROR] File .env tidak ditemukan di $BOT_DIR"
    echo "             Salin .env.example ke .env dan isi API key-nya!"
    exit 1
fi

# Patch AI_PROVIDER ke groq (cloud) karena Ollama tidak bisa di Android
if grep -q "^AI_PROVIDER=" "$ENV_FILE"; then
    # Ganti nilai yang ada
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
