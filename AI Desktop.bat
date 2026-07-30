@echo off
cd /d "%~dp0"
echo AI Coder v2 — Desktop App
echo.
pip install pywebview 2>nul || echo pywebview not found, will use browser
python desktop.py
if %errorlevel% neq 0 (
    echo.
    echo Error. Make sure dependencies are installed:
    echo pip install fastapi uvicorn requests duckduckgo_search pywebview
    pause
)
