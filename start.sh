#!/usr/bin/env bash
# LAN Drop - Unix/macOS Launcher

cd "$(dirname "$0")"

echo "[1/2] Checking Python dependencies..."
if ! command -v python3 &> /dev/null; then
    echo "[!] python3 is not installed or not in PATH."
    exit 1
fi

python3 -m pip install -r requirements.txt

echo ""
echo "[2/2] Starting LAN Drop server..."
python3 app.py
