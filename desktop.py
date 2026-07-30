#!/usr/bin/env python3
"""Desktop App — нативное окно для AI Coder v2 через pywebview."""

import os, sys, threading, webbrowser
from pathlib import Path

# Запускаем agent.py как подпроцесс или встраиваем
os.environ.setdefault("PORT", "8765")
PORT = int(os.environ["PORT"])

def start_server():
    """Запускаем FastAPI сервер в фоне."""
    from agent import app, wait_ollama
    import uvicorn
    wait_ollama()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

def main():
    # Запускаем сервер в отдельном потоке
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Пробуем pywebview, если нет — открываем браузер
    try:
        import webview
        webview.create_window("AI Coder v2", f"http://127.0.0.1:{PORT}", width=1200, height=800, resizable=True)
        webview.start(private_mode=False)
    except ImportError:
        print("pywebview not installed. Opening in browser.")
        print("Install: pip install pywebview")
        url = f"http://localhost:{PORT}"
        webbrowser.open(url)
        # Ждём пока сервер работает
        try:
            import time
            while True: time.sleep(1)
        except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
