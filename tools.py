"""Tool definitions and core agent logic — extracted from agent.py."""

import json, os, subprocess, glob, re, shutil, hashlib, textwrap, urllib.parse, time, logging, importlib.util, threading
from pathlib import Path
from datetime import datetime
import requests
from duckduckgo_search import DDGS

log = logging.getLogger('tools')

# ─── config (set by agent.py) ───────────────────────────
OLLAMA_URL = "http://localhost:11434"
MODEL = "qwen2.5-coder:7b"
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

# Thread safety (uvicorn is multi-threaded)
LLM_CACHE_LOCK = threading.Lock()
TODO_LOCK = threading.Lock()
GLOBAL_LOCK = threading.RLock()

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
    if not path or not isinstance(path, str):
        return "Error: path must be a non-empty string"
    if path.startswith(("/path/to", "/tmp", "/var", "/usr", "/home",
                        "/etc", "/bin", "/dev", "C:\\Windows", "C:\\Program")):
        return (f"Error: path '{path}' looks invented. Use RELATIVE paths or paths "
                f"inside the workspace (use list/glob to see files). "
                f"Do NOT give tutorials — retry with a correct path.")
    p = resolve(path).resolve()
    wk = WORK_DIR.resolve()
    if wk not in p.parents and p != wk:
        return (f"Error: path '{path}' is outside workspace '{WORK_DIR}'. "
                f"Use RELATIVE paths inside the workspace (use list/glob to see files). "
                f"Do NOT give tutorials — retry with a correct path.")
    return None

def _similar_files(path, limit=5):
    """Suggest nearby files when a path was not found — helps the model fix paths."""
    try:
        name = Path(path).name.lower()
        candidates = []
        exts = (".py", ".js", ".ts", ".json", ".md", ".html", ".css", ".txt", ".yaml", ".yml")
        for p in list(WORK_DIR.rglob("*"))[:4000]:
            if not p.is_file() or not p.suffix.lower() in exts:
                continue
            if any(x in p.parts for x in (".git", "__pycache__", ".agent_sessions",
                                          ".rag_cache", ".agent_backups", ".agent_memory", "node_modules")):
                continue
            fn = p.name.lower()
            if fn == name or fn.startswith(name[:6]) or name.startswith(fn[:6]):
                try:
                    candidates.append(str(p.relative_to(WORK_DIR)))
                except Exception:
                    pass
        if candidates:
            return f". Similar files in workspace: {', '.join(sorted(set(candidates))[:limit])}"
    except Exception:
        pass
    return ""

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
    "testgen": {"required": ["path"]},
    "db_query": {"required": ["query"]},
    "deps": {},
    "mcp": {"required": ["server", "call"]},
}

def validate_tool(tc):
    name = tc.get("tool", "")
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        return f"Unknown tool '{name}'. Available tools: {', '.join(sorted(TOOL_SCHEMAS))}"
    missing = [k for k in schema.get("required", []) if k not in tc]
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
7. NEVER invent tools and NEVER explain how to create a tool. All tools already exist and are listed below.
8. If a tool returns an error (file not found, bad args) — fix the arguments and retry the tool (or use glob to locate the file). NEVER give tutorials, multi-step advice, or checklists. Report the final result only.
9. If no tool is needed to answer — reply with plain text, no tool block.
10. Answer in the user's language (same language as the last user message).
11. Simple questions ("who are you", "what can you do", greetings, thanks, small talk) — answer DIRECTLY with ONE short sentence, NEVER call any tool, NEVER use code blocks. Never call `skill` with an invented name; if a tool result says "not found" — do NOT call that tool again. Never copy tool results or history into your text reply.
12. NEVER write the markers [PLAN], [CONFIRM], [tool:...] or "Reply 'yes'" inside your text — those are system markers, you must not produce them.
13. Call `plan` ONLY for real multi-step coding tasks. Never call plan for questions or chat.
14. After every write/edit: run a check with the `bash` TOOL (e.g. `python -m py_compile <file>` or run the tests) and report the result. NEVER describe a bash command inside your text — if you want to run something, you MUST emit a ```tool bash block. Never echo empty code blocks; reply with the actual result.
15. ALWAYS read a file with the `read` tool BEFORE calling `edit` or `write` on it (except brand-new files). The `old` text of an edit must be copied EXACTLY from the read output.
16. NEVER invent file paths. Only use paths returned by `list`/`glob`/`grep` or confirmed by the user. Paths are RELATIVE to the workspace.

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

# ─── plugins system ───────────────────────────────────────
PLUGINS = {}
PLUGIN_DIR = WORK_DIR / ".agent_plugins"

def load_plugins():
    global PLUGINS
    PLUGINS = {}
    if not PLUGIN_DIR.exists(): return
    for f in sorted(PLUGIN_DIR.glob("*.py")):
        try:
            mod_name = f.stem
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "register"):
                    tools, defs = mod.register()
                    for name in tools:
                        PLUGINS[name] = {"module": mod, "tools": tools, "defs": defs}
                        if name in tools:
                            TOOL_SCHEMAS[name] = defs.get("schema", {"required": []})
                    log.info("Plugin loaded: %s (%d tools)", mod_name, len(tools))
        except Exception as e:
            log.warning("Plugin load failed %s: %s", f.name, e)

def call_plugin(name, args):
    plugin = PLUGINS.get(name)
    if not plugin: return None
    func = plugin["tools"].get(name)
    if func: return func(args)
    return None

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

# ─── call Ollama with fallback + TTL cache ────────────────
LLM_CACHE = {}
LLM_CACHE_TTL = int(os.environ.get("LLM_CACHE_TTL", "60"))

def _cache_key(messages, model):
    body = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.md5((model + body).encode()).hexdigest()[:24]

def stream_ollama(messages, model=None, on_chunk=None):
    """Stream a chat completion from Ollama. on_chunk(text_fragment) is called
    for every fragment as it arrives; returns the full text (think tags stripped)."""
    m = model or MODEL
    num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
    parts = []
    last_err = None
    for attempt in range(2):
        try:
            with requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": m, "messages": [msg for msg in messages if msg.get("content")],
                "stream": True, "keep_alive": -1,
                "options": {"temperature": 0.2, "num_predict": 2048, "num_ctx": num_ctx}
            }, stream=True, timeout=180) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    frag = (data.get("message") or {}).get("content") or ""
                    if frag:
                        parts.append(frag)
                        if on_chunk:
                            try:
                                on_chunk(frag)
                            except Exception:
                                pass
                    if data.get("done"):
                        break
            text = re.sub(r'<think>.*?</think>', '', "".join(parts), flags=re.DOTALL)
            if not text:
                text = "No response from model"
            return text
        except Exception as e:
            last_err = e
            log.warning("stream_ollama attempt %d/2 failed: %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(1)
    raise RuntimeError(f"stream_ollama failed: {last_err}")

def call_ollama(messages, model=None):
    global LLM_CACHE
    m = model or MODEL
    if LLM_CACHE_TTL > 0:
        key = _cache_key(messages, m)
        with LLM_CACHE_LOCK:
            hit = LLM_CACHE.get(key)
            if hit and time.time() - hit[0] < LLM_CACHE_TTL:
                log.info("LLM cache hit (TTL=%ds)", LLM_CACHE_TTL)
                return hit[1], hit[2]
    max_retries = 3
    num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": m, "messages": [msg for msg in messages if msg.get("content")],
                "stream": False, "keep_alive": -1,
                "options": {"temperature": 0.2, "num_predict": 2048, "num_ctx": num_ctx}
            }, timeout=180)
            r.raise_for_status()
            data = r.json()
            msg = data.get("message", {}).get("content", "")
            tokens_used = data.get("eval_count", 0)
            msg = re.sub(r'<think>.*?</think>', '', msg, flags=re.DOTALL)
            if not msg: msg = "No response from model"
            if LLM_CACHE_TTL > 0:
                with LLM_CACHE_LOCK:
                    LLM_CACHE[key] = (time.time(), msg, tokens_used)
                    if len(LLM_CACHE) > 100:
                        now = time.time()
                        LLM_CACHE = {k: v for k, v in LLM_CACHE.items() if now - v[0] < LLM_CACHE_TTL}
            return msg, tokens_used
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
    "rm -rf /", "rm -rf --no-preserve-root", "rm -rf ~", "rm -rf /tmp/",
    "rm -rf c:\\", "rm -rf .", "rm -rf *", "rm -rf",
    "mkfs", "format ", "dd if=", "dd of=", ":(){ :|:& };:", "fork bomb",
    "> /dev/sda", "> /dev/sdb", "| sh", "| bash", "curl ", "wget ", "chmod 777",
    "sudo ", "su ", "passwd", "del /f /s", "rmdir /s", "rd /s", "del /q /s",
    "shutdown", "taskkill /f", "net user",
]
# Whitelist of allowed bare commands (first token). Everything else is rejected
# unless it is a path to an existing file inside WORK_DIR (e.g. .\build.py).
BASH_ALLOWED = {
    "python", "python3", "py", "pythonw", "pip", "pip3", "pipenv", "poetry", "uv", "uvx",
    "npm", "npx", "node", "yarn", "pnpm",
    "git", "gh",
    "cd", "pwd", "echo", "type", "cat", "dir", "ls", "where", "findstr", "find", "cls", "clear",
    "mkdir", "rmdir", "del", "copy", "xcopy", "move", "ren", "cp", "mv", "rm",
    "date", "time", "tasklist", "tree", "fc", "comp",
}
# Destructive commands whose args must not contain ".." (path escape / obfuscation)
BASH_NO_DOTDOT = {"rm", "del", "rd", "rmdir", "move", "mv", "copy", "xcopy", "cp", "ren"}

def _segment_token(segment):
    seg = segment.strip().strip('"').strip("'")
    if not seg:
        return None, ""
    tok = seg.split()[0].strip('"').strip("'")
    base = tok.split("\\")[-1].replace(".exe", "").replace(".bat", "").replace(".cmd", "")
    return tok, base.lower()

def check_bash(cmd):
    """Block dangerous shell commands. Whitelist for bare commands + blacklist
    patterns + recursive check of nested interpreters (bash -c, cmd /c,
    powershell -c, python -c, node -e)."""
    norm = " ".join(cmd.lower().split())
    stripped = norm.replace('"', "").replace("'", "").replace("`", "").replace("\\", "")
    checks = [norm, stripped]
    # recursive interpreter bodies: bash/sh/cmd/powershell AND python/node inline scripts
    for m in re.finditer(r"(?:bash|sh|cmd|powershell|pwsh)\s+(?:-c|-command)\s+[\"']?([^\"']+)", norm):
        checks.append(" ".join(m.group(1).split()))
    for m in re.finditer(r"(?:python|py|node)\s+(?:-c|-e|-m)\s+[\"']?([^\"']+)", norm):
        checks.append(" ".join(m.group(1).split()))
    for c in checks:
        for dangerous in BASH_BLACKLIST:
            if dangerous in c:
                return f"Blocked: command matching blacklist pattern '{dangerous}' is not allowed"
    # whitelist: every pipeline/; /&& segment must start with an allowed command
    for segment in re.split(r"[\|;&]|(?:^| )(?:and|or) ", norm):
        tok, base = _segment_token(segment)
        if not tok:
            continue
        if base in BASH_ALLOWED:
            continue
        # allow project-local scripts: .\x.py, ./x.py, or relative paths that exist in WORK_DIR
        p = Path(tok.replace("/", os.sep))
        if not os.path.isabs(str(p)) and not tok.startswith(".."):
            pp = (WORK_DIR / p).resolve()
            if WORK_DIR.resolve() in pp.parents and pp.exists():
                continue
        return f"Blocked: '{tok}' is not in the command whitelist"
    # destructive commands must not reference parent dirs (rm -rf /tmp/.. bypass)
    for seg in re.split(r"[\|;&]", norm):
        tok, base = _segment_token(seg)
        if base in BASH_NO_DOTDOT and re.search(r"\.\.[\\/]| \.\.$", seg):
            return f"Blocked: '{base}' with '..' path escape is not allowed"
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

# ─── execute tool ─────────────────────────────────────────
AUDIT_LOG = None

def _audit(name, args, result):
    """Log every tool call with timestamp (action audit)."""
    global AUDIT_LOG
    if AUDIT_LOG is None:
        AUDIT_LOG = WORK_DIR / ".agent_audit.log"
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        arg_preview = json.dumps(args, ensure_ascii=False)[:200]
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {name} {arg_preview}\n")
    except: pass

def execute_tool(name, args):
    try:
        result = _execute_tool_inner(name, args)
        _audit(name, args, result)
        return result
    except Exception as e:
        return f"Error: {e}"

def _execute_tool_inner(name, args):
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
            if not pp.exists():
                return f"Error: {p} not found" + (_similar_files(p) or ". Use the glob tool to find files. Do NOT give tutorials — retry with a correct path.")
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
            if not p.exists():
                return f"Error: {p} not found" + (_similar_files(args["path"]) or ". Use the glob tool to find files. Do NOT give tutorials — retry with a correct path.")
            old = args.get("old", ""); new = args.get("new", "")
            content = p.read_text("utf-8")
            if old not in content:
                lines = content.split("\n")
                snippet = "\n".join(lines[:20]) if len(lines) <= 20 else "\n".join(lines[:10]) + "\n...\n" + "\n".join(lines[-5:])
                return f"Error: text not found in {args['path']}.\nCurrent file content (first lines):\n```\n{snippet[:800]}\n```\nUse the EXACT text from the file."
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
            import rag as _rag
            return _rag.rag_search(args.get("query", ""), args.get("top_k", 5))
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
            if result is None:
                return "Error: patch does not match file content (hunk context mismatch)"
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
        elif name == "lsp":
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
        elif name == "testgen":
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
        elif name == "db_query":
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
        elif name == "deps":
            # Dependency analysis: requirements.txt / package.json / go.mod / pyproject.toml
            out = []
            for pattern in ("requirements*.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "Pipfile"):
                for f in sorted(Path(WORK_DIR).glob(pattern)):
                    rel = str(f.relative_to(WORK_DIR))
                    try:
                        content = f.read_text("utf-8", errors="ignore")
                    except: continue
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
                        except: out.append("package.json: invalid JSON")
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
        elif name == "mcp":
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
        else:
            result = call_plugin(name, args)
            if result is not None: return result
            return f"Unknown tool: {name}. Available tools: {', '.join(sorted(TOOL_SCHEMAS))}"
    except Exception as e:
        return f"Error: {e}"
