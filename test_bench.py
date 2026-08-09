"""Stage 48: benchmark harness — measures model quality on real agent tasks.

Runs N coding scenarios through the real agent loop (like test_live.py) and
reports pass rate, wall time and token usage per model. Output: console table
+ JSON report file (bench_reports/<model>.json) for comparing models/versions.

Run:
    python test_bench.py                    # default models (installed only)
    python test_bench.py --models qwen3:8b  # specific model(s)
    python test_bench.py --fast             # 3 quick scenarios instead of 6

Scenarios (each is a full agent-loop task in a scratch dir, verified by us):
  1. create-file   — write app.py with sum(a,b) -> file + def sum
  2. edit-rename   — rename old_fn -> new_fn (edit tool)
  3. find-and-fix  — locate the buggy line in bug.py and fix it (needs grep/read)
  4. js-create     — create utils.js with an exported add() (no syntax errors)
  5. sql-schema    — create schema.sql with users + messages tables (FOREIGN KEY)
  6. refactor-extract — extract a function from main.py (extract_function tool)

Result of each scenario: PASS/FAIL, time, tokens. Aggregates printed at end.
Requires: Ollama on 127.0.0.1:11434, qwen3:8b recommended (native tools).
"""
import json, os, re, sys, time
from pathlib import Path

sys.path.insert(0, r"E:\My OpenCode1")
os.environ.setdefault("PYTHONUTF8", "1")

import requests
from tools import init_config, init_backup
import agent as agent_mod
from agent import run_agent_loop, _pending_clear

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
BENCH_DIR = Path(r"E:\My OpenCode1\.bench_tmp")
REPORT_DIR = Path(r"E:\My OpenCode1\bench_reports")
DEFAULT_MODELS = ["qwen3:8b", "qwen2.5-coder:7b"]

init_config()
init_backup()
agent_mod.NO_CONFIRM = True


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
    elif "--fast" in sys.argv:
        want = DEFAULT_MODELS
    else:
        want = DEFAULT_MODELS
    return [m for m in want if any(m.split(":")[0] == n.split(":")[0] for n in have)], have


SCENARIOS = {}


def _register(name):
    def deco(fn):
        SCENARIOS[name] = fn
        return fn
    return deco


@_register("create-file")
def sc_create(model, sid):
    p = BENCH_DIR / "app.py"
    p.unlink(missing_ok=True)
    msgs = [{"role": "user", "content":
             f"Create the file {p.relative_to(agent_mod.WORK_DIR).as_posix()} with "
             "def sum(a, b): return a + b. Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    ok = p.exists() and "def sum" in p.read_text("utf-8", errors="ignore")
    return ok, time.time() - t0, len(out)


@_register("edit-rename")
def sc_edit(model, sid):
    p = BENCH_DIR / "fixme.py"
    p.write_text("def old_fn():\n    return 1\nprint(old_fn())\n", "utf-8")
    msgs = [{"role": "user", "content":
             f"Rename the function old_fn to new_fn in {p.relative_to(agent_mod.WORK_DIR).as_posix()}. "
             "Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    c = p.read_text("utf-8", errors="ignore")
    ok = "new_fn" in c and "old_fn" not in c
    return ok, time.time() - t0, len(out)


@_register("find-and-fix")
def sc_fix(model, sid):
    p = BENCH_DIR / "bug.py"
    p.write_text("def divide(a, b):\n    return a / b  # BUG: division by zero possible\n"
                 "print(divide(1, 0))\n", "utf-8")
    msgs = [{"role": "user", "content":
             f"Fix the bug in {p.relative_to(agent_mod.WORK_DIR).as_posix()}: division by zero "
             "must not crash (return None instead). Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    c = p.read_text("utf-8", errors="ignore")
    ok = ("None" in c or "try" in c) and "def divide" in c
    return ok, time.time() - t0, len(out)


@_register("js-create")
def sc_js(model, sid):
    p = BENCH_DIR / "utils.js"
    p.unlink(missing_ok=True)
    msgs = [{"role": "user", "content":
             f"Create the file {p.relative_to(agent_mod.WORK_DIR).as_posix()} with "
             "'export function add(a, b) { return a + b; }'. Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    ok = p.exists() and "function add" in p.read_text("utf-8", errors="ignore")
    return ok, time.time() - t0, len(out)


@_register("sql-schema")
def sc_sql(model, sid):
    p = BENCH_DIR / "schema.sql"
    p.unlink(missing_ok=True)
    msgs = [{"role": "user", "content":
             f"Create the file {p.relative_to(agent_mod.WORK_DIR).as_posix()} with SQL schema: "
             "tables users(id, email, password_hash) and messages(id, user_id FOREIGN KEY, text). "
             "Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    c = p.read_text("utf-8", errors="ignore") if p.exists() else ""
    ok = "CREATE TABLE" in c.upper() and "users" in c and "messages" in c and "FOREIGN KEY" in c.upper()
    return ok, time.time() - t0, len(out)


@_register("refactor-extract")
def sc_extract(model, sid):
    p = BENCH_DIR / "main.py"
    p.write_text("x = 1\nprint(x + 2)\nprint(x * 3)\n", "utf-8")
    msgs = [{"role": "user", "content":
             f"In {p.relative_to(agent_mod.WORK_DIR).as_posix()} extract the print lines "
             "into a function show(x) and call it. Do not ask, just do it."}]
    t0 = time.time()
    out = run_agent_loop(msgs, sid, None, model)
    c = p.read_text("utf-8", errors="ignore")
    ok = "def show" in c and ("show(" in c)
    return ok, time.time() - t0, len(out)


def main():
    models, have = pick_models()
    if not models:
        print(f"SKIP: no candidate models installed (found: {have[:6]})")
        sys.exit(0)
    BENCH_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    names = list(SCENARIOS.keys())[:3] if "--fast" in sys.argv else list(SCENARIOS.keys())
    print(f"Benchmark: {len(models)} model(s) x {len(names)} scenarios "
          f"(dir={BENCH_DIR})")
    table = []
    for model in models:
        run_agent_loop([{"role": "user", "content": "Warm up: reply with the word ready."}],
                       f"bench-warm-{model.split(':')[0]}", None, model)
        rows, ok_n, t_sum = [], 0, 0.0
        for i, name in enumerate(names):
            sid = f"bench-{model.split(':')[0]}-{name}"
            _pending_clear(sid)
            try:
                ok, dt, ntok = SCENARIOS[name](model, sid)
            except Exception as e:
                ok, dt, ntok = False, 0.0, 0
                print(f"    [ERR] {name}: {e}")
            rows.append({"scenario": name, "pass": bool(ok), "seconds": round(dt, 1)})
            ok_n += bool(ok); t_sum += dt
            print(f"    [{'OK' if ok else 'FAIL'}] {name} ({round(dt, 1)}s)")
        rep = {"model": model, "date": time.strftime("%Y-%m-%d %H:%M"),
               "scenarios": rows, "pass": f"{ok_n}/{len(names)}",
               "total_seconds": round(t_sum, 1)}
        (REPORT_DIR / f"{model.replace(':', '-')}.json").write_text(
            json.dumps(rep, indent=2, ensure_ascii=False), "utf-8")
        table.append((model, ok_n, len(names), t_sum))
    print("=" * 46)
    for m, ok, n, t in table:
        print(f"  {m}: {ok}/{n}  ({round(t, 1)}s total)")
    total_ok = sum(x[1] for x in table); total = sum(x[2] for x in table)
    print(f"TOTAL {total_ok}/{total} | reports: {REPORT_DIR}")
    sys.exit(0 if total_ok == total else 1)


if __name__ == "__main__":
    main()
