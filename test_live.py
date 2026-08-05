"""Live integration tests with a real Ollama model (not mocks).

Run:  python test_live.py          # all scenarios, skips if Ollama/model missing
      python test_live.py --full   # force-run even if model not preinstalled

These catch regressions in the prompt/tool-format that mock tests can't.
Requires: Ollama running on 127.0.0.1:11434 with qwen2.5-coder:7b.
"""
import os, sys, time, json
from pathlib import Path

sys.path.insert(0, r"E:\My OpenCode1")
os.environ.setdefault("PYTHONUTF8", "1")

import requests
from tools import init_config, init_backup
import agent as agent_mod
from agent import run_agent_loop, MODEL, WORK_DIR, _pending_clear

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LIVE_MODEL = os.environ.get("AI_MODEL", "qwen2.5-coder:7b")
FORCE = "--full" in sys.argv
SCENARIO_DIR = WORK_DIR / ".live_tests"

init_config()
init_backup()
agent_mod.NO_CONFIRM = True  # live tests must not block on [CONFIRM] dialogs


def ollama_ready():
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        names = [m.get("name", "") for m in tags]
        return any(n.startswith(LIVE_MODEL.split(":")[0]) for n in names), names
    except Exception:
        return False, []


def scenario_create_file():
    """'create hello.py with function greet' -> file must exist with def greet."""
    path = SCENARIO_DIR / "hello.py"
    if path.exists():
        path.unlink()
    sid = "live-create"
    _pending_clear(sid)
    msgs = [{"role": "user", "content":
             f"Create the file {path.relative_to(WORK_DIR).as_posix()} with a function "
             "greet(name) that prints 'Hello, ' + name. Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid)
    dt = time.time() - t0
    created = path.exists()
    content = path.read_text("utf-8") if created else ""
    ok = created and "def greet" in content
    print(f"  [{'OK' if ok else 'FAIL'}] create hello.py/greet "
          f"({round(dt, 1)}s, {len(out)} chars out)"
          + ("" if ok else f" | file exists={created} | content={content[:200]!r}"))
    if not ok:
        print("  agent output tail:", out[-400:])
    return ok


def scenario_simple_question():
    """'what is 2+2?' -> answer without tools, contains '4'."""
    sid = "live-q"
    _pending_clear(sid)
    t0 = time.time()
    out = run_agent_loop([{"role": "user", "content": "What is 2+2? Answer in one word."}], sid)
    dt = time.time() - t0
    ok = "4" in out and "[tool:" not in out
    print(f"  [{'OK' if ok else 'FAIL'}] simple question ({round(dt, 1)}s) | out: {out[:150]!r}")
    return ok


def main():
    ready, names = ollama_ready()
    if not ready:
        print(f"SKIP: Ollama model {LIVE_MODEL} not found (found: {names[:5]}) — "
              "install with: ollama pull qwen2.5-coder:7b")
        sys.exit(0)
    SCENARIO_DIR.mkdir(exist_ok=True)
    print(f"Live integration tests (model={LIVE_MODEL}, dir={SCENARIO_DIR})")
    results = [scenario_create_file(), scenario_simple_question()]
    print("=" * 40)
    print(f"{sum(results)}/{len(results)} live scenarios passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
