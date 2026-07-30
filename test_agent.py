#!/usr/bin/env python3
"""Smoke tests for agent tool loop."""
import json, sys, os, tempfile
from pathlib import Path
sys.path.insert(0, "E:\\My OpenCode1")
from tools import execute_tool, backup, undo, verify_file, resolve, init_config, init_backup
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

if __name__ == "__main__":
    print(f"\nSmoke tests for agent.py\n{'='*40}")
    tests = [test_read, test_read_absolute, test_read_url, test_list, test_glob,
             test_write_and_undo, test_edit, test_bash, test_verify_py, test_verify_json,
             test_backup_undo]
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
