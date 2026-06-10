@echo off
cd /d "%~dp0"
echo ========================================
echo  Cloudflare Tunnel - Демо режим
echo ========================================
echo.
echo  1. Убедитесь что сервер запущен (start-http.bat)
echo  2. Этот скрипт создаст временную ссылку
echo.
echo  При первом запуске может потребоваться
echo  авторизация через браузер
echo.
pause

if not exist cloudflared.exe (
    echo Скачивание cloudflared...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
)

echo.
echo Запуск туннеля...
echo Подождите, ссылка появится ниже...
echo.
echo ========================================

cloudflared.exe tunnel --url http://localhost:8000

pause