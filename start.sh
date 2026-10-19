#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$DIR/tablet1-chatbot" ]; then
    cd "$DIR/tablet1-chatbot"
    chmod +x start.sh 2>/dev/null || true
    exec ./start.sh
else
    echo "Directory tablet1-chatbot not found in $DIR"
    exit 1
fi
