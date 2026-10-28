#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# TABLET1-CHATBOT: ONE-CLICK TERMUX SETUP SCRIPT (INSTITUTIONAL V2)
# T0.8: Zero hardcoded/base64 credentials in repository scripts
# ==============================================================================
set -e

echo "=================================================================="
echo "📱 TABLET1-CHATBOT TRADING DESK - INSTALLASI TERMUX (ANDROID)"
echo "=================================================================="

# 1. Update Termux Packages
echo "[1/5] Memperbarui repositori Termux..."
pkg update -y && pkg upgrade -y

# 2. Install Dependencies (Pre-built ARM64 packages)
echo "[2/5] Menginstall Node.js, Python, dan Numpy ARM64..."
pkg install -y git nodejs python python-numpy clang make coreutils util-linux termux-api

# 3. Install Node Modules
echo "[3/5] Menginstall Node.js dependencies..."
npm install

# 4. Install Python Dependencies
echo "[4/5] Menginstall Python packages via pip..."
pip install flask flask-cors requests python-dotenv urllib3 websocket-client

# 5. Initialize .env files safely (without hardcoded secrets in git)
echo "[5/5] Memeriksa konfigurasi .env..."
mkdir -p pluang-bot/results

if [ ! -f ".env" ]; then
    cp .env.example .env 2>/dev/null || cat > .env << 'EOF'
PORT=4000
PLUANG_PORT=5000
AI_PROVIDER=groq
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
TELEGRAM_BOT_TOKEN=
BINANCE_API_KEY=
BINANCE_API_SECRET=
EOF
    chmod 600 .env 2>/dev/null || true
    echo "[!] Template .env dibuat. Silakan isi API keys Anda di .env dan pluang-bot/.env"
fi

if [ ! -f "pluang-bot/.env" ]; then
    cp .env pluang-bot/.env 2>/dev/null || true
    chmod 600 pluang-bot/.env 2>/dev/null || true
fi

chmod +x start.sh

# 6. Keep Termux awake
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock || true
    echo "[*] Wake-lock diaktifkan (Termux tidak akan mati saat layar redup)."
fi

echo "=================================================================="
echo "✅ SETUP TABLET1-CHATBOT SELESAI!"
echo "👉 Untuk menjalankan seluruh sistem (Bloomberg + Bot), ketik:"
echo "   ./start.sh"
echo "🌐 Buka browser di: http://localhost:4000 (Tab 10 - Crypto Desk)"
echo "=================================================================="
