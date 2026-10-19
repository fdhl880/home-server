#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# PYROFUEL & BLOOMBERG TERMINAL - ONE-CLICK TERMUX SETUP SCRIPT
# ==============================================================================
set -e

echo "=================================================================="
echo "📱 PYROFUEL TRADING DESK - INSTALLASI TERMUX (ANDROID TABLET)"
echo "=================================================================="

# 1. Update Termux Packages
echo "[1/5] Memperbarui repositori Termux..."
pkg update -y && pkg upgrade -y

# 2. Install Dependencies (Pre-built ARM64 packages)
echo "[2/5] Menginstall Node.js, Python, dan Numpy ARM64..."
pkg install -y git nodejs python python-numpy clang make

# 3. Install Node Modules
echo "[3/5] Menginstall Node.js dependencies..."
npm install

# 4. Install Python Dependencies
echo "[4/5] Menginstall Python packages via pip..."
pip install flask flask-cors requests python-dotenv urllib3

# 5. Check pluang-bot .env
PLUANG_DIR="pluang-bot"
if [ ! -f "$PLUANG_DIR/.env" ]; then
    echo "[!] Membuat $PLUANG_DIR/.env dari template..."
    if [ -f "$PLUANG_DIR/.env.example" ]; then
        cp "$PLUANG_DIR/.env.example" "$PLUANG_DIR/.env"
    fi
    echo "[⚠️] PENTING: Edit API Key Anda di $PLUANG_DIR/.env jika belum terisi!"
fi

chmod +x start.sh

# 6. Keep Termux awake
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock
    echo "[*] Wake-lock diaktifkan (Termux tidak akan mati saat layar redup)."
fi

echo "=================================================================="
echo "✅ SETUP SELESAI!"
echo "👉 Untuk menjalankan server, ketik:"
echo "   ./start.sh"
echo "🌐 Buka browser tablet di: http://localhost:4000 (Tab 10 - Crypto Desk)"
echo "=================================================================="
