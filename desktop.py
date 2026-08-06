#!/usr/bin/env python3
"""Desktop App — native window for My OpenCode via pywebview.

Runs the FastAPI server in-process, waits for it to be ready, then opens a
native window (or the default browser if pywebview is missing). If the server
is already running on PORT it is reused instead of being started twice.

Usage: python desktop.py [--browser]
"""

import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

os.environ.setdefault("PORT", "8765")
PORT = int(os.environ["PORT"])
ROOT = Path(__file__).resolve().parent
ICON = ROOT / "assets" / "icon.ico"


def is_port_open(port, host="127.0.0.1", timeout=0.4):
    """True if something is already listening on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def wait_server_ready(port, host="127.0.0.1", timeout=30.0, interval=0.25):
    """Poll GET /health until the agent server responds (or timeout)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/health",
                                        timeout=1.5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(interval)
    return False


def start_server():
    """Run the FastAPI server in this process (blocking)."""
    from agent import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def run_desktop():
    url = f"http://127.0.0.1:{PORT}"
    import webview
    icon = str(ICON) if ICON.exists() else None
    try:
        window = webview.create_window("My OpenCode", url,
                                       width=1280, height=860,
                                       min_size=(800, 600),
                                       resizable=True, icon=icon)
        webview.start(private_mode=False)
    except Exception as e:
        print(f"pywebview failed ({e}); opening in browser instead.")
        webbrowser.open(url)
        while True:
            time.sleep(60)


def run_browser():
    url = f"http://127.0.0.1:{PORT}"
    webbrowser.open(url)
    while True:
        time.sleep(60)


def main():
    already_running = is_port_open(PORT)
    if not already_running:
        threading.Thread(target=start_server, daemon=True).start()
    if not wait_server_ready(PORT):
        print(f"Server did not become ready on port {PORT}. "
              "Check the logs and try again.")
        sys.exit(1)
    if "--browser" in sys.argv:
        run_browser()
    else:
        try:
            run_desktop()
        except ImportError:
            print("pywebview not installed. Opening in browser.")
            print("Install: pip install pywebview")
            run_browser()


if __name__ == "__main__":
    main()
