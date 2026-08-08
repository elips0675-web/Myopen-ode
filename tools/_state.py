"""Shared mutable state for the tools package.

All global values live here so that init_config() can update them after the
package was imported. Submodules keep local copies (for plain attribute access)
and register themselves via _sync_register() so init_config keeps the copies
in sync.
"""
import os, sys, threading
from pathlib import Path

log = __import__("logging").getLogger("tools")

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

# ─── JSON Schema constrained output (experimental) ────────
# Ollama `format` keeps the model honest about JSON. The agent loop enables it
# for specific retry iterations (after format/tool-error nudges); AI_JSON_FORMAT=1
# in the environment forces it on every call. No `required` field on purpose —
# the model may answer in prose ({answer: ...}) on turns where no tool is needed.
TOOL_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "path": {"type": "string"},
        "content": {"type": "string"},
        "text": {"type": "string"},
        "query": {"type": "string"},
        "pattern": {"type": "string"},
        "command": {"type": "string"},
        "old": {"type": "string"},
        "new": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
    },
}
_JSON_FMT = threading.local()

def set_json_mode(on):
    """Enable/disable the JSON Schema `format` for this thread's next call(s)."""
    _JSON_FMT.enabled = bool(on)

def _json_mode():
    if os.environ.get("AI_JSON_FORMAT") == "1":
        return True
    return bool(getattr(_JSON_FMT, "enabled", False))

# modules with copies of these values — kept in sync by init_config
_SYNC_MODULES = []

def _sync_register(mod):
    if mod not in _SYNC_MODULES:
        _SYNC_MODULES.append(mod)

def _set_config(key, value):
    setattr(sys.modules[__name__], key, value)
    for mod in _SYNC_MODULES:
        if hasattr(mod, key):
            setattr(mod, key, value)

def init_config(**kw):
    global BASH_TIMEOUT
    for k, v in kw.items():
        if v is not None:
            _set_config(k, v)
    # Apply AGENT_TIMEOUT to bash tool if set
    bash_timeout = os.environ.get("AGENT_TIMEOUT", "")
    if bash_timeout:
        try:
            _set_config("BASH_TIMEOUT", int(float(bash_timeout)))
        except ValueError:
            pass

# ─── file versioning ──────────────────────────────────────
BACKUP_DIR = None
MAX_BACKUPS = 50

# ─── tool schemas (mutated by load_plugins) ───────────────
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
    "snapshot": {"required": [], "description": "git pre-backup of all changes (tracked diff + untracked copies)"},
    "restore": {"required": [], "description": "restore all changes from the last snapshot (git checkout + re-apply tracked diff + sync untracked)"},
}

# ─── plugins system ───────────────────────────────────────
PLUGINS = {}

# ─── in-memory todo store ─────────────────────────────────
TODO_LIST = []

# ─── audit / stats ────────────────────────────────────────
AUDIT_LOG = None
TOOL_STATS = {}  # name -> {"calls": int, "errors": int}

# ─── LLM cache ────────────────────────────────────────────
LLM_CACHE = {}
LLM_CACHE_TTL = int(os.environ.get("LLM_CACHE_TTL", "60"))

# ─── native tool calling (Ollama /api/chat "tools") ──────
NATIVE_TOOL_MODELS = tuple(
    p.strip() for p in os.environ.get("AI_NATIVE_MODELS",
                                      "qwen3,llama3.1,gpt-oss").split(",")
    if p.strip())
