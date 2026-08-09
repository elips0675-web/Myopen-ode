#!/usr/bin/env python3
"""AI Coding Agent v2 — OpenCode Desktop alternative with DeepSeek support."""

import sys
if __name__ == "__main__" and "agent" not in sys.modules:
    # running as `python agent.py` registers itself under the module name
    # so api_* routers import the same instance instead of a fresh copy
    sys.modules["agent"] = sys.modules["__main__"]

import json, os, webbrowser, re, time, logging, asyncio, threading, subprocess
from pathlib import Path
from datetime import datetime
import requests, uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi import Request
from pydantic import BaseModel
from ui import HTML

logging.basicConfig(level=logging.WARNING, format='%(levelname)s [%(name)s] %(message)s')
log = logging.getLogger('agent')
log.setLevel(logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)

# ─── config ───────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AI_MODEL", "qwen2.5-coder:7b")


def _auto_pick_model():
    """Stage 25 (DS4): pick qwen3:8b as default when the GPU has >=10GB VRAM
    and the model is installed. Only when AI_MODEL was NOT set explicitly —
    an explicit user choice always wins. Logs the decision."""
    global MODEL
    if os.environ.get("AI_MODEL"):
        return MODEL
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=15)
        installed = [ln.split()[0] for ln in r.stdout.splitlines()[1:] if ln.strip()]
        if "qwen3:8b" not in installed:
            return MODEL
        vr = subprocess.run(["nvidia-smi", "--query-gpu=memory.total",
                             "--format=csv,noheader,nounits"], capture_output=True,
                            text=True, timeout=15)
        vram = max((int(x.strip()) for x in vr.stdout.splitlines() if x.strip().isdigit()),
                   default=0)
        if vram >= 10_000:  # MB
            MODEL = "qwen3:8b"
            log.info("Auto-picked qwen3:8b as default (%.1f GB VRAM, installed)", vram / 1024)
    except Exception:
        pass
    return MODEL


_auto_pick_model()


def _detect_docker():
    """Stage 26 (DS4): when Docker is present, suggest the bash sandbox.
    Detection is one `docker version` call; a failing daemon just means the
    local shell stays in use. Returns True when docker is usable."""
    if os.environ.get("DOCKER_SANDBOX") == "0":
        return False
    try:
        r = subprocess.run(["docker", "version"], capture_output=True,
                           text=True, timeout=5)
        ok = r.returncode == 0
        if ok:
            log.warning("Docker detected — bash commands CAN run sandboxed: "
                        "set DOCKER_SANDBOX=1 to enable (0 to disable detection)")
        return ok
    except Exception:
        return False


_detect_docker()
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "deepseek-r1:1.5b")
WORK_DIR = Path(os.environ.get("WORK_DIR") or Path(__file__).resolve().parent)
NO_CONFIRM = os.environ.get("NO_CONFIRM", "0") == "1"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "0"))
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "")
FLASH_PROVIDER = os.environ.get("FLASH_PROVIDER", "")
FLASH_API_KEY = os.environ.get("FLASH_API_KEY", "")
FLASH_MODEL = os.environ.get("FLASH_MODEL", "deepseek-v4-flash")

# pending confirmations: session_id -> (tool_name, args) awaiting user "yes"
_PENDING_CONFIRM = {}
_PENDING_LOCK = threading.Lock()
def _pending_set(session_id, name, tc):
    with _PENDING_LOCK:
        _PENDING_CONFIRM[session_id or ""] = (name, dict(tc))
def _pending_get(session_id):
    with _PENDING_LOCK:
        return _PENDING_CONFIRM.pop(session_id or "", None)
def _pending_clear(session_id):
    with _PENDING_LOCK:
        _PENDING_CONFIRM.pop(session_id or "", None)

# graceful cancellation: session_id -> cancelled flag (checked between iterations)
_CANCEL_FLAGS = set()
_CANCEL_LOCK = threading.Lock()
def _cancel_set(session_id):
    with _CANCEL_LOCK:
        _CANCEL_FLAGS.add(session_id or "")
def _cancel_clear(session_id):
    with _CANCEL_LOCK:
        _CANCEL_FLAGS.discard(session_id or "")
def _cancel_pending(session_id):
    with _CANCEL_LOCK:
        return (session_id or "") in _CANCEL_FLAGS

# ─── rate limiting (stage 35) ──────────────────────────────
# Sliding-window per-IP cap for /api/chat (LAN DoS protection) + a cap on
# concurrent in-flight chat runs per IP (slow client / many sessions).
RATE_MAX = int(os.environ.get("AI_RATE_LIMIT", "60"))       # requests per window
RATE_WINDOW = float(os.environ.get("AI_RATE_WINDOW", "60.0"))
RATE_BURST = int(os.environ.get("AI_RATE_BURST", "6"))      # concurrent per IP
_RATE_HITS = {}     # ip -> [timestamps]
_RATE_INFLIGHT = {}  # ip -> int
_RATE_LOCK = threading.Lock()

def _rate_limited(ip):
    """Return (blocked, retry_seconds) for the given client IP."""
    if RATE_MAX <= 0:
        return False, None
    now = time.time()
    with _RATE_LOCK:
        dq = _RATE_HITS.setdefault(ip, [])
        while dq and now - dq[0] > RATE_WINDOW:
            dq.pop(0)
        if len(dq) >= RATE_MAX:
            return True, int(RATE_WINDOW - (now - dq[0]) + 1)
        dq.append(now)
        if _RATE_INFLIGHT.get(ip, 0) >= RATE_BURST:
            return True, 2
    return False, None

def _rate_inc(ip):
    with _RATE_LOCK:
        _RATE_INFLIGHT[ip] = _RATE_INFLIGHT.get(ip, 0) + 1

def _rate_dec(ip):
    with _RATE_LOCK:
        _RATE_INFLIGHT[ip] = max(0, _RATE_INFLIGHT.get(ip, 0) - 1)

# ─── import tools & rag ───────────────────────────────────
from tools import (init_config, execute_tool, validate_tool, call_ollama,
                   stream_ollama, SYSTEM_PROMPT, init_backup, TOOL_STATS)
from rag import init_rag, rag_search

# ─── core engine (extracted modules) ──────────────────────
from core.agent_loop import run_agent_loop, _dynamic_context, summarize_context  # noqa: E402
from core.tool_parser import (_parse_tool_json, _strip_system_markers,          # noqa: E402
                              extract_pending_tool, parse_tool_blocks)
from core.tool_executor import _sess_record                                     # noqa: E402

init_config(OLLAMA_URL=OLLAMA_URL, MODEL=MODEL, PLANNER_MODEL=PLANNER_MODEL,
    WORK_DIR=WORK_DIR, EMBED_MODEL=EMBED_MODEL, NO_CONFIRM=NO_CONFIRM,
    MAX_TOKENS=MAX_TOKENS, OPENAI_KEY=OPENAI_KEY, ANTHROPIC_KEY=ANTHROPIC_KEY,
    FALLBACK_MODEL=FALLBACK_MODEL)

init_backup()
init_rag(OLLAMA_URL=OLLAMA_URL, WORK_DIR=WORK_DIR, EMBED_MODEL=EMBED_MODEL)
from tools import load_plugins
load_plugins()

# ─── DI container (stage 41) + storage abstractions (stage 42) ──
from core import abstractions
from core.container import register as _di_register
_di_register("work_dir", lambda: WORK_DIR)
_di_register("sessions_dir", lambda: SESSIONS_DIR)
_di_register("memory_dir", lambda: MEMORY_DIR)
_di_register("logger", lambda: log)
abstractions.init_defaults()  # registers 'rag' (RagAdapter over rag module)
_di_register("sessions_db", lambda: abstractions.SqliteKVStore(DB_PATH))

# ─── projects management ──────────────────────────────────
AGENT_HOME = Path(__file__).parent
PROJECTS_FILE = AGENT_HOME / "projects.json"

def load_projects():
    if not PROJECTS_FILE.exists():
        default = [{"name": WORK_DIR.name, "path": str(WORK_DIR), "active": True}]
        save_projects(default)
        return default
    try: return json.loads(PROJECTS_FILE.read_text())
    except: return [{"name": WORK_DIR.name, "path": str(WORK_DIR), "active": True}]

def save_projects(projects):
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2, ensure_ascii=False), "utf-8")

def switch_project(path):
    global WORK_DIR, SESSIONS_DIR, MEMORY_DIR
    new_wd = Path(path).resolve()
    if not new_wd.exists():
        new_wd.mkdir(parents=True, exist_ok=True)
    old_wd = WORK_DIR
    WORK_DIR = new_wd
    # Re-init configs with new WORK_DIR
    init_config(WORK_DIR=WORK_DIR)
    init_backup()
    init_rag(OLLAMA_URL=OLLAMA_URL, WORK_DIR=WORK_DIR, EMBED_MODEL=EMBED_MODEL)
    SESSIONS_DIR = WORK_DIR / ".agent_sessions"
    SESSIONS_DIR.mkdir(exist_ok=True)
    MEMORY_DIR = WORK_DIR / ".agent_memory"
    MEMORY_DIR.mkdir(exist_ok=True)
    # Update SYSTEM_PROMPT with new workspace
    from tools import SYSTEM_PROMPT as _
    # Reload tools module config
    from tools import load_plugins
    load_plugins()
    log.info("Switched project: %s → %s", old_wd.name, WORK_DIR.name)
    return True

# ─── sessions ────────────────────────────────────────────
SESSIONS_DIR = WORK_DIR / ".agent_sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# SQLite storage (primary) with JSON fallback
DB_PATH = SESSIONS_DIR / "sessions.db"

def _db():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT, messages TEXT, created TEXT, updated TEXT)")
    return conn

def _db_ok():
    try:
        with _db() as conn:
            conn.execute("SELECT 1 FROM sessions LIMIT 1")
        return True
    except sqlite3.Error:
        return False

def save_session(sid, title, messages, updated=None):
    updated = updated or datetime.now().isoformat()
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, messages, created, updated) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, messages=excluded.messages, updated=excluded.updated",
                (sid, title, json.dumps(messages, ensure_ascii=False), updated, updated))
        return True
    except (sqlite3.Error, OSError):
        try:
            (SESSIONS_DIR / f"{sid}.json").write_text(
                json.dumps({"title": title, "messages": messages, "updated": updated}, ensure_ascii=False), "utf-8")
            return True
        except OSError:
            return False

def load_session(sid):
    try:
        with _db() as conn:
            row = conn.execute("SELECT title, messages, updated FROM sessions WHERE id=?", (sid,)).fetchone()
        if row:
            return {"id": sid, "title": row[0], "messages": json.loads(row[1]), "updated": row[2]}
    except (sqlite3.Error, json.JSONDecodeError):
        pass
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists():
        try:
            return {"id": sid, **json.loads(f.read_text())}
        except json.JSONDecodeError:
            return None
    return None

def delete_session_db(sid):
    try:
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
    except sqlite3.Error:
        pass
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists(): f.unlink()
    try:
        _state_path(sid).unlink(missing_ok=True)
    except OSError:
        pass

def _state_path(sid):
    return SESSIONS_DIR / f"{sid}.state"

def session_interrupted(sid):
    """True if the last run of this session crashed mid-loop (stale runtime
    state file: created when the loop starts, touched on checkpoints, removed
    on clean finish; anything still there after >90s is a crashed run)."""
    try:
        p = _state_path(sid)
        if p.exists() and time.time() - p.stat().st_mtime > 90:
            return True
    except OSError:
        pass
    return False

def list_sessions_db():
    sessions = []
    try:
        with _db() as conn:
            rows = conn.execute("SELECT id, title, updated FROM sessions ORDER BY updated DESC").fetchall()
        sessions = [{"id": r[0], "title": r[1], "updated": r[2], "messages": []} for r in rows]
    except sqlite3.Error:
        pass
    json_ids = {s["id"] for s in sessions}
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.stem in json_ids: continue
        try:
            data = json.loads(f.read_text())
            sessions.append({"id": f.stem, "title": data.get("title", f.stem),
                "updated": data.get("updated", ""), "messages": data.get("messages", [])})
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Bad session file %s: %s", f.name, e)
    sessions.sort(key=lambda s: s.get("updated", ""), reverse=True)
    return sessions

def migrate_json_sessions():
    """One-time import of legacy *.json sessions into SQLite."""
    if not _db_ok(): return 0
    count = 0
    try:
        with _db() as conn:
            existing = {r[0] for r in conn.execute("SELECT id FROM sessions").fetchall()}
    except sqlite3.Error:
        return 0
    for f in sorted(SESSIONS_DIR.glob("*.json")):
        if f.stem in existing: continue
        try:
            data = json.loads(f.read_text())
            messages = data.get("messages", [])
            updated = data.get("updated", datetime.now().isoformat())
            if save_session(f.stem, data.get("title", f.stem), messages, updated):
                count += 1
        except (json.JSONDecodeError, OSError):
            continue
    return count

MEMORY_DIR = WORK_DIR / ".agent_memory"
MEMORY_DIR.mkdir(exist_ok=True)
AGENT_MEMORY_LIMIT = int(os.environ.get("AGENT_MEMORY_LIMIT", "10"))

def load_memory():
    mems = []
    for f in sorted(MEMORY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:AGENT_MEMORY_LIMIT]:
        try:
            data = json.loads(f.read_text())
            if data.get("summary"):
                mems.append(data["summary"])
        except: pass
    return mems

def save_memory(session_id, messages):
    texts = [m["content"][:300] for m in messages[-10:] if m.get("content")]
    if not texts: return
    prompt = "Summarize what was accomplished in 1-2 sentences:\n" + "\n".join(texts)[:1000]
    summary = ""
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json={
            "model": PLANNER_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.1, "num_predict": 128}
        }, timeout=15)
        summary = r.json().get("response", "")
    except: pass
    mem = {"id": session_id, "summary": summary[:500], "time": datetime.now().isoformat()}
    (MEMORY_DIR / f"{session_id}_memory.json").write_text(json.dumps(mem, ensure_ascii=False), "utf-8")

def memory_prompt():
    mems = load_memory()
    return "\nPrevious session memories:\n" + "\n".join(f"- {m}" for m in mems) if mems else ""

# ─── file tree helper ────────────────────────────────────
def build_tree(path, root=None):
    if root is None: root = WORK_DIR
    p = Path(path) if os.path.isabs(path) else WORK_DIR / path
    if not p.exists() or not p.is_dir(): return []
    result = []
    try:
        for item in sorted(p.iterdir()):
            if item.name.startswith(".") and item.name not in (".env", ".gitignore"): continue
            rel = str(item.relative_to(root))
            node = {"name": item.name, "path": rel, "type": "dir" if item.is_dir() else "file"}
            if item.is_dir():
                children = build_tree(str(item), root)
                if children: node["children"] = children
            result.append(node)
    except Exception as e:
        log.warning("build_tree error: %s", e)
    return result

# ─── agent loop ──────────────────────────────────────────
def _get_available_models():
    try:
        return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])]
    except:
        return []

_available_models = _get_available_models()

# agent loop lives in core/agent_loop.py (run_agent_loop, _dynamic_context,
# _sess_record, summarize_context are re-exported above); this module keeps
# the HTTP layer, sessions, memory, pending/cancel state and project management.

# ─── API models ──────────────────────────────────────────
class ChatReq(BaseModel): messages: list; model: str = ""; session_id: str = ""
class CancelReq(BaseModel): session_id: str = ""
class SessionReq(BaseModel): title: str = ""
class FileUploadReq(BaseModel): path: str = ""; content: str = ""
class ProjectReq(BaseModel): name: str = ""; path: str = ""
class ProjectSwitchReq(BaseModel): path: str = ""
class TerminalReq(BaseModel): cmd: str = ""; cwd: str = ""

# ─── FastAPI app ─────────────────────────────────────────
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/")
def index(): return HTMLResponse(HTML)

@app.get("/static/app.js")
def app_js():
    """Serve the extracted UI script (kept out of ui.py for maintainability)."""
    try:
        path = WORK_DIR / "static" / "app.js"
        resp = FileResponse(path, media_type="text/javascript")
        resp.headers["Cache-Control"] = "public, max-age=300"
        return resp
    except OSError as e:
        return JSONResponse({"error": f"static/app.js unavailable: {e}"}, status_code=404)

_VENDOR_ALLOW = {"xterm.min.js": "text/javascript", "xterm.css": "text/css",
                 "cm6.bundle.js": "text/javascript"}

@app.get("/static/vendor/{fname}")
def vendor_file(fname: str):
    """Vendored frontend libraries (xterm.js) with a strict whitelist."""
    if fname not in _VENDOR_ALLOW:
        raise HTTPException(404)
    try:
        resp = FileResponse(WORK_DIR / "static" / "vendor" / fname, media_type=_VENDOR_ALLOW[fname])
        resp.headers["Cache-Control"] = "public, max-age=3600"
        return resp
    except OSError as e:
        return JSONResponse({"error": f"vendor file unavailable: {e}"}, status_code=404)

app.mount("/static/vendor/cm", StaticFiles(directory=WORK_DIR / "static" / "vendor" / "cm"), name="codemirror")


@app.post("/api/chat")
async def chat(req: ChatReq, request: Request = None):
    if request and request.client and request.client.host:
        blocked, retry = _rate_limited(request.client.host)
        if blocked:
            raise HTTPException(429, detail=f"Rate limit exceeded — retry in ~{retry}s")
    session_msgs = []
    if req.session_id:
        s = load_session(req.session_id)
        if s:
            try: session_msgs = s.get("messages", [])
            except: pass
    mem_text = memory_prompt()
    sys_content = SYSTEM_PROMPT + mem_text
    msgs = [{"role": "system", "content": sys_content}] + session_msgs + req.messages
    first_text = next((m.get("content", "") for m in req.messages
                       if m.get("role") == "user"), "") or ""
    chosen_model = req.model or None
    if not chosen_model:
        from tools.llm import pick_task_model as _ptm
        chosen_model = _ptm(first_text, MODEL)
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()
    def emit(ev):
        loop.call_soon_threadsafe(q.put_nowait, ev)
    _rate_inc(request.client.host if request and request.client else "?")
    task = asyncio.create_task(asyncio.to_thread(run_agent_loop, msgs, req.session_id, emit, chosen_model or None))
    task.add_done_callback(lambda _t: _rate_dec(request.client.host if request and request.client else "?"))
    if req.session_id:
        _cancel_clear(req.session_id)
    async def gen():
        # 1) live events (tool progress + streamed model text) while the loop runs
        live_text = False
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.5)
                if ev.get("type") == "text":
                    live_text = True
                    yield f"data: {json.dumps({'text': ev['text']})}\n\n"
                else:
                    yield f"data: {json.dumps({'tool': ev})}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    # loop ended: drain remaining events with a small grace
                    # period so events emitted right before completion arrive
                    for _ in range(20):
                        if not q.empty():
                            ev = q.get_nowait()
                            if ev.get("type") == "text":
                                live_text = True
                                yield f"data: {json.dumps({'text': ev['text']})}\n\n"
                            else:
                                yield f"data: {json.dumps({'tool': ev})}\n\n"
                        else:
                            await asyncio.sleep(0.1)
                    while not q.empty():
                        ev = q.get_nowait()
                        if ev.get("type") == "text":
                            live_text = True
                            yield f"data: {json.dumps({'text': ev['text']})}\n\n"
                        else:
                            yield f"data: {json.dumps({'tool': ev})}\n\n"
                    break
        # 2) final text stream (only if nothing was streamed live — avoids duplication)
        try:
            full = await task
        except Exception as e:
            full = f"[Error: {e}]"
        if req.session_id and msgs:
            try: save_memory(req.session_id, msgs)
            except: pass
        if not live_text:
            for i in range(0, len(full), 3):
                chunk = full[i:i+3]
                if chunk.strip():
                    yield f"data: {json.dumps({'text':chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/api/chat/cancel")
async def cancel_chat(req: CancelReq):
    """Graceful cancel: sets the session's cancel flag; the agent loop stops
    between iterations and the client gets '[cancelled]'."""
    _cancel_set(req.session_id)
    return {"ok": True}


# ─── extracted API routers ─────────────────────────
from api_sessions import router as sessions_router  # noqa: E402
from api_files import router as files_router        # noqa: E402
from api_misc import router as misc_router          # noqa: E402
from stt import router as stt_router                # noqa: E402
app.include_router(sessions_router)
app.include_router(files_router)
app.include_router(misc_router)
app.include_router(stt_router)

# ─── wait ollama ─────────────────────────────────────────
def wait_ollama():
    for i in range(3):
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if r.ok:
                log.info("Ollama connected")
                return True
        except Exception as e:
            log.warning("Ollama not ready (attempt %d/3): %s", i+1, e)
        time.sleep(2)
    log.error("Ollama unavailable after 3 attempts")
    return False

# ─── main ────────────────────────────────────────────────
def main():
    wait_ollama()
    migrated = migrate_json_sessions()
    if migrated:
        log.info("Migrated %d legacy JSON sessions to SQLite", migrated)
    port = int(os.environ.get("PORT", "8765"))
    url = f"http://localhost:{port}"
    print(f"\n  🤖 AI Coder v2 — OpenCode Desktop")
    print(f"  🌐 {url}")
    print(f"  📁 Project: {WORK_DIR.name}")
    print(f"  🧠 Model: {MODEL}")
    print(f"  📋 Planner: {PLANNER_MODEL}")
    print(f"  🔤 Embed: {EMBED_MODEL}")
    print(f"  ⚡ NO_CONFIRM: {NO_CONFIRM}")
    print(f"  🎯 Max Tokens: {MAX_TOKENS if MAX_TOKENS else 'unlimited'}")
    if FALLBACK_MODEL:
        print(f"  🔄 Fallback: {FALLBACK_MODEL}")
    print(f"  Ctrl+C to exit\n")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

_SERVER_START = time.time()

if __name__ == "__main__":
    main()
