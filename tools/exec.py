"""Tool execution: validation, bash sandbox, unified diff, execute_tool."""
import ast
import difflib
import glob as _glob, json, os, re, subprocess, sys
from pathlib import Path
import logging
from . import _state as _s
from ._state import WORK_DIR, MODEL, TOOL_SCHEMAS, TODO_LIST, TODO_LOCK
from ._state import _sync_register
from .paths import resolve, ensure_safe_path, _similar_files
from .backup import backup, undo, git, git_prebackup, git_restore_all, diff_preview, verify_file
from .backup import git_auto_commit as _git_auto_commit
from .plugins import call_plugin
from .llm import call_ollama
from .audit import _audit, _stats_record
from core.safety.bash_guard import check_bash as _check_bash, docker_bash  # noqa: F401

log = logging.getLogger("tools")

def check_bash(cmd):
    """Block dangerous shell commands (whitelist + blacklist + nested checks)."""
    return _check_bash(cmd, WORK_DIR)

# ─── post-write syntax guard (AST) ────────────────────────
def _syntax_check(path):
    """AST-level syntax check after write/edit/patch for Python/JSON/JS.

    Returns "OK" or "ERROR: <msg> (line N)" for checkable files; None when the
    language is not checkable or no checker binary is available (e.g. node
    missing). Uses only the stdlib (ast) so there are no hard dependencies."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".py", ".json", ".js", ".mjs", ".cjs", ".ts"):
        return None
    try:
        code = Path(path).read_text("utf-8", errors="replace")
    except OSError as e:
        return f"ERROR: cannot read for syntax check ({e})"
    if suffix == ".py":
        try:
            ast.parse(code, filename=str(path))
            return "OK"
        except SyntaxError as e:
            return f"ERROR: {e.msg} (line {e.lineno})"
    if suffix == ".json":
        try:
            json.loads(code)
            return "OK"
        except ValueError as e:
            return f"ERROR: invalid JSON ({e})"
    try:
        r = subprocess.run(["node", "--check", str(path)], capture_output=True,
                           text=True, timeout=30)
        if r.returncode == 0:
            return "OK"
        tail = (r.stderr or r.stdout).strip().split("\n")[-1]
        return f"ERROR: {tail[:300]}"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

# ─── unified diff parser ──────────────────────────────────
def _parse_hunks(diff_text):
    """Parse unified diff into hunks: [{old_start, lines: [op lines]}]."""
    hunks = []
    cur = None
    for line in diff_text.split("\n"):
        if line.startswith("@@") and not line.startswith("@@@"):
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not m:
                cur = None
                continue
            cur = {"old_start": int(m.group(1)), "lines": []}
            hunks.append(cur)
        elif cur is not None:
            cur["lines"].append(line)
    return hunks

def _apply_diff(content, diff_text):
    """Apply a unified diff to content using hunk line numbers.
    Hunks are applied bottom-up so positions never shift. Returns None on mismatch."""
    lines = content.splitlines(keepends=True)
    hunks = _parse_hunks(diff_text)
    if not hunks:
        return None
    for h in reversed(hunks):
        old_start = h["old_start"]  # 1-based
        if old_start < 1 or old_start > len(lines) + 1:
            return None
        ops = []
        for line in h["lines"]:
            if line.startswith("+"):
                ops.append(("+", line[1:] + "\n"))
            elif line.startswith("-"):
                ops.append(("-", line[1:] + "\n"))
            elif line.startswith(" "):
                ops.append((" ", line[1:] + "\n"))
            elif line.startswith("\\"):
                continue  # "\ No newline at end of file"
            elif line.strip() == "":
                continue  # trailing separator from split("\n")
            else:
                return None
        new_content = lines[:old_start - 1]
        i = old_start - 1
        ok = True
        for op, text in ops:
            if op == " ":
                if i >= len(lines) or lines[i] != text:
                    ok = False
                    break
                new_content.append(lines[i])
                i += 1
            elif op == "-":
                if i >= len(lines):
                    ok = False
                    break
                i += 1
            elif op == "+":
                new_content.append(text)
        if not ok:
            return None
        new_content.extend(lines[i:])
        lines = new_content
    return "".join(lines)

def _validate_patch(diff_text):
    """Validate unified diff format."""
    if not any(line.startswith("@@") for line in diff_text.split("\n")):
        return "Invalid diff: no hunk headers (@@)"
    if "--- " not in diff_text or "+++ " not in diff_text:
        return "Invalid diff: missing file headers"
    return None

# ─── validation ───────────────────────────────────────────
def _path_dir_hint(p):
    """Stage 36: semantic argument validation — a path that resolves to an
    existing DIRECTORY is almost always an invented/wrong argument (models
    hallucinate `read /tmp`-style paths). Fail fast with a concrete hint
    instead of a cryptic OS error. Includes the path-jail check."""
    err = ensure_safe_path(p)
    if err:
        return err
    try:
        pp = resolve(p)
    except Exception:
        return None
    if pp.exists() and pp.is_dir():
        return (f"Error: '{p}' looks like a directory, but write/edit/patch needs a "
                f"FILE path. Use the `list` tool to see its contents or `glob` to "
                f"find the real file before retrying.")
    return None


def validate_tool(tc):
    name = tc.get("tool", "")
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        return f"Unknown tool '{name}'. Available tools: {', '.join(sorted(TOOL_SCHEMAS))}"
    req = schema.get("required", [])
    if tc.get("tool") == "patch" and isinstance(tc.get("files"), list):
        req = [k for k in req if k not in ("path", "diff")]
    missing = [k for k in req if k not in tc]
    if missing: return f"Missing required fields: {', '.join(missing)} in {name}"
    def need_str(key, label):
        if key in tc and not isinstance(tc[key], str): return f"{label} must be string"
    def need_int(key, label, min_val=None, max_val=None):
        if key in tc and not isinstance(tc[key], int): return f"{label} must be integer"
        if key in tc and isinstance(tc[key], int):
            if min_val is not None and tc[key] < min_val: return f"{label} must be >= {min_val}"
            if max_val is not None and tc[key] > max_val: return f"{label} must be <= {max_val}"
    for key in ("path", "content", "old", "new", "cmd", "pattern", "query", "text", "name", "url", "diff", "message", "operation", "prompt"):
        err = need_str(key, key); 
        if err: return err
    for key, lo, hi in (("top_k", 1, 50), ("line", 0, 10**9), ("character", 0, 10**9), ("index", 0, 10**9), ("max_results", 1, 20)):
        err = need_int(key, key, lo, hi)
        if err: return err
    if tc.get("tool") == "plan" and "steps" in tc:
        if isinstance(tc["steps"], str):
            tc["steps"] = [s.strip() for s in re.split(r'[.,;\n]+', tc["steps"]) if s.strip()]
        elif not isinstance(tc["steps"], list):
            return "plan.steps must be an array of strings"
    if tc.get("tool") == "question" and "options" in tc:
        if isinstance(tc["options"], str):
            tc["options"] = [o.strip() for o in tc["options"].split(",") if o.strip()]
        elif not isinstance(tc["options"], list):
            return "question.options must be an array"
    if tc.get("tool") == "task" and tc.get("agent") not in ("explore", "scout", "general"):
        return "task.agent must be one of: explore, scout, general"
    if tc.get("tool") == "todo" and tc.get("action") not in ("add", "complete", "list"):
        return "todo.action must be one of: add, complete, list"
    if tc.get("tool") == "lsp" and tc.get("operation") not in ("definition", "references", "hover", "symbols", "rename", "completion"):
        return f"lsp.operation must be one of: definition, references, hover, symbols, rename, completion"
    if tc.get("tool") == "mcp":
        if not isinstance(tc.get("server"), str) or not tc.get("server"): return "mcp.server must be a non-empty string"
        if tc.get("server") != "_list" and not isinstance(tc.get("call"), str): return "mcp.call must be a string"
    if tc.get("tool") == "patch" and "diff" in tc:
        err = _validate_patch(tc["diff"])
        if err: return err
    if tc.get("tool") == "patch" and isinstance(tc.get("files"), list):
        for f in tc["files"]:
            if not isinstance(f, dict) or not f.get("path") or not isinstance(f.get("diff"), str):
                return "patch.files must be an array of {path, diff}"
            err = _validate_patch(f["diff"])
            if err: return f"patch.files[{f.get('path')}]: {err}"
    return ""

# ─── per-tool implementations ─────────────────────────────
def _tool_read(args):
    p = args["path"]
    if p.startswith(("http://", "https://")):
        try:
            import requests as _requests
            r = _requests.get(p, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            return r.text[:5000]
        except Exception as e: return f"Error fetching URL: {e}"
    err = ensure_safe_path(p)
    if err: return err
    pp = resolve(p)
    if not pp.exists():
        return f"Error: {p} not found" + (_similar_files(p) or ". Use the glob tool to find files. Do NOT give tutorials — retry with a correct path.")
    if pp.is_dir():
        return (f"Error: '{p}' looks like a directory — read needs a FILE path. "
                f"Use `list` to see its contents or `glob` to find the real file.")
    return pp.read_text("utf-8")

def _tool_web(args):
    url = args.get("url", "")
    try:
        import requests as _requests
        r = _requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        return r.text[:5000]
    except Exception as e: return f"Error: {e}"

def _tool_write(args):
    err = _path_dir_hint(args["path"])
    if err: return err
    p = resolve(args["path"])
    rel = str(p.relative_to(_s.WORK_DIR.resolve())) if _s.WORK_DIR in p.parents else str(p)
    backup(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args["content"], "utf-8")
    v = verify_file(str(p))
    sc = _syntax_check(str(p))
    gc = _git_auto_commit(rel, "write")
    msg = f"Written {len(args['content'])}b to {p}"
    if v: msg += f"\nVerify: {v[:500]}"
    if sc: msg += f"\nSyntax: {sc}"
    if gc: msg += f"\n{gc}"
    return msg

def _edit_old_stats(content, old):
    """Count exact occurrences of `old`; if absent, find the closest line (fuzzy)."""
    n = content.count(old)
    if n > 0:
        return n, None
    best, best_r = None, 0.0
    for line in content.splitlines():
        r = difflib.SequenceMatcher(None, old.strip(), line.strip()).ratio()
        if r > best_r:
            best_r, best = r, line.strip()
    return 0, (best, best_r) if best_r >= 0.8 else None

def _tool_edit(args):
    err = _path_dir_hint(args["path"])
    if err: return err
    p = resolve(args["path"])
    if not p.exists():
        return f"Error: {p} not found" + (_similar_files(args["path"]) or ". Use the glob tool to find files. Do NOT give tutorials — retry with a correct path.")
    old = args.get("old", ""); new = args.get("new", "")
    content = p.read_text("utf-8")
    count, fuzzy = _edit_old_stats(content, old)
    if count == 0:
        lines = content.split("\n")
        snippet = "\n".join(lines[:20]) if len(lines) <= 20 else "\n".join(lines[:10]) + "\n...\n" + "\n".join(lines[-5:])
        hint = ""
        if fuzzy:
            hint = (f"\nClosest match in file: `{fuzzy[0][:160]}` "
                    f"(similarity {int(fuzzy[1]*100)}%). Copy it EXACTLY.")
        return f"Error: text not found in {args['path']}.{hint}\nCurrent file content (first lines):\n```\n{snippet[:800]}\n```\nUse the EXACT text from the file."
    if count > 1:
        return (f"Error: 'old' text found {count} times in {args['path']} — ambiguous, "
                f"edit NOT applied.\nMake the old text unique: include the surrounding lines "
                f"from the file (copy EXACTLY from read output), so only one match remains.")
    rel = str(p.relative_to(_s.WORK_DIR.resolve())) if _s.WORK_DIR in p.parents else str(p)
    backup(rel)
    p.write_text(content.replace(old, new), "utf-8")
    v = verify_file(str(p))
    sc = _syntax_check(str(p))
    gc = _git_auto_commit(rel, "edit")
    msg = f"Replaced in {p}"
    if v: msg += f"\nVerify: {v[:500]}"
    if sc: msg += f"\nSyntax: {sc}"
    if gc: msg += f"\n{gc}"
    return msg

def _ast_rename_symbol(args):
    """Stage 28: rename a Python symbol (function/class/variable/param) via
    AST node positions — no regex, no substring matches."""
    err = ensure_safe_path(args["path"])
    if err: return err
    p = resolve(args["path"])
    if not str(p).endswith(".py"):
        return "Error: rename_symbol supports Python (.py) files only"
    if not p.exists():
        return f"Error: {p} not found" + (_similar_files(args["path"]) or "")
    old, new = args.get("old_name", ""), args.get("new_name", "")
    if not old or not new:
        return "Error: old_name and new_name are required"
    if old == new:
        return "Error: old_name and new_name are identical"
    if not new.isidentifier():
        return f"Error: '{new}' is not a valid Python identifier"
    src = p.read_text("utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"Error: source file has syntax errors: {e}"
    hits = []
    old_b = old.encode("utf-8")
    src_lines = src.splitlines(keepends=True)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.arg)):
            if getattr(node, "id", None) == old:
                hits.append((node.lineno, node.col_offset, node.col_offset + len(old_b)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == old:
                # py3.14+: col_offset points at 'def'/'class', find the name
                ln = src_lines[node.lineno - 1].encode("utf-8")
                pos = ln.find(old_b, node.col_offset)
                if pos >= 0:
                    hits.append((node.lineno, pos, pos + len(old_b)))
    if not hits:
        return f"Error: symbol '{old}' not found in {p}"
    lines = src.splitlines(keepends=True)
    applied = 0
    for lineno, col, end in sorted(hits, reverse=True):
        line = lines[lineno - 1]
        b = line.encode("utf-8")
        if 0 <= col <= end <= len(b):
            lines[lineno - 1] = (b[:col] + new.encode("utf-8") + b[end:]).decode("utf-8")
            applied += 1
    new_src = "".join(lines)
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        return f"Error: renamed source fails syntax check: {e}"
    rel = str(p.relative_to(_s.WORK_DIR.resolve())) if _s.WORK_DIR in p.parents else str(p)
    backup(rel)
    p.write_text(new_src, "utf-8")
    gc = _git_auto_commit(rel, "rename_symbol")
    return f"renamed '{old}' -> '{new}' in {p} ({applied} occurrence(s))" + (f"\n{gc}" if gc else "")


def _ast_extract_function(args):
    """Stage 28: extract a line range into a new function and replace the
    range with a call. Params and call args are explicit (model supplies
    them) so the result is predictable."""
    err = ensure_safe_path(args["path"])
    if err: return err
    p = resolve(args["path"])
    if not str(p).endswith(".py"):
        return "Error: extract_function supports Python (.py) files only"
    if not p.exists():
        return f"Error: {p} not found"
    name = args.get("name", "")
    params = args.get("params") or []
    call_args = args.get("call_args") or []
    if not name or not name.isidentifier():
        return "Error: name must be a valid Python identifier"
    if any(not (isinstance(x, str) and x.isidentifier()) for x in params):
        return "Error: params must be valid identifiers"
    lines = p.read_text("utf-8").splitlines(keepends=True)
    ls, le = args.get("line_start"), args.get("line_end")
    if not isinstance(ls, int) or not isinstance(le, int) or ls < 1 or le < ls or le > len(lines):
        return f"Error: invalid line range {ls}..{le} (file has {len(lines)} lines)"
    body = lines[ls - 1:le]
    indent = len(body[0]) - len(body[0].lstrip(" \t"))
    prefix = body[0][:indent]
    base_indent = " " * indent
    stripped = []
    for ln in body:
        if ln.strip():
            stripped.append(ln[indent:] if len(ln) > indent else ln.lstrip(" \t"))
        else:
            stripped.append("\n")
    head = stripped[0]
    if head.startswith("def ") or head.startswith("class ") or head.startswith("async def "):
        return "Error: range starts with a def/class — extract only executable statements"
    def_text = f"def {name}({', '.join(params)}):\n" + "".join(("    " + ln if ln.strip() else ln) for ln in stripped)
    if not def_text.endswith("\n"):
        def_text += "\n"
    call_text = f"{base_indent}{name}({', '.join(call_args)})\n"
    new_lines = lines[:ls - 1] + [call_text] + lines[le:]
    if new_lines and new_lines[-1] and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    new_lines += [def_text]
    new_src = "".join(new_lines)
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        return f"Error: extracted source fails syntax check: {e}"
    rel = str(p.relative_to(_s.WORK_DIR.resolve())) if _s.WORK_DIR in p.parents else str(p)
    backup(rel)
    p.write_text(new_src, "utf-8")
    gc = _git_auto_commit(rel, "extract_function")
    return f"extracted lines {ls}..{le} into def {name}({', '.join(params)}) in {p}" + (f"\n{gc}" if gc else "")


def _ast_inline_variable(args):
    """Stage 28: inline a simple `var = expr` assignment: remove the line and
    replace later uses of var with the expression text."""
    err = ensure_safe_path(args["path"])
    if err: return err
    p = resolve(args["path"])
    if not str(p).endswith(".py"):
        return "Error: inline_variable supports Python (.py) files only"
    if not p.exists():
        return f"Error: {p} not found"
    var = args.get("var_name", "")
    line_no = args.get("line_number")
    if not var or not isinstance(line_no, int):
        return "Error: var_name and line_number are required"
    src = p.read_text("utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"Error: source file has syntax errors: {e}"
    assign = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.lineno == line_no \
           and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
           and node.targets[0].id == var:
            assign = node
            break
    if assign is None:
        return f"Error: no top-level '{var} = ...' on line {line_no}"
    expr_text = ast.get_source_segment(src, assign.value)
    if not expr_text:
        return "Error: could not extract expression text"
    uses = []
    targets = {id(t) for t in ast.walk(assign) if isinstance(t, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == var and node is not assign.targets[0]:
            if node.lineno > line_no and node.lineno != assign.lineno:
                uses.append((node.lineno, node.col_offset, node.end_col_offset))
    lines = src.splitlines(keepends=True)
    lines[line_no - 1] = ""
    for lineno, col, end in sorted(uses, reverse=True):
        ln = lines[lineno - 1]
        b = ln.encode("utf-8")
        if 0 <= col <= end <= len(b):
            lines[lineno - 1] = (b[:col] + expr_text.encode("utf-8") + b[end:]).decode("utf-8")
    new_src = "".join(lines)
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        return f"Error: inlined source fails syntax check: {e}"
    rel = str(p.relative_to(_s.WORK_DIR.resolve())) if _s.WORK_DIR in p.parents else str(p)
    backup(rel)
    p.write_text(new_src, "utf-8")
    gc = _git_auto_commit(rel, "inline_variable")
    return f"inlined '{var}' from line {line_no} in {p} ({len(uses)} use(s))" + (f"\n{gc}" if gc else "")


def _tool_bash(args):
    cmd = args["cmd"]
    blocked = check_bash(cmd)
    if blocked: return blocked
    cwd = resolve(args.get("cwd", ".")) if args.get("cwd") else WORK_DIR
    bt = _s.BASH_TIMEOUT
    out = docker_bash(cmd, WORK_DIR, bt)
    if out is not None:
        return out
    r = subprocess.run(cmd, shell=True, cwd=str(cwd) if cwd else str(WORK_DIR), capture_output=True, text=True, timeout=bt)
    return ((r.stdout or "")[-3000:] + ("\nSTDERR:\n" + (r.stderr or "")[-1000:] if r.stderr else ""))

def _tool_glob(args):
    pattern = args["pattern"]
    cwd_arg = args.get("cwd", ".")
    err = ensure_safe_path(cwd_arg)
    if err: return err
    base = Path(cwd_arg) if args.get("cwd") else WORK_DIR
    if not base.is_absolute():
        if "\\" in pattern or pattern.startswith("/") or ":" in pattern:
            p = Path(pattern)
            if p.is_absolute():
                base = p.root; pattern = str(p.relative_to(p.root))
    fs = list(_glob.glob(str(base / pattern), recursive=True))[:60]
    return "\n".join(fs) if fs else "No matches"

def _tool_grep(args):
    pat, inc = args["pattern"], args.get("include", "*")
    cwd = args.get("cwd", ".")
    err = ensure_safe_path(cwd)
    if err: return err
    cwd = str(resolve(cwd))
    r = subprocess.run(f'rg -n "{pat}" --glob "{inc}"', shell=True, cwd=cwd, capture_output=True, text=True, timeout=30)
    return "\n".join(r.stdout.split("\n")[:60]) or "No matches"

def _tool_list(args):
    err = ensure_safe_path(args.get("path", "."))
    if err: return err
    p = resolve(args.get("path", "."))
    items = [f"{'[DIR]' if x.is_dir() else '     '} {x.name}" for x in sorted(p.iterdir())]
    return "\n".join(items) if items else "(empty)"

def _tool_diff(args):
    stat = git("diff", "--stat")
    names = git("diff", "--name-only")
    diff_out = git("diff", "--unified=2")
    lines = diff_out.split("\n")
    parsed = []
    current_file = ""
    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            current_file = parts[-1] if len(parts) > 1 else line
            parsed.append(f"\n--- {current_file}")
        elif line.startswith("@@"):
            parsed.append(f"  {line}")
        elif line.startswith("+") and not line.startswith("+++"):
            parsed.append(f"+{line[1:]}")
        elif line.startswith("-") and not line.startswith("---"):
            parsed.append(f"-{line[1:]}")
    body = "\n".join(parsed) if parsed else diff_out[:3000]
    return stat + "\n\n" + body[:3000]

def _tool_commit(args):
    git("add", "-A"); return git("commit", "-m", args.get("message", "update"))

def _tool_undo(args):
    err = ensure_safe_path(args.get("path", ""))
    if err: return err
    return undo(args.get("path", ""))

def _tool_verify(args):
    path = args.get("path", "")
    if path:
        err = ensure_safe_path(path)
        if err: return err
    return verify_file(path) if path else "No path specified"

def _tool_search(args):
    import rag as _rag
    return _rag.rag_search(args.get("query", ""), args.get("top_k", 5),
                           scope=args.get("scope") or None)

def _tool_snapshot(args):
    return git_prebackup()

def _tool_restore(args):
    return git_restore_all(args.get("id") or None)

def _tool_websearch(args):
    query = args.get("query", "")
    max_results = int(args.get("max_results", 5))
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                results.append(f"[{i+1}] {r.get('title','')}\n    URL: {r.get('href','')}\n    {r.get('body','')[:300]}")
        return "\n\n".join(results) if results else "No results found"
    except Exception as e:
        return f"Web search error: {e}"

def _tool_question(args):
    text = args.get("text", "")
    opts = args.get("options", [])
    opts_str = " / ".join([f"{i+1}. {o}" for i, o in enumerate(opts)])
    return f"[QUESTION] {text}\n{opts_str}"

def _tool_skill(args):
    skill_name = args.get("name", "")
    skills_dir = WORK_DIR / ".agent_skills"
    if not skills_dir.exists():
        return f"[SKILL] No .agent_skills directory found"
    skill_file = skills_dir / f"{skill_name}.md"
    if not skill_file.exists():
        available = [f.stem for f in skills_dir.glob("*.md")]
        return f"[SKILL] '{skill_name}' not found. Available: {', '.join(available) or 'none'}"
    content = skill_file.read_text("utf-8", errors="ignore")
    return f"[SKILL: {skill_name}]\n{content[:2000]}"

def _tool_patch(args):
    """Apply unified diffs: single file (path+diff) or multiple files at once
    (files=[{path, diff}, ...]). Each file: backup, apply, verify, syntax check."""
    jobs = []
    files = args.get("files")
    if isinstance(files, list) and files:
        for f in files:
            fp, fd = (f or {}).get("path", ""), (f or {}).get("diff", "")
            if fp and fd:
                jobs.append((fp, fd))
    elif args.get("path") and args.get("diff"):
        jobs.append((args["path"], args["diff"]))
    if not jobs:
        return "Error: provide path+diff or files=[{path, diff}, ...]"
    out = []
    for path, diff_text in jobs:
        err = _path_dir_hint(path)
        if err:
            out.append(err)
            continue
        pp = resolve(path)
        if not pp.exists():
            out.append(f"Error: {path} not found")
            continue
        content = pp.read_text("utf-8")
        result = _apply_diff(content, diff_text)
        if result is None:
            out.append(f"Error: patch does not match file content (hunk context mismatch): {path}")
            continue
        backup(str(pp))
        pp.write_text(result, "utf-8")
        v = verify_file(str(pp))
        sc = _syntax_check(str(pp))
        m = f"Patched {path} ({len(pp.read_text('utf-8'))}b)"
        if v: m += f"\nVerify: {v[:300]}"
        if sc: m += f"\nSyntax: {sc}"
        out.append(m)
    if jobs:
        gc = _git_auto_commit([p for p, _ in jobs], "patch")
        if gc:
            out.append(gc)
    return "\n".join(out)

def _tool_task(args):
    agent_type = args.get("agent", "general")
    user_prompt = args.get("prompt", "")
    import tools as _t
    sub_prompt = _t.SUBAGENT_PROMPTS.get(agent_type, _t.GENERAL_PROMPT)
    msgs = [
        {"role": "system", "content": sub_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        # hierarchical delegation: the subagent runs its own tool loop
        from core.agent_loop import run_agent_loop
        import agent as _a
        import types as _types
        d = _types.SimpleNamespace()
        for _name in ("OLLAMA_URL", "PLANNER_MODEL", "MODEL", "WORK_DIR",
                      "MAX_TOKENS", "_available_models", "_cancel_pending",
                      "_cancel_clear", "_pending_get", "_pending_set",
                      "session_interrupted", "_state_path", "load_session",
                      "save_session", "call_ollama", "stream_ollama",
                      "execute_tool", "datetime"):
            setattr(d, _name, getattr(_a, _name))
        d.NO_CONFIRM = True
        res = run_agent_loop(msgs, None, None, model=MODEL, deps=d)
        return f"[SUBAGENT:{agent_type}]\n{res[:3000]}"
    except Exception as e:
        log.warning("subagent loop failed (%s), falling back to single call", e)
        result, _ = call_ollama(msgs, MODEL)
        return f"[SUBAGENT:{agent_type}]\n{result[:3000]}"

def _tool_todo(args):
    action = args.get("action", "list")
    items = args.get("items", [])
    idx = args.get("index", None)
    if action == "add":
        with TODO_LOCK:
            for item in (items if isinstance(items, list) else [items]):
                TODO_LIST.append({"text": item, "done": False})
            n = len(TODO_LIST)
        return f"[TODO] Added {len(items) if isinstance(items, list) else 1} item(s). Total: {n}"
    elif action == "complete":
        if idx is None: return "[TODO] Need index"
        with TODO_LOCK:
            if idx < 1 or idx > len(TODO_LIST): return f"[TODO] Invalid index {idx}"
            TODO_LIST[idx-1]["done"] = True
            text = TODO_LIST[idx-1]['text']
        return f"[TODO] Completed: {text}"
    elif action == "list":
        with TODO_LOCK:
            if not TODO_LIST: return "[TODO] List is empty"
            lines = []
            for i, t in enumerate(TODO_LIST):
                mark = "✅" if t["done"] else "⬜"
                lines.append(f"  {i+1}. {mark} {t['text']}")
        return "[TODO]\n" + "\n".join(lines)
    return f"[TODO] Unknown action: {action}"

def _tool_lsp(args):
    try:
        from lsp import LSPClient
    except ImportError:
        import lsp
        LSPClient = lsp.LSPClient
    op = args.get("operation", "")
    path = args.get("path", "")
    line = int(args.get("line", 0))
    char = int(args.get("character", 0))
    if not hasattr(execute_tool, '_lsp_client'):
        execute_tool._lsp_client = LSPClient(WORK_DIR)
    client = execute_tool._lsp_client
    if op == "definition":
        return client.goto_definition(path, line, char)
    elif op == "references":
        return client.find_references(path, line, char)
    elif op == "hover":
        return client.hover(path, line, char)
    elif op == "symbols":
        return client.document_symbols(path)
    elif op == "rename":
        new_name = args.get("new_name", "")
        if not new_name: return "Missing new_name"
        return client.rename(path, line, char, new_name)
    elif op == "completion":
        items = client.completion(path, line, char, args.get("text"))
        if not items:
            from lsp import token_completions
            items = token_completions(path, args.get("text", ""), line, char)
        if not items: return "No completions"
        return "\n".join(f"{it['label']}  ({it['detail'] or 'kind ' + str(it['kind'])})" for it in items[:30])
    return f"Unknown LSP operation: {op}"

def _tool_testgen(args):
    p = Path(args["path"]) if os.path.isabs(args["path"]) else WORK_DIR / args["path"]
    if not p.exists(): return f"File not found: {args['path']}"
    code = p.read_text("utf-8", errors="ignore")
    ext = p.suffix
    test_path = p.with_name("test_" + p.name)
    if ext == ".py":
        funcs = re.findall(r"def\s+(test)?(?!test_)\w+\s*\(", code) or re.findall(r"def\s+(\w+)\s*\(", code)
        funcs = [f for f in re.findall(r"def\s+(\w+)\s*\(", code) if not f.startswith("test_")]
        imports = ""
        for m in re.finditer(r"^(from\s+\S+\s+import\s+.*|import\s+.*)$", code, re.M):
            imports += m.group(1) + "\n"
        mod = p.stem
        body = f"import unittest\n{imports}\nfrom {mod} import " + ", ".join(funcs[:20]) + "\n\n\n"
        body += f"class Test{p.stem.title()}(unittest.TestCase):\n"
        for f in funcs[:20]:
            body += f"    def test_{f}(self):\n        self.assertIsNotNone({f}())\n\n\n"
        body += "if __name__ == '__main__':\n    unittest.main()\n"
    elif ext in (".js", ".ts"):
        funcs = re.findall(r"(?:export\s+)?(?:function|const)\s+(\w+)", code)
        body = "// Auto-generated tests\n"
        body += f"import {{ {', '.join(funcs[:20])} }} from './{p.stem}';\n\n"
        for f in funcs[:20]:
            body += f"test('{f}', () => {{\n  expect({f}).toBeDefined();\n}});\n"
    else:
        return f"testgen not supported for {ext}"
    test_path.write_text(body, "utf-8")
    return f"Generated: {test_path.name} ({len(body)} bytes, {len(funcs)} functions)"

def _tool_db_query(args):
    import sqlite3
    conn = sqlite3.connect(":memory:")
    query = args["query"]
    try:
        cur = conn.execute(query)
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchall()[:50]
        out = " | ".join(cols) + "\n" + "-" * 60 + "\n"
        out += "\n".join(" | ".join(str(c) for c in r) for r in rows)
        out += f"\n({len(rows)} rows)" if rows else "Empty result"
        return out
    except Exception as e:
        return f"db_query error: {e}"
    finally:
        conn.close()

def _tool_deps(args):
    # Dependency analysis: requirements.txt / package.json / go.mod / pyproject.toml
    out = []
    for pattern in ("requirements*.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Pipfile"):
        for f in sorted(Path(WORK_DIR).glob(pattern)):
            rel = str(f.relative_to(WORK_DIR))
            try:
                content = f.read_text("utf-8", errors="ignore")
            except Exception:
                continue
            out.append(f"### {rel}")
            if f.name == "requirements.txt":
                pkgs = [l.strip() for l in content.splitlines() if l.strip() and not l.startswith(("#", "-"))]
                if pkgs:
                    out.append("pip packages:")
                    for p in pkgs: out.append(f"  {p}")
                    out.append("Install: pip install " + " ".join(re.split(r'[<>=!~\[; ]+', p)[0] for p in pkgs))
            elif f.name == "pyproject.toml":
                deps = re.findall(r'^([\w\-]+)\s*=\s*["\^~>=<0-9.\[]+', content, re.M)
                if deps: out.append("pyproject deps: " + ", ".join(deps))
            elif f.name == "package.json":
                try:
                    j = json.loads(content)
                    deps = list(j.get("dependencies", {}).keys()) + list(j.get("devDependencies", {}).keys())
                    if deps:
                        out.append("npm deps:")
                        for d in deps: out.append(f"  npm install {d}")
                except Exception:
                    out.append("package.json: invalid JSON")
            elif f.name == "go.mod":
                deps = re.findall(r'^\s*([\w\.\-]+/\S+)\s+v\S+', content, re.M)
                if deps:
                    out.append("go deps:")
                    for d in deps: out.append(f"  go get {d}")
            elif f.name == "Cargo.toml":
                deps = re.findall(r'^([\w\-]+)\s*=\s*\{?\s*version', content, re.M)
                if deps: out.append("cargo deps: " + ", ".join(deps))
            elif f.name == "Pipfile":
                deps = re.findall(r'^([\w\-]+)\s*=\s*"', content, re.M)
                if deps: out.append("pipenv deps: " + ", ".join(deps))
            out.append("")
    if not out: return "No dependency files found (requirements.txt, package.json, go.mod, Cargo.toml, Pipfile)"
    return "\n".join(out).rstrip()

def _tool_mcp(args):
    try:
        from mcp_client import mcp_call, mcp_tools_list
    except ImportError:
        import mcp_client
        mcp_call, mcp_tools_list = mcp_client.mcp_call, mcp_client.mcp_tools_list
    server = args.get("server", "")
    if server == "_list":
        pairs = mcp_tools_list()
        if not pairs:
            return "No external MCP tools available (check mcp_servers.json)"
        return "\n".join(f"  {s}.{t}" for s, t in pairs)
    return mcp_call(server, args.get("call", ""), args.get("args", {}))

# ─── execute tool ─────────────────────────────────────────
def execute_tool(name, args):
    try:
        result = _execute_tool_inner(name, args)
        _audit(name, args, result)
        _stats_record(name, result)
        return result
    except Exception as e:
        _stats_record(name, f"Error: {e}")
        return f"Error: {e}"

_TOOL_DISPATCH = {
    "read": _tool_read,
    "web": _tool_web,
    "write": _tool_write,
    "edit": _tool_edit,
    "bash": _tool_bash,
    "glob": _tool_glob,
    "grep": _tool_grep,
    "list": _tool_list,
    "diff": _tool_diff,
    "commit": _tool_commit,
    "undo": _tool_undo,
    "verify": _tool_verify,
    "search": _tool_search,
    "snapshot": _tool_snapshot,
    "restore": _tool_restore,
    "websearch": _tool_websearch,
    "question": _tool_question,
    "skill": _tool_skill,
    "patch": _tool_patch,
    "task": _tool_task,
    "todo": _tool_todo,
    "lsp": _tool_lsp,
    "testgen": _tool_testgen,
    "db_query": _tool_db_query,
    "deps": _tool_deps,
    "mcp": _tool_mcp,
    "rename_symbol": _ast_rename_symbol,
    "extract_function": _ast_extract_function,
    "inline_variable": _ast_inline_variable,
}

def _execute_tool_inner(name, args):
    try:
        handler = _TOOL_DISPATCH.get(name)
        if handler is not None:
            return handler(args)
        result = call_plugin(name, args)
        if result is not None: return result
        return f"Unknown tool: {name}. Available tools: {', '.join(sorted(TOOL_SCHEMAS))}"
    except Exception as e:
        return f"Error: {e}"

_sync_register(sys.modules[__name__])
