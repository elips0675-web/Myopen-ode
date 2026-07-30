@echo off
cd /d "%~dp0"
python agent.py
if %errorlevel% neq 0 (
    echo.
    echo Need: pip install fastapi uvicorn requests duckduckgo_search
    pause
)
