"""LLM calls: Ollama streaming/non-streaming, native tool calling, fallbacks."""
import json, os, re, sys, time, hashlib
import logging
import requests
from ._state import (MODEL, OLLAMA_URL, OPENAI_KEY, ANTHROPIC_KEY, FALLBACK_MODEL,
                     FLASH_PROVIDERS, TOOL_JSON_SCHEMA, LLM_CACHE, LLM_CACHE_TTL,
                     LLM_CACHE_LOCK, TOOL_SCHEMAS, NATIVE_TOOL_MODELS, _json_mode)
from ._state import _sync_register

log = logging.getLogger("tools")

def _cache_key(messages, model):
    body = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.md5((model + body).encode()).hexdigest()[:24]


_TASK_MODEL_MAP = {
    "bugfix": "qwen3:8b",
    "refactor": "qwen3:8b",
    "tests": "qwen3:8b",
    "chat": "qwen2.5-coder:3b",
}
_MODELS_CACHE = {"at": 0, "list": None}


def _installed_models():
    """Cached list of installed Ollama models (TTL 60s); empty on failure."""
    now = time.time()
    if _MODELS_CACHE["list"] is not None and now - _MODELS_CACHE["at"] < 60:
        return _MODELS_CACHE["list"]
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        lst = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        lst = []
    _MODELS_CACHE.update({"at": now, "list": lst})
    return lst


def pick_task_model(task_text, base_model, classify=None):
    """Stage 30: task-level model router (DS4 P2 #7). A zero-shot classifier
    (PLANNER_MODEL, one light call) picks the strongest model BEFORE the loop:
    bugfix/refactor/tests -> qwen3:8b, chat -> qwen2.5-coder:3b. Rules:
    explicit AI_MODEL always wins; the user-picked model is never overridden;
    short chats stay on the default model; if the target model is not
    installed, the default is kept. classify is injectable for tests."""
    import os as _os
    from ._state import PLANNER_MODEL
    if _os.environ.get("AI_MODEL"):
        return base_model
    t = (task_text or "").strip()
    if not t or len(t) < 20 or base_model == "qwen3:8b":
        return base_model
    if classify is None:
        classify = _classify_task
    try:
        cat = classify(t, PLANNER_MODEL) or ""
        target = _TASK_MODEL_MAP.get(cat.strip().lower())
        if not target or target == base_model:
            return base_model
        if target not in _installed_models():
            return base_model
        return target
    except Exception:
        return base_model


def _classify_task(task_text, planner_model, timeout=20):
    """One zero-shot call: answer with exactly one word from
    bugfix|refactor|tests|chat|other."""
    import requests as _r
    prompt = ("Classify the user request into exactly one word: "
              "bugfix, refactor, tests, chat, other.\n\nUser request: "
              + (task_text or "")[:400])
    try:
        resp = _r.post(f"{OLLAMA_URL}/api/chat", json={
            "model": planner_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "options": {"temperature": 0},
        }, timeout=timeout)
        text = (resp.json().get("message", {}).get("content") or "")[:60].lower()
        for w in ("bugfix", "refactor", "tests", "chat", "other"):
            if w in text:
                return w
    except Exception:
        pass
    return "other"

def stream_ollama(messages, model=None, on_chunk=None):
    """Stream a chat completion from Ollama. on_chunk(text_fragment) is called
    for every fragment as it arrives; returns the full text (think tags stripped)."""
    m = model or MODEL
    num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
    parts = []
    last_err = None
    for attempt in range(2):
        try:
            temp = 0.1 if attempt > 0 else 0.2
            payload = {
                "model": m, "messages": [msg for msg in messages if msg.get("content")],
                "stream": True, "keep_alive": -1,
                "options": {"temperature": temp, "num_predict": 2048, "num_ctx": num_ctx}
            }
            if _json_mode():
                payload["format"] = TOOL_JSON_SCHEMA
            with requests.post(f"{OLLAMA_URL}/api/chat", json=payload,
                               stream=True, timeout=180) as r:
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
            # retries are more deterministic (temp 0.1) — after a failure the
            # model should retry the exact same reasoning, not invent new ones
            temp = 0.1 if attempt > 0 else 0.2
            payload = {
                "model": m, "messages": [msg for msg in messages if msg.get("content")],
                "stream": False, "keep_alive": -1,
                "options": {"temperature": temp, "num_predict": 2048, "num_ctx": num_ctx}
            }
            if _json_mode():
                payload["format"] = TOOL_JSON_SCHEMA
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
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

# ─── native tool calling (Ollama /api/chat "tools") ─────
TOOL_DESCS = {
    "read": "Read a file from the workspace (relative path)",
    "write": "Create or overwrite a file with content",
    "edit": "Replace old text with new text in a file",
    "bash": "Run a shell command in the workspace",
    "glob": "Find files by glob pattern",
    "grep": "Search file contents by regex",
    "list": "List workspace files and folders",
    "web": "Fetch a web page and return text",
    "websearch": "Search the web (DuckDuckGo)",
    "diff": "Show uncommitted changes",
    "commit": "Commit all changes with a message",
    "undo": "Revert last write/edit of a file",
    "verify": "Syntax-check a file",
    "plan": "Propose a multi-step plan",
    "search": "Semantic code search (RAG)",
    "question": "Ask the user a multiple choice question",
    "skill": "Load a .agent_skills/*.md skill",
    "patch": "Apply a unified diff to a file",
    "task": "Delegate to a subagent (explore/scout/general/reviewer/fixer)",
    "todo": "Manage the in-session todo list",
    "lsp": "Code intelligence via LSP",
    "testgen": "Generate unit tests from code",
    "db_query": "Run an SQL query against the local SQLite DB",
    "deps": "Analyze project dependencies",
    "mcp": "Call an external MCP server tool",
    "snapshot": "Git pre-backup of all changes",
    "restore": "Restore all changes from the last snapshot",
}

_NATIVE_OPTIONAL = {
    "read": ["max_lines", "offset"],
    "bash": ["cwd"],
    "glob": ["path"],
    "grep": ["path", "include"],
    "search": ["top_k", "hybrid", "scope"],
    "web": ["format"],
    "websearch": ["num_results"],
    "write": ["append"],
    "edit": ["path"],
    "todo": ["items", "index"],
    "mcp": ["args", "prompt"],
    "lsp": ["operation", "path"],
}

_NATIVE_INT = {"top_k", "max_results", "num_results", "offset", "max_lines", "index", "character", "line"}


def _native_prop(key):
    if key in _NATIVE_INT:
        return {"type": "integer"}
    if key == "items":
        return {"type": "array", "items": {"type": "string"}}
    return {"type": "string"}


def native_supported(model):
    """True if the model name is known to support Ollama native tool calls
    (and native calling is not disabled via AI_NATIVE_TOOLS=0)."""
    if os.environ.get("AI_NATIVE_TOOLS", "").lower() in ("0", "off", "false", "no"):
        return False
    m = (model or "").lower()
    return any(m.startswith(p.lower()) for p in NATIVE_TOOL_MODELS)


def native_tools_schema():
    """TOOL_SCHEMAS -> Ollama tools=[{"type": "function", ...}]."""
    out = []
    for name, sch in TOOL_SCHEMAS.items():
        required = sch.get("required", [])
        props = {}
        for key in required:
            props[key] = _native_prop(key)
        for key in _NATIVE_OPTIONAL.get(name, ()):
            if key not in props:
                props[key] = _native_prop(key)
        out.append({"type": "function", "function": {
            "name": name,
            "description": TOOL_DESCS.get(name, name),
            "parameters": {"type": "object", "properties": props,
                           "required": required or None}}})
    return out


NATIVE_SYSTEM_PROMPT = """CRITICAL: You are a coding AGENT with tools on Windows.

WORKSPACE: . — project root.

You can call the provided FUNCTIONS (tools) when you need to act on the workspace.
RULES:
1. Complex multi-step tasks: call plan FIRST with steps, wait for user confirmation, then execute.
2. Ask before destructive tools: write, edit, bash, commit, undo.
3. When the user confirms with "yes"/"да" — proceed with the exact tool call you proposed.
4. NEVER invent tools — use ONLY the functions provided to you.
5. If a tool returns an error (file not found, bad args) — fix the arguments and retry (use glob to locate real paths). Report the final result only, no tutorials or checklists.
6. If no tool is needed — reply with plain text.
7. Answer in the user's language (same as the last user message).
8. Simple questions ("who are you", greetings, thanks, small talk) — answer DIRECTLY with one short sentence, NEVER call any tool.
9. NEVER write system markers like [PLAN], [CONFIRM], [tool:...] or "Reply yes" in your text.
10. After every write/edit — run a check with the bash function (e.g. python -m py_compile) and report the result.
11. ALWAYS read a file BEFORE calling edit or write on it (except brand-new files); the old text of an edit must be copied EXACTLY from the read output.
12. NEVER invent file paths; use paths returned by list/glob/grep; paths are RELATIVE to the workspace.
13. You may call several functions in one turn if they are independent and do not depend on each other's results.
14. The final reply to the user is plain text in the user's language.
15. Folder OUTSIDE the workspace (E:\app, D:\data)? Pass the FULL absolute path in every function (read/write/edit path='E:\app\file', glob with cwd='E:\app', list path='E:\app', bash with cwd='E:\app'). Never fall back to workspace files for that task. If a function says 'outside workspace' — stop and tell the user to add EXTRA_ROOTS.
16. Creating or extending a web app? Call the `skill` function (name "webapp") first.
17. Code review? Call `task` with agent="reviewer"; then fix the findings with agent="fixer" (never patch manually after a reviewer report). User can also start a message with @reviewer/@fixer/@general.
"""


def native_system_prompt():
    return NATIVE_SYSTEM_PROMPT


def native_chat(messages, model=None, tools=None):
    """Ollama native tool-calling chat. Returns (content, tool_calls, tokens).
    tool_calls: list of {"name": str, "arguments": dict}."""
    m = model or MODEL
    num_ctx = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
    payload = {
        "model": m,
        "messages": [msg for msg in messages if msg.get("content")],
        "stream": False, "keep_alive": -1,
        "options": {"temperature": 0.2, "num_predict": 2048, "num_ctx": num_ctx},
    }
    if tools is None:
        tools = native_tools_schema()
    payload["tools"] = tools
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    msg = data.get("message", {}) or {}
    content = re.sub(r'<think>.*?</think>', '', msg.get("content", "") or "",
                     flags=re.DOTALL)
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if name:
            calls.append({"name": name, "arguments": args or {}})
    return content, calls, data.get("eval_count", 0)


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

_sync_register(sys.modules[__name__])
