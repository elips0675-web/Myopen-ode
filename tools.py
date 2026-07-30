"""Tool definitions and core agent logic — extracted from agent.py."""

import json, os, subprocess, glob, re, shutil, hashlib, textwrap, urllib.parse, time, logging
from pathlib import Path
from datetime import datetime
import requests
from duckduckgo_search import DDGS

log = logging.getLogger('tools')

# ─── config (set by agent.py) ───────────────────────────
OLLAMA_URL = "http://localhost:11434"
MODEL = "deepseek-r1:7b"
PLANNER_MODEL = "deepseek-r1:1.5b"
WORK_DIR = Path(".")
EMBED_MODEL = "nomic-embed-text"
NO_CONFIRM = False
MAX_TOKENS = 0
OPENAI_KEY = ""
ANTHROPIC_KEY = ""
FALLBACK_MODEL = ""
BASH_TIMEOUT = 60
# DeepSeek-V4-Flash provider URLs (и т.д. бесплатные)
FLASH_PROVIDERS = {
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
}

def init_config(**kw):
    global OLLAMA_URL, MODEL, PLANNER_MODEL, WORK_DIR, EMBED_MODEL, NO_CONFIRM, MAX_TOKENS, OPENAI_KEY, ANTHROPIC_KEY, FALLBACK_MODEL
    for k, v in kw.items():
        if v is not None:
            globals()[k] = v
    # Apply AGENT_TIMEOUT to bash tool if set
    bash_timeout = os.environ.get("AGENT_TIMEOUT", "")
    if bash_timeout:
        try: globals()["BASH_TIMEOUT"] = int(float(bash_timeout))
        except: pass

# ─── path resolver with security ──────────────────────────
def resolve(path):
    p = Path(path)
    if p.is_absolute(): return p
    return WORK_DIR / path

def ensure_safe_path(path):
    """Resolve path and verify it stays within WORK_DIR to prevent directory traversal."""
    p = resolve(path).resolve()
    wk = WORK_DIR.resolve()
    if wk not in p.parents and p != wk:
        return f"Error: path '{path}' is outside workspace '{WORK_DIR}'"
    return None

# ─── file versioning ──────────────────────────────────────
BACKUP_DIR = None
MAX_BACKUPS = 50

def init_backup():
    global BACKUP_DIR
    BACKUP_DIR = WORK_DIR / ".agent_backups"
    BACKUP_DIR.mkdir(exist_ok=True)

def backup(path):
    if BACKUP_DIR is None: return
    p = Path(path) if os.path.isabs(path) else WORK_DIR / path
    if p.exists():
        key = str(p).replace("\\", "_").replace("/", "_").replace(":", "")
        b = BACKUP_DIR / key / datetime.now().strftime("%H%M%S_%f")
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, b)
        versions = sorted(b.parent.iterdir())
        for v in versions[:-MAX_BACKUPS]:
            v.unlink()

def undo(path):
    if BACKUP_DIR is None: return f"No backup dir"
    key = str(Path(path) if os.path.isabs(path) else WORK_DIR / path)
    key = key.replace("\\", "_").replace("/", "_").replace(":", "")
    bd = BACKUP_DIR / key
    if not bd.exists(): return f"No backup for {path}"
    versions = sorted(bd.iterdir())
    if not versions: return f"No backup for {path}"
    dst = Path(path) if os.path.isabs(path) else WORK_DIR / path
    shutil.copy2(versions[-1], dst)
    versions[-1].unlink()
    return f"Undone: {path} restored"

# ─── verify ───────────────────────────────────────────────
VERIFY_COMMANDS = {
    ".js,.jsx,.ts,.tsx": "npx tsc --noEmit 2>&1 || true",
    ".py": "python -m py_compile {file} 2>&1 || true",
    ".json": "python -m json.tool {file} > nul 2>&1 && echo OK || echo Invalid JSON",
}

def verify_file(path):
    ext = "".join(Path(path).suffixes)
    for pattern, cmd in VERIFY_COMMANDS.items():
        if any(ext.endswith(e) for e in pattern.split(",")):
            p = Path(path) if os.path.isabs(path) else WORK_DIR / path
            fcmd = cmd.replace("{file}", f'"{p}"')
            r = subprocess.run(fcmd, shell=True, capture_output=True, text=True, timeout=15)
            return r.stdout.strip()[:1000] or r.stderr.strip()[:1000]
    return ""

# ─── git helpers ──────────────────────────────────────────
def git(*args):
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(WORK_DIR), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip()
    except: return "(git not available)"

# ─── tool schemas ─────────────────────────────────────────
TOOL_SCHEMAS = {
    "read":   {"required": ["path"]},
    "write":  {"required": ["path", "content"]},
    "edit":   {"required": ["path", "old", "new"]},
    "bash":   {"required": ["cmd"]},
    "glob":   {"required": ["pattern"]},
    "grep":   {"required": ["pattern"]},
    "list":   {},
    "web":    {"required": ["url"]},
    "diff":   {},
    "commit": {},
    "undo":   {"required": ["path"]},
    "verify": {"required": ["path"]},
    "plan":   {"required": ["steps"]},
    "search": {"required": ["query"]},
    "websearch": {"required": ["query"]},
    "question": {"required": ["text", "options"]},
    "skill": {"required": ["name"]},
    "patch": {"required": ["path", "diff"]},
    "task": {"required": ["agent", "prompt"]},
    "todo": {"required": ["action"]},
    "lsp": {"required": ["operation", "path"]},
}

def validate_tool(tc):
    name = tc.get("tool", "")
    schema = TOOL_SCHEMAS.get(name)
    if not schema: return f"Unknown tool '{name}'"
    missing = [k for k in schema.get("required", []) if k not in tc]
    if missing: return f"Missing required fields: {', '.join(missing)} in {name}"
    if "path" in tc and not isinstance(tc["path"], str): return "path must be string"
    if "content" in tc and not isinstance(tc["content"], str): return "content must be string"
    if tc.get("tool") == "plan" and "steps" in tc:
        if isinstance(tc["steps"], str):
            tc["steps"] = [s.strip() for s in re.split(r'[.,;\n]+', tc["steps"]) if s.strip()]
        elif not isinstance(tc["steps"], list):
            return "plan.steps must be an array of strings"
    if tc.get("tool") == "question" and "options" in tc:
        if isinstance(tc["options"], str):
            tc["options"] = [o.strip() for o in tc["options"].split(",") if o.strip()]
    if tc.get("tool") == "patch" and "diff" in tc:
        err = _validate_patch(tc["diff"])
        if err: return err
    return ""

# ─── system prompt ────────────────────────────────────────
SYSTEM_PROMPT = "CRITICAL: You are a coding AGENT with tools on Windows.\n\nWORKSPACE: " + str(WORK_DIR) + """ — project root.

RULES:
1. Complex tasks: call plan FIRST with steps, user confirms, then execute.
2. Simple tasks: call tool directly. Ask before write/edit/bash/commit/undo.
3. Your response MUST start with a ```tool block. NEVER describe tools.
4. NEVER write code blocks. ONLY ```tool blocks.
5. Every tool call MUST include ALL required fields. Missing fields will be rejected.
6. When user confirms with "yes" or "да" — you MUST repeat the exact same ```tool block. No explanations.

TOOLS (required fields in bold):
```tool
{"tool": "plan", "steps": ["step1", "step2"]}
```
```tool
{"tool": "read", "path": "file.py"}
```
```tool
{"tool": "list", "path": "dir"}
```
```tool
{"tool": "bash", "cmd": "echo hi"}
```
```tool
{"tool": "web", "url": "https://..."}
```
```tool
{"tool": "write", "path": "file", "content": "text"}
```
```tool
{"tool": "edit", "path": "file", "old": "...", "new": "..."}
```
```tool
{"tool": "glob", "pattern": "**/*.py"}
```
```tool
{"tool": "grep", "pattern": "TODO", "include": "*.py"}
```
```tool
{"tool": "diff"}
```
```tool
{"tool": "commit", "message": "desc"}
```
```tool
{"tool": "undo", "path": "file"}
```
```tool
{"tool": "verify", "path": "file"}
```
```tool
{"tool": "search", "query": "function that handles auth"}
```
```tool
{"tool": "websearch", "query": "python async await example", "max_results": 5}
```
```tool
{"tool": "question", "text": "Which approach?", "options": ["Option A", "Option B"]}
```
```tool
{"tool": "skill", "name": "testing"}
```
```tool
{"tool": "patch", "path": "file.py", "diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new"}
```
```tool
{"tool": "task", "agent": "explore", "prompt": "Find all async functions in src/"}
```
```tool
{"tool": "todo", "action": "add", "items": ["task1", "task2"]}
```
```tool
{"tool": "todo", "action": "complete", "index": 1}
```
```tool
{"tool": "todo", "action": "list"}
```
```tool
{"tool": "lsp", "operation": "definition", "path": "main.py", "line": 10, "character": 5}
```
```tool
{"tool": "lsp", "operation": "references", "path": "main.py", "line": 10, "character": 5}
```
```tool
{"tool": "lsp", "operation": "hover", "path": "main.py", "line": 10, "character": 5}
```
```tool
{"tool": "lsp", "operation": "symbols", "path": "main.py"}
```

Paths: forward slashes. C:/Users/... or relative to workspace.
Search: semantic code search via RAG.
WebSearch: internet search via DuckDuckGo.
Question: ask user with multiple choice options.
Skill: load SKILL.md instructions from .agent_skills/ directory.
Patch: apply unified diff to a file.
Multi-agent: planning uses a smaller model; execution uses the main model.
Task: delegate to subagent. Agents: explore (read-only research), scout (web/external research), general (complex multi-step).
Todo: manage task list within session — add, complete, list items.
LSP: code intelligence — definition, references, hover, symbols per file."""

# ─── in-memory todo store ─────────────────────────────────
TODO_LIST = []

# ─── subagent prompts ────────────────────────────────────
EXPLORE_PROMPT = "You are EXPLORE agent — read-only codebase researcher.\n\nWORKSPACE: " + str(WORK_DIR) + """
You can ONLY use: read, glob, grep, list, search (RAG).
NEVER write, edit, bash, commit, or any destructive tools.
Your job is to find information, explore code structure, and report findings concisely."""

SCOUT_PROMPT = "You are SCOUT agent — external research specialist.\n\nWORKSPACE: " + str(WORK_DIR) + """
You can ONLY use: web, websearch, read (URLs only).
Your job is to research external dependencies, documentation, and APIs.
Report findings with sources."""

GENERAL_PROMPT = "You are GENERAL agent — full-access subagent for complex tasks.\n\nWORKSPACE: " + str(WORK_DIR) + """
You have access to ALL tools: read, write, edit, bash, glob, grep, list, web, websearch, diff, commit, undo, verify, plan, search, question, skill, patch.
Follow the same rules as the main agent: confirm before destructive operations, verify after write/edit, prefer edit over write."""

SUBAGENT_PROMPTS = {
    "explore": EXPLORE_PROMPT,
    "scout": SCOUT_PROMPT,
    "general": GENERAL_PROMPT,
}

# ─── call Ollama with fallback ────────────────────────────
def call_ollama(messages, model=None):
    m = model or MODEL
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": m, "messages": [msg for msg in messages if msg.get("content")],
                "stream": False, "keep_alive": -1,
                "options": {"temperature": 0.2, "num_predict": 4096, "num_ctx": 32768}
            }, timeout=120)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message", {}).get("content", "")
            tokens_used = data.get("eval_count", 0)
            msg = re.sub(r'<think>.*?</think>', '', msg, flags=re.DOTALL)
            return msg if msg else "No response from model", tokens_used
        except Exception as e:
            log.warning("Ollama attempt %d/%d failed: %s", attempt+1, max_retries, e)
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                log.info("Retrying in %ds...", wait)
                time.sleep(wait)
            else:
                log.warning("All Ollama retries exhausted. Trying fallback...")
                return call_fallback(messages, m), 0

def call_fallback(messages, model_name):
    fallback = FALLBACK_MODEL or ""
    flash_provider = os.environ.get("FLASH_PROVIDER", "")
    flash_key = os.environ.get("FLASH_API_KEY", OPENAI_KEY)
    if not fallback and not flash_provider:
        return "[Error: Ollama unavailable, no fallback configured]"
    try:
        # DeepSeek-V4-Flash via provider
        if flash_provider and flash_key:
            base = FLASH_PROVIDERS.get(flash_provider, flash_provider)
            h = {"Authorization": f"Bearer {flash_key}", "Content-Type": "application/json"}
            flash_model = os.environ.get("FLASH_MODEL", "deepseek-v4-flash")
            body = {"model": flash_model, "messages": [m for m in messages if m.get("content")], "temperature": 0.2, "max_tokens": 8192, "max_context": 1048576}
            try:
                r = requests.post(f"{base}/chat/completions", json=body, headers=h, timeout=180)
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"]
            except Exception as e:
                log.warning("Flash provider failed: %s", e)
        if OPENAI_KEY and ("gpt" in fallback or "o1" in fallback or "o3" in fallback or "/" not in fallback):
            h = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
            body = {"model": fallback, "messages": [m for m in messages if m.get("content")], "temperature": 0.2, "max_tokens": 4096}
            r = requests.post("https://api.openai.com/v1/chat/completions", json=body, headers=h, timeout=120)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        if ANTHROPIC_KEY and "claude" in fallback:
            h = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
            body = {"model": fallback, "max_tokens": 4096, "messages": [{"role": m["role"], "content": m["content"]} for m in messages if m.get("content") and m["role"] != "system"]}
            r = requests.post("https://api.anthropic.com/v1/messages", json=body, headers=h, timeout=120)
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        return f"[Error: No matching API for fallback model '{fallback}']"
    except Exception as e2:
        return f"[Error: Fallback API: {e2}]"

# ─── extract pending tool for auto-execute ────────────────
def extract_pending_tool(msgs):
    tp = re.compile(r'```(?:tool|json)\n(.*?)\n```', re.DOTALL)
    bare = re.compile(r'\{\s*"tool"\s*:\s*"[^"]+"\s*.*?\}', re.DOTALL)
    bad = ("write", "edit", "bash", "commit", "undo")
    for m in reversed(msgs):
        if m.get("role") != "assistant": continue
        c = m.get("content", "")
        for match in tp.finditer(c):
            raw = match.group(1).strip()
            try: j = json.loads(raw)
            except:
                try: j = json.loads(raw.replace("'", '"'))
                except: continue
            n = j.get("tool", "")
            if n in bad:
                tc = dict(j); tc.pop("tool", None); return n, tc
        for match in bare.finditer(c):
            try:
                j = json.loads(match.group())
                n = j.get("tool", "")
                if n in bad:
                    tc = dict(j); tc.pop("tool", None); return n, tc
            except: pass
    return None, None

# ─── bash sandbox ─────────────────────────────────────────
BASH_BLACKLIST = [
    "rm -rf /", "rm -rf ~", "rm -rf .", "rm -rf *", "rm -rf --no-preserve-root",
    "mkfs.", "format ", "dd if=", "dd of=", ":(){ :|:& };:", "fork bomb",
    "> /dev/sda", "| sh", "| bash", "curl ", "wget ", "chmod 777",
    "sudo ", "su ", "passwd",
]
def check_bash(cmd):
    cmd_lower = cmd.lower()
    for dangerous in BASH_BLACKLIST:
        if dangerous in cmd_lower:
            return f"Blocked: command matching blacklist pattern '{dangerous}' is not allowed"
    return None

# ─── unified diff parser ──────────────────────────────────
def _apply_diff(content, diff_text):
    """Apply a unified diff to content and return the result."""
    import difflib
    lines = content.splitlines(keepends=True)
    old_lines = []
    new_lines = []
    in_hunk = False
    for line in diff_text.split("\n"):
        if line.startswith("--- "): continue
        if line.startswith("+++ "): continue
        if line.startswith("@@"):
            if in_hunk and new_lines:
                content = "".join(new_lines)
                lines = content.splitlines(keepends=True)
                new_lines = []
            in_hunk = True
            parts = line.split(" ")
            if len(parts) >= 2:
                try:
                    old_start = int(parts[1].split(",")[0].lstrip("-"))
                except: old_start = 1
            continue
        if in_hunk:
            if line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:] + "\n")
            elif line.startswith("-") and not line.startswith("---"):
                pass  # skip removed lines
            elif line.startswith(" "):
                new_lines.append(line[1:] + "\n")
            else:
                new_lines.append(line + "\n")
    if in_hunk and new_lines:
        content = "".join(new_lines)
    return content

def _validate_patch(diff_text):
    """Validate unified diff format."""
    if not any(line.startswith("@@") for line in diff_text.split("\n")):
        return "Invalid diff: no hunk headers (@@)"
    if "--- " not in diff_text or "+++ " not in diff_text:
        return "Invalid diff: missing file headers"
    return None

# ─── execute tool ─────────────────────────────────────────
def execute_tool(name, args):
    try:
        if name == "read":
            p = args["path"]
            if p.startswith(("http://", "https://")):
                try:
                    r = requests.get(p, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    return r.text[:5000]
                except Exception as e: return f"Error fetching URL: {e}"
            err = ensure_safe_path(p)
            if err: return err
            pp = resolve(p)
            if not pp.exists(): return f"Error: {p} not found"
            if pp.is_dir(): return f"'{p}' is a directory. Use list tool to see contents."
            return pp.read_text("utf-8")
        elif name == "web":
            url = args.get("url", "")
            try:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                return r.text[:5000]
            except Exception as e: return f"Error: {e}"
        elif name == "write":
            err = ensure_safe_path(args["path"])
            if err: return err
            p = resolve(args["path"])
            rel = str(p.relative_to(WORK_DIR)) if WORK_DIR in p.parents else str(p)
            backup(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], "utf-8")
            v = verify_file(str(p))
            msg = f"Written {len(args['content'])}b to {p}"
            if v: msg += f"\nVerify: {v[:500]}"
            return msg
        elif name == "edit":
            err = ensure_safe_path(args["path"])
            if err: return err
            p = resolve(args["path"])
            if not p.exists(): return f"Error: {p} not found"
            old = args.get("old", ""); new = args.get("new", "")
            content = p.read_text("utf-8")
            if old not in content: return f"Error: text not found in {args['path']}"
            rel = str(p.relative_to(WORK_DIR)) if WORK_DIR in p.parents else str(p)
            backup(rel)
            p.write_text(content.replace(old, new), "utf-8")
            v = verify_file(str(p))
            return f"Replaced in {p}" + (f"\nVerify: {v[:500]}" if v else "")
        elif name == "bash":
            cmd = args["cmd"]
            blocked = check_bash(cmd)
            if blocked: return blocked
            cwd = resolve(args.get("cwd", ".")) if args.get("cwd") else WORK_DIR
            bt = globals().get("BASH_TIMEOUT", 60)
            r = subprocess.run(cmd, shell=True, cwd=str(cwd) if cwd else str(WORK_DIR), capture_output=True, text=True, timeout=bt)
            return ((r.stdout or "")[-3000:] + ("\nSTDERR:\n" + (r.stderr or "")[-1000:] if r.stderr else ""))
        elif name == "glob":
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
            fs = list(glob.glob(str(base / pattern), recursive=True))[:60]
            return "\n".join(fs) if fs else "No matches"
        elif name == "grep":
            pat, inc = args["pattern"], args.get("include", "*")
            cwd = args.get("cwd", ".")
            err = ensure_safe_path(cwd)
            if err: return err
            cwd = str(resolve(cwd))
            r = subprocess.run(f'rg -n "{pat}" --glob "{inc}"', shell=True, cwd=cwd, capture_output=True, text=True, timeout=30)
            return "\n".join(r.stdout.split("\n")[:60]) or "No matches"
        elif name == "list":
            err = ensure_safe_path(args.get("path", "."))
            if err: return err
            p = resolve(args.get("path", "."))
            items = [f"{'[DIR]' if x.is_dir() else '     '} {x.name}" for x in sorted(p.iterdir())]
            return "\n".join(items) if items else "(empty)"
        elif name == "diff":
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
        elif name == "commit":
            git("add", "-A"); return git("commit", "-m", args.get("message", "update"))
        elif name == "undo":
            err = ensure_safe_path(args.get("path", ""))
            if err: return err
            return undo(args.get("path", ""))
        elif name == "verify":
            path = args.get("path", "")
            if path:
                err = ensure_safe_path(path)
                if err: return err
            return verify_file(path) if path else "No path specified"
        elif name == "search":
            from .rag import rag_search
            return rag_search(args.get("query", ""), args.get("top_k", 5))
        elif name == "websearch":
            query = args.get("query", "")
            max_results = int(args.get("max_results", 5))
            try:
                results = []
                with DDGS() as ddgs:
                    for i, r in enumerate(ddgs.text(query, max_results=max_results)):
                        results.append(f"[{i+1}] {r.get('title','')}\n    URL: {r.get('href','')}\n    {r.get('body','')[:300]}")
                return "\n\n".join(results) if results else "No results found"
            except Exception as e:
                return f"Web search error: {e}"
        elif name == "question":
            text = args.get("text", "")
            opts = args.get("options", [])
            opts_str = " / ".join([f"{i+1}. {o}" for i, o in enumerate(opts)])
            return f"[QUESTION] {text}\n{opts_str}"
        elif name == "skill":
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
        elif name == "patch":
            path = args.get("path", "")
            err = ensure_safe_path(path)
            if err: return err
            pp = resolve(path)
            if not pp.exists(): return f"Error: {path} not found"
            diff_text = args.get("diff", "")
            if not diff_text:
                return "Error: diff field is required"
            content = pp.read_text("utf-8")
            result = _apply_diff(content, diff_text)
            if result.startswith("Error"):
                return result
            backup(str(pp))
            pp.write_text(result, "utf-8")
            v = verify_file(str(pp))
            msg = f"Patch applied to {path} ({len(pp.read_text('utf-8'))}b)"
            if v: msg += f"\nVerify: {v[:500]}"
            return msg
        elif name == "task":
            agent_type = args.get("agent", "general")
            user_prompt = args.get("prompt", "")
            sub_prompt = SUBAGENT_PROMPTS.get(agent_type, GENERAL_PROMPT)
            msgs = [
                {"role": "system", "content": sub_prompt},
                {"role": "user", "content": user_prompt},
            ]
            result, _ = call_ollama(msgs, PLANNER_MODEL)
            return f"[SUBAGENT:{agent_type}]\n{result[:3000]}"
        elif name == "todo":
            action = args.get("action", "list")
            items = args.get("items", [])
            idx = args.get("index", None)
            if action == "add":
                for item in (items if isinstance(items, list) else [items]):
                    TODO_LIST.append({"text": item, "done": False})
                return f"[TODO] Added {len(items) if isinstance(items, list) else 1} item(s). Total: {len(TODO_LIST)}"
            elif action == "complete":
                if idx is None: return "[TODO] Need index"
                if idx < 1 or idx > len(TODO_LIST): return f"[TODO] Invalid index {idx}"
                TODO_LIST[idx-1]["done"] = True
                return f"[TODO] Completed: {TODO_LIST[idx-1]['text']}"
            elif action == "list":
                if not TODO_LIST: return "[TODO] List is empty"
                lines = []
                for i, t in enumerate(TODO_LIST):
                    mark = "✅" if t["done"] else "⬜"
                    lines.append(f"  {i+1}. {mark} {t['text']}")
                return "[TODO]\n" + "\n".join(lines)
            return f"[TODO] Unknown action: {action}"
        elif name == "lsp":
            from .lsp import LSPClient
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
            return f"Unknown LSP operation: {op}"
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"
