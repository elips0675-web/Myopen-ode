#!/usr/bin/env python3
"""Smoke tests for agent tool loop."""
import json, sys, os, tempfile
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
    """Integration: loop returns plain text without tools."""
    import agent as agent_mod
    def mock_ollama(msgs, model):
        return "Just a plain answer.", 5
    original = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "hello"}], None)
    finally:
        agent_mod.call_ollama = original
    assert out.strip() == "Just a plain answer.", f"plain loop failed: {out[:200]}"
    print("  [OK] agent loop: plain text")

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

if __name__ == "__main__":
    print(f"\nSmoke tests for agent.py\n{'='*40}")
    tests = [test_read, test_read_absolute, test_read_url, test_list, test_glob,
             test_write_and_undo, test_edit, test_bash, test_verify_py, test_verify_json,
             test_backup_undo, test_db_query, test_testgen, test_validation, test_save_api,
             test_terminal_api, test_deps_tool, test_audit, test_rag_cache_incremental,
             test_agent_loop_tool_call, test_agent_loop_plain_text, test_agent_loop_shell_alias,
             test_sessions_sqlite, test_session_json_migration]
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
