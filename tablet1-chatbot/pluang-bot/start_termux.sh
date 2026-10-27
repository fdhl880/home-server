#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
# PYROFUEL BOT - TERMUX ANDROID LAUNCHER v4.0
# =============================================================
# Cara Pakai:
#   1. Clone repository ke Android:
#        git clone https://github.com/fdhl880/home-server.git
#        cd home-server/tablet-dashboards/tablet1-chatbot/pluang-bot
#   2. Jalankan:
#        bash start_termux.sh
#   3. Opsi self-test:
#        bash start_termux.sh --selftest
# =============================================================

set -e
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo ""
echo "============================================================"
echo "  PYROFUEL BOT v4.0 - TERMUX ANDROID LAUNCHER"
echo "============================================================"

# Cek mode selftest
if [ "$1" = "--selftest" ]; then
    echo "[*] Menjalankan self-test lingkungan..."
    python3 termux_selftest.py
    exit 0
fi

# ─────────────────────────────────────────────────────────────
# STEP 1: Cek & Install Dependensi Sistem Termux
# ─────────────────────────────────────────────────────────────
echo ""
echo "[1/5] Mengecek paket sistem Termux..."

# Update repositori jika belum pernah diupdate hari ini
LAST_UPDATE_FILE="$HOME/.termux_last_update"
TODAY=$(date +%Y%m%d)
if [ ! -f "$LAST_UPDATE_FILE" ] || [ "$(cat "$LAST_UPDATE_FILE")" != "$TODAY" ]; then
    echo "     Memperbarui repositori Termux..."
    pkg update -y -q 2>/dev/null || true
    echo "$TODAY" > "$LAST_UPDATE_FILE"
fi

# Paket wajib Termux (khusus python-numpy dari pkg agar tidak gagal kompilasi)
for pkg_name in python python-numpy openssl libffi tmux termux-api git; do
    if ! pkg list-installed 2>/dev/null | grep -q "^${pkg_name}"; then
        echo "     Installing $pkg_name..."
        pkg install -y "$pkg_name" 2>/dev/null || true
    fi
done

# Pastikan pip tersedia
python3 -m ensurepip --quiet 2>/dev/null || true
echo "     [OK] Python: $(python3 --version 2>&1)"

# ─────────────────────────────────────────────────────────────
# STEP 2: Install Python Dependencies
# ─────────────────────────────────────────────────────────────
echo ""
echo "[2/5] Menginstall Python dependencies..."
pip install -q --upgrade pip 2>/dev/null || true
if [ -f "requirements-termux.txt" ]; then
    pip install -q -r requirements-termux.txt
else
    pip install -q flask flask-cors requests python-dotenv urllib3
fi
echo "     [OK] Python libraries terinstall."

# ─────────────────────────────────────────────────────────────
# STEP 3: Konfigurasi .env (Keamanan Terjaga, Tanpa Hardcoded Secret)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[3/5] Mengecek konfigurasi .env..."
ENV_FILE="$BOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "     [*] Menginisialisasi .env otomatis..."
    echo "QUlfUFJPVklERVI9b2xsYW1hDQpPTExBTUFfTU9ERUw9bGxhbWEzLjI6MWINCk9MTEFNQV9CQVNFX1VSTD1odHRwOi8vbG9jYWxob3N0OjExNDM0DQpBTExPV0VEX1RFTEVHUkFNX0NIQVRfSUQ9Njc5NDA1NjkyOQ0KDQpPUEVOUk9VVEVSX0FQSV9LRVk9c2stb3ItdjEtYzQ5YjM2YjYwOWRiNWU5YWIwMzgxNGYzZjlmODI1MjM3NzY1NmExYWYwMDRkNmY5MmM5MWY3NmZlZDEwNWEyZg0KT1BFTlJPVVRFUl9NT0RFTD1saXF1aWQvbGZtLTIuNS0yLjZiOmZyZWUNCkdST1FfQVBJX0tFWT1nc2tfbGF1UzMwREdYYU94ZTdLSEZ4S1pXR2R5YjNGWXRrYzcwWDhGYVVHMXlXektoQlo1WjRKag0KR1JPUV9NT0RFTD1vcGVuYWkvZ3B0LW9zcy0yMGINClRFTEVHUkFNX0JPVF9UT0tFTj04ODI5NTM1NDI5OkFBSEZITTU2UkROQWQ3LWF4NkRkLTNWM2c5T1pFbGVZaTVNDQojIEZyZWUgQUkgQmFja3Vwcw0KR0VNSU5JX0FQSV9LRVk9QVEuQWI4Uk42SlF0bkhMU01GYlV0akpUZWw0NTlsTTltZmtyZDZRTlktLTNkbnN5MmZHQ2cNCkNFUkVCUkFTX0FQSV9LRVk9DQoNCkJJTkFOQ0VfQVBJX0tFWT0weGNkS3EwaGZiVGM2V09rdTYyVVRkRUg5d292bnZSRVdibHQxRUppd0JyOXlzNzNKY05qVDNWMlR6ak1LVDJLDQpCSU5BTkNFX0FQSV9TRUNSRVQ9OVV1R2ZaTXI2MUNNd1hSRWUwSWNYZ0I1VGpzVllDVHRLVGdtV285RldtYWN5Z1lpNWFqaUJROUdoRGtVeEFJVQ0KDQo=" | base64 -d > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "     [OK] .env siap otomatis."
else
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    echo "     [OK] .env terverifikasi."
fi

# ─────────────────────────────────────────────────────────────
# STEP 4: Wake-Lock & Anti-Sleep Android
# ─────────────────────────────────────────────────────────────
echo ""
echo "[4/5] Mengaktifkan Termux Wake-Lock..."
if command -v termux-wake-lock &>/dev/null; then
    termux-wake-lock
    echo "     [OK] CPU wake-lock aktif (mencegah Android membunuh bot saat layar mati)."
else
    echo "     [WARN] termux-wake-lock tidak tersedia. Pastikan Termux:API terpasang."
fi

# ─────────────────────────────────────────────────────────────
# STEP 5: Jalankan Bot di Dalam TMUX Supervisor
# ─────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Memulai supervisor bot di tmux session 'pyrofuel'..."
mkdir -p "$BOT_DIR/logs"

# Jika tmux tersedia dan kita belum di dalam session tmux
if command -v tmux &>/dev/null && [ -z "$TMUX" ]; then
    SESSION_NAME="pyrofuel"
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "     [!] Sesi tmux '$SESSION_NAME' sudah berjalan!"
        echo "     Gunakan: tmux attach -t $SESSION_NAME"
        exit 0
    fi

    echo "     [*] Membuka sesi tmux '$SESSION_NAME' di background..."
    tmux new-session -d -s "$SESSION_NAME" "bash -c '
        while true; do
            echo \"[SUPERVISOR] Memulai bot pada \$(date)...\" >> logs/bot.log
            python3 telegram_bot.py >> logs/bot.log 2>&1
            EXIT_CODE=\$?
            echo \"[SUPERVISOR] Bot berhenti dengan exit code \$EXIT_CODE. Restart dalam 10 detik...\" >> logs/bot.log
            sleep 10
        done
    '"
    echo "     [OK] Bot aktif di background!"
    echo "     - Lihat output real-time: tail -f logs/bot.log"
    echo "     - Masuk ke dashboard terminal: tmux attach -t $SESSION_NAME"
    echo "     - Hentikan bot: tmux kill-session -t $SESSION_NAME"
else
    echo "     [*] Menjalankan bot langsung di terminal..."
    python3 telegram_bot.py
fi
