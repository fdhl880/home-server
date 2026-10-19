#!/bin/bash
# -------------------------------------------------------------
# PLUANG AI AGENTIC TERMINAL - VPS DEPLOYMENT SCRIPT
# -------------------------------------------------------------

echo "=== MENGINSTALL DEPENDENCIES DI VPS ==="
sudo apt-get update
sudo apt-get install -y python3 python3-pip

pip3 install flask requests

echo "=== MENJALANKAN DASHBOARD SERVER 24/7 ==="
# Menjalankan server di background dengan nohup
nohup python3 server.py > server.log 2>&1 &

echo "[+] SUKSES! Dashboard sekarang berjalan 24/7 di port 5000."
echo "[+] Buka di browser: http://IP_VPS_ANDA:5000"
