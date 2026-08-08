"""Live integration tests with real Ollama models (not mocks).

Run:  python test_live.py                # all installed candidate models
      python test_live.py --full         # force-run even if model not installed
      python test_live.py --models qwen3:8b   # specific model(s, comma-sep)

Scenarios: create file+verify, simple question, edit existing file.
Each runs through the real agent loop (legacy ```tool or native tools=,
auto-detected per model). Catches prompt/tool-format regressions.
Requires: Ollama running on 127.0.0.1:11434.
"""
import os, sys, time, json
from pathlib import Path

sys.path.insert(0, r"E:\My OpenCode1")
os.environ.setdefault("PYTHONUTF8", "1")

import requests
from tools import init_config, init_backup
import agent as agent_mod
from agent import run_agent_loop, WORK_DIR, _pending_clear

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
FORCE = "--full" in sys.argv
SCENARIO_DIR = WORK_DIR / ".live_tests"
DEFAULT_MODELS = ["qwen2.5-coder:7b", "qwen3:8b", "deepseek-coder-v2:16b"]

init_config()
init_backup()
agent_mod.NO_CONFIRM = True  # live tests must not block on [CONFIRM] dialogs


def installed_models():
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        return [m.get("name", "") for m in tags]
    except Exception:
        return []


def pick_models():
    have = installed_models()
    if "--models" in sys.argv:
        want = [m for m in sys.argv[sys.argv.index("--models") + 1].split(",") if m]
    else:
        want = DEFAULT_MODELS
    if not have:
        return [], have
    if FORCE:
        return [m for m in want if any(m.split(":")[0] in n for n in have)], have
    return [m for m in want if any(m.split(":")[0] == n.split(":")[0] for n in have)], have


def scenario_create_file(model):
    """'create hello.py with function greet' -> file must exist with def greet."""
    path = SCENARIO_DIR / f"hello_{model.split(':')[0]}.py"
    if path.exists():
        path.unlink()
    sid = f"live-create-{model.split(':')[0]}"
    _pending_clear(sid)
    msgs = [{"role": "user", "content":
             f"Create the file {path.relative_to(WORK_DIR).as_posix()} with a function "
             "greet(name) that prints 'Hello, ' + name. Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    dt = time.time() - t0
    created = path.exists()
    content = path.read_text("utf-8") if created else ""
    ok = created and "def greet" in content
    print(f"    [{'OK' if ok else 'FAIL'}] create file ({round(dt, 1)}s)"
          + ("" if ok else f" | exists={created} | content={content[:200]!r}\n      tail: {out[-300:]}"))
    return ok


def scenario_simple_question(model):
    """'what is 2+2?' -> answer without tools, contains '4'."""
    sid = f"live-q-{model.split(':')[0]}"
    _pending_clear(sid)
    t0 = time.time()
    out = run_agent_loop([{"role": "user", "content": "What is 2+2? Answer in one word."}],
                         sid, None, model)
    dt = time.time() - t0
    ok = (("4" in out or "four" in out.lower()) and "[tool:" not in out)
    print(f"    [{'OK' if ok else 'FAIL'}] simple question ({round(dt, 1)}s) | out: {out[:150]!r}")
    return ok


def scenario_edit_file(model):
    """'rename function old_fn -> new_fn in fixme.py' -> edit applied."""
    path = SCENARIO_DIR / f"fixme_{model.split(':')[0]}.py"
    path.write_text("def old_fn():\n    return 1\n\nprint(old_fn())\n", "utf-8")
    sid = f"live-edit-{model.split(':')[0]}"
    _pending_clear(sid)
    msgs = [{"role": "user", "content":
             f"Rename the function old_fn to new_fn in {path.relative_to(WORK_DIR).as_posix()}. "
             "Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    dt = time.time() - t0
    content = path.read_text("utf-8", errors="ignore")
    ok = "new_fn" in content and "old_fn" not in content
    print(f"    [{'OK' if ok else 'FAIL'}] edit rename ({round(dt, 1)}s)"
          + ("" if ok else f" | content={content[:200]!r}\n      tail: {out[-300:]}"))
    return ok


def main():
    models, have = pick_models()
    if not models:
        print(f"SKIP: no candidate models found (found: {have[:6]}) — "
              f"install with: ollama pull {' '.join(DEFAULT_MODELS)}")
        sys.exit(0)
    SCENARIO_DIR.mkdir(exist_ok=True)
    scenarios = [scenario_create_file, scenario_simple_question, scenario_edit_file]
    print(f"Live integration tests (dir={SCENARIO_DIR})")
    summary = []
    for model in models:
        print(f"  model={model} (native tools: "
              f"{'yes' if __import__('tools').native_supported(model) else 'no'})")
        t0 = time.time()
        run_agent_loop([{"role": "user", "content": "Warm up: reply with the word ready."}],
                       f"live-warmup-{model.split(':')[0]}", None, model)
        print(f"    warm-up {round(time.time() - t0, 1)}s (loaded into VRAM)")
        res = [s(model) for s in scenarios]
        summary.append((model, sum(res), len(res)))
    print("=" * 40)
    for m, ok, n in summary:
        print(f"  {m}: {ok}/{n}")
    total_ok = sum(x[1] for x in summary)
    total = sum(x[2] for x in summary)
    print(f"TOTAL {total_ok}/{total} live scenarios passed")
    sys.exit(0 if total_ok == total else 1)


if __name__ == "__main__":
    main()
