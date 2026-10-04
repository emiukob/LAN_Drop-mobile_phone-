@echo off
title LAN Drop - Fast Local File Transfer
cd /d "%~dp0"

echo [1/2] Checking dependencies...
pip install -r requirements.txt

echo.
echo [2/2] Starting server...
python app.py
pause
