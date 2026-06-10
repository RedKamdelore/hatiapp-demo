@echo off
cd /d "%~dp0"
echo ========================================
echo  HatiApp Server - HTTPS Mode
echo ========================================
echo.
echo  This mode requires SSL certificates:
echo    - cert.pem
echo    - key.pem
echo.
echo  If certificates are missing, server will
echo  show error and exit.
echo.
echo  On phones: Chrome will show 'Not Secure'
echo  Press 'Advanced' -^> 'Proceed to site'
echo.
pause
call venv\Scripts\activate.bat
python hotspot.py --https
pause