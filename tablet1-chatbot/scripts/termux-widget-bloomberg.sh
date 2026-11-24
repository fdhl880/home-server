#!/data/data/com.termux/files/usr/bin/bash
# Bloomberg Terminal — Termux:Widget Android Home Screen Launcher
# Install:
#   mkdir -p ~/.shortcuts
#   cp ~/home-server/tablet1-chatbot/scripts/termux-widget-bloomberg.sh ~/.shortcuts/"Bloomberg Terminal.sh"
#   chmod +x ~/.shortcuts/"Bloomberg Terminal.sh"
# Then add the "Termux:Widget" widget to your Android Home Screen.

PORT="${PORT:-4000}"
URL="http://localhost:${PORT}/widget?mode=all"

if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "$URL"
elif command -v am >/dev/null 2>&1; then
  am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1
else
  echo "Open Bloomberg Terminal Widget at: $URL"
fi
