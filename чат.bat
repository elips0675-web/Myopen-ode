@echo off
chcp 65001 >nul
cd /d "E:\My OpenCode"

echo Чат с Ollama
echo.

ollama list >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] Ollama не запущена
    pause
    exit /b 1
)

echo Открывается http://localhost:8888
python chat.py
pause
