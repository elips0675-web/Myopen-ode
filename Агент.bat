@echo off
cd /d "E:\My OpenCode"
python agent.py
if %errorlevel% neq 0 (
    echo.
    echo Need: pip install requests fastapi uvicorn
    pause
)
