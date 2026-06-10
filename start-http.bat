@echo off
cd /d "%~dp0"
echo ========================================
echo  HatiApp Server - HTTP Mode
echo ========================================
echo.
echo  Simple HTTP mode (no SSL required)
echo.
echo  Works immediately on all devices
echo  No security warnings in browser
echo.
echo  NOTE: Offline mode works via localStorage
echo  PWA (add to home screen) limited in HTTP
echo.
pause
call venv\Scripts\activate.bat
python hotspot.py --http
pause