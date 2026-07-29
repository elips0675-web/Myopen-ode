@echo off
cd /d "E:\My OpenCode"
echo AI Desktop запускается...
python desktop.py
if %errorlevel% neq 0 (
    echo Ошибка: Убедитесь что установлен Python и библиотеки.
    echo pip install requests fastapi uvicorn
    pause
)
