#!/data/data/com.termux/files/usr/bin/bash
export DEBIAN_FRONTEND=noninteractive

echo "[1/4] Stopping old node server..."
pkill -9 -f node 2>/dev/null || true

echo "[2/4] Syncing Termux packages (libicu + nodejs)..."
dpkg --configure -a </dev/null 2>/dev/null || true
apt-get update -y </dev/null >/dev/null 2>&1 || pkg update -y </dev/null
yes | apt-get -y -o Dpkg::Options::="--force-confnew" upgrade || yes | pkg upgrade -y
yes | pkg install -y --reinstall libicu nodejs git curl

if ! node -v >/dev/null 2>&1; then
  echo "[!] Fallback: switching to nodejs-lts..."
  yes | pkg install -y --reinstall libicu nodejs-lts
fi
echo "[*] Node version: $(node -v 2>&1)"

echo "[3/4] Updating GitHub repo (fdhl880/home-server)..."
SRV=$(find ~ -maxdepth 4 -path '*/tablet1-chatbot/server.js' 2>/dev/null | head -n 1)
if [ -z "$SRV" ]; then
  git clone https://github.com/fdhl880/home-server.git ~/home-server </dev/null
  SRV="$HOME/home-server/tablet1-chatbot/server.js"
fi
APP_DIR=$(dirname "$SRV")
cd "$APP_DIR/.." || exit 1
git stash </dev/null >/dev/null 2>&1 || true
git pull origin main </dev/null
git stash pop </dev/null >/dev/null 2>&1 || true

echo "[4/4] Starting Bloomberg Terminal on port 4000..."
cd "$APP_DIR" || exit 1
chmod +x start.sh setup_termux.sh
exec ./start.sh </dev/null
