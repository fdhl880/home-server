#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
# PYROFUEL BOT - TERMUX ANDROID LAUNCHER v5.0 (INSTITUTIONAL)
# =============================================================
# T0.8: Zero hardcoded/base64 secrets in repository scripts
# T9.1: Single-instance flock + termux-wake-lock + heartbeat watchdog
# =============================================================

set -e
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo ""
echo "============================================================"
echo "  PYROFUEL BOT v5.0 - INSTITUTIONAL TERMUX LAUNCHER"
echo "============================================================"

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

LAST_UPDATE_FILE="$HOME/.termux_last_update"
TODAY=$(date +%Y%m%d)
if [ ! -f "$LAST_UPDATE_FILE" ] || [ "$(cat "$LAST_UPDATE_FILE")" != "$TODAY" ]; then
    echo "     Memperbarui repositori Termux..."
    pkg update -y -q 2>/dev/null || true
    echo "$TODAY" > "$LAST_UPDATE_FILE"
fi

for pkg_name in python python-numpy openssl libffi tmux termux-api git util-linux; do
    if ! pkg list-installed 2>/dev/null | grep -q "^${pkg_name}"; then
        echo "     Installing $pkg_name..."
        pkg install -y "$pkg_name" 2>/dev/null || true
    fi
done

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
    pip install -q flask flask-cors requests python-dotenv urllib3 websocket-client
fi
echo "     [OK] Python libraries terinstall."

# ─────────────────────────────────────────────────────────────
# STEP 3: Konfigurasi .env (T0.8: Tanpa Hardcoded / Base64 Secret)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[3/5] Mengecek konfigurasi .env..."
ENV_FILE="$BOT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$BOT_DIR/.env.example" ]; then
        cp "$BOT_DIR/.env.example" "$ENV_FILE"
    else
        cat > "$ENV_FILE" << 'EOF'
AI_PROVIDER=groq
ALLOWED_TELEGRAM_CHAT_ID=6794056929
TELEGRAM_BOT_TOKEN=
BINANCE_API_KEY=
BINANCE_API_SECRET=
GROQ_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
CEREBRAS_API_KEY=
EOF
    fi
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    echo "     [!] File .env baru dibuat dari template. Silakan isi API keys Anda di $ENV_FILE."
else
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    echo "     [OK] .env terverifikasi (permissions 600)."
fi

# ─────────────────────────────────────────────────────────────
# STEP 4: Wake-Lock & Anti-Sleep Android (T9.1)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[4/5] Mengaktifkan Termux Wake-Lock..."
if command -v termux-wake-lock &>/dev/null; then
    termux-wake-lock
    echo "     [OK] CPU wake-lock aktif."
else
    echo "     [WARN] termux-wake-lock tidak tersedia."
fi

# ─────────────────────────────────────────────────────────────
# STEP 5: Single-Instance Lock + Heartbeat Watchdog Supervisor (T9.1)
# ─────────────────────────────────────────────────────────────
echo ""
echo "[5/5] Memulai supervisor bot dengan single-instance flock & heartbeat watchdog..."
mkdir -p "$BOT_DIR/logs" "$BOT_DIR/results"
LOCK_FILE="$BOT_DIR/results/pyrofuel.lock"

if command -v tmux &>/dev/null && [ -z "$TMUX" ]; then
    SESSION_NAME="pyrofuel"
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "     [!] Sesi tmux '$SESSION_NAME' sudah berjalan!"
        echo "     Gunakan: tmux attach -t $SESSION_NAME"
        exit 0
    fi

    echo "     [*] Membuka sesi tmux '$SESSION_NAME' di background..."
    tmux new-session -d -s "$SESSION_NAME" "bash -c '
        exec 9>\"$LOCK_FILE\"
        if ! flock -n 9; then
            echo \"[ERROR] Instance lain sedang berjalan (flock terkunci).\" >> logs/bot.log
            exit 1
        fi
        while true; do
            echo \"[SUPERVISOR] Memulai bot pada \$(date)...\" >> logs/bot.log
            python3 server.py >> logs/bot.log 2>&1 &
            BOT_PID=\$!
            while kill -0 \$BOT_PID 2>/dev/null; do
                sleep 30
                if [ -f results/heartbeat.json ]; then
                    HB_AGE=\$(( \$(date +%s) - \$(date -r results/heartbeat.json +%s 2>/dev/null || date +%s) ))
                    if [ \$HB_AGE -gt 300 ]; then
                        echo \"[WATCHDOG] Heartbeat stale (\${HB_AGE}s > 300s). Merestart proses...\" >> logs/bot.log
                        kill -9 \$BOT_PID 2>/dev/null || true
                        break
                    fi
                fi
            done
            wait \$BOT_PID 2>/dev/null || true
            echo \"[SUPERVISOR] Proses berhenti. Restart dalam 5 detik...\" >> logs/bot.log
            sleep 5
        done
    '"
    echo "     [OK] Bot aktif di background dengan Heartbeat Watchdog!"
    echo "     - Lihat output real-time: tail -f logs/bot.log"
    echo "     - Masuk ke dashboard terminal: tmux attach -t $SESSION_NAME"
else
    echo "     [*] Menjalankan bot langsung di terminal..."
    python3 server.py
fi
