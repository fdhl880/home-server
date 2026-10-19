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
pkg install -y git nodejs python python-numpy clang make coreutils

# 3. Install Node Modules
echo "[3/5] Menginstall Node.js dependencies..."
npm install

# 4. Install Python Dependencies
echo "[4/5] Menginstall Python packages via pip..."
pip install flask flask-cors requests python-dotenv urllib3

# 5. Auto-inject ready-to-use .env configuration (Zero Typing Required)
echo "[5/5] Memasang konfigurasi .env otomatis..."
mkdir -p pluang-bot

echo "IyA9PT0gQkxPT01CRVJHIFRFUk1JTkFMIChOb2RlLmpzIC0gUG9ydCA0MDAwKSA9PT0KUE9SVD00MDAwCkdFTUlOSV9BUElfS0VZPUFRLkFiOFJONkplc09laUViNVZxOThFWVF3TW9jTWg3TTZ5bl9LcmVoUkRHTVFnVUdWaWh3CkdST1FfQVBJX0tFWT1nc2tfbGF1UzMwREdYYU94ZTdLSEZ4S1pXR2R5YjNGWXRrYzcwWDhGYVVHMXlXektoQlo1WjRKagpPUEVOUk9VVEVSX0FQSV9LRVk9c2stb3ItdjEtMGQzMmI2MWZjOTM4ODRjNzdhMjYxMWM0MzZiN2FmZjlhYmQ3ZjdiZWZkNzQ4Mzg4MzdiZDhiMGQ2ZjE0NGVhNgoKIyA9PT0gUExVQU5HIEJPVCAoUHl0aG9uIC0gUG9ydCA1MDAwKSA9PT0KUExVQU5HX1BPUlQ9NTAwMApURUxFR1JBTV9CT1RfVE9LRU49ODgyOTUzNTQyOTpBQUhGSE01NlJETkFkNy1heDZEZC0zVjNnOU9aRWxlWWk1TQpBSV9QUk9WSURFUj1ncm9xCkdST1FfTU9ERUw9b3BlbmFpL2dwdC1vc3MtMTIwYgpPUEVOUk9VVEVSX01PREVMPW1pbmltYXgvbWluaW1heC1tMy4xLWZsYXNoOmZyZWUK" | base64 -d > .env

echo "T1BFTlJPVVRFUl9BUElfS0VZPXNrLW9yLXYxLWM0OWIzNmI2MDlkYjVlOWFiMDM4MTRmM2Y5ZjgyNTIzNzc2NTZhMWFmMDA0ZDZmOTJjOTFmNzZmZWQxMDVhMmYKT1BFTlJPVVRFUl9NT0RFTD1taW5pbWF4L21pbmltYXgtbTMuMS1mbGFzaDpmcmVlCkdST1FfQVBJX0tFWT1nc2tfbGF1UzMwREdYYU94ZTdLSEZ4S1pXR2R5YjNGWXRrYzcwWDhGYVVHMXlXektoQlo1WjRKagpHUk9RX01PREVMPW9wZW5haS9ncHQtb3NzLTEyMGIKVEVMRUdSQU1fQk9UX1RPS0VOPTg4Mjk1MzU0Mjk6QUFIRkhNNTZSRE5BZDctYXg2RGQtM1YzZzlPWkVsZVlpNU0KQUlfUFJPVklERVI9Z3JvcQo=" | base64 -d > pluang-bot/.env

echo "[+] File .env dan pluang-bot/.env berhasil dibuat otomatis!"

chmod +x start.sh

# 6. Keep Termux awake
if command -v termux-wake-lock &> /dev/null; then
    termux-wake-lock || true
    echo "[*] Wake-lock diaktifkan (Termux tidak akan mati saat layar redup)."
fi

echo "=================================================================="
echo "✅ SETUP SELESAI TANPA PERLU KETIK APA-APA!"
echo "👉 Untuk menjalankan server, ketik:"
echo "   ./start.sh"
echo "🌐 Buka browser tablet di: http://localhost:4000 (Tab 10 - Crypto Desk)"
echo "=================================================================="
