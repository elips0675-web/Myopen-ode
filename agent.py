#!/usr/bin/env python3
"""AI Coding Agent v2 — OpenCode Desktop alternative with DeepSeek support."""

import json, os, glob, webbrowser, re, time, logging, asyncio, subprocess, threading
from pathlib import Path
from datetime import datetime
import requests, uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from ui import HTML

logging.basicConfig(level=logging.WARNING, format='%(levelname)s [%(name)s] %(message)s')
log = logging.getLogger('agent')
log.setLevel(logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)

# ─── config ───────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AI_MODEL", "qwen2.5-coder:7b")
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

_VENDOR_ALLOW = {"xterm.min.js": "text/javascript", "xterm.css": "text/css"}

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

@app.get("/api/stats")
def tool_stats():
    """Per-tool call/error counters (diagnostics; shows repeated model failures)."""
    return TOOL_STATS

@app.get("/api/rag/status")
def rag_status():
    """RAG indexing progress (phase, files done/total, chunks) for the UI."""
    from rag import RAG_STATUS
    return dict(RAG_STATUS)

@app.get("/api/audit")
def audit_log(limit: str = "50"):
    """Last N lines of .agent_audit.log (action audit view in the UI)."""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, 500))
    try:
        lines = (WORK_DIR / ".agent_audit.log").read_text("utf-8", errors="ignore").splitlines()
        return {"lines": lines[-n:]}
    except Exception as e:
        return {"error": str(e)}

@app.get("/health")
def health():
    """Liveness + basic diagnostics for monitoring (uptime, model, session count)."""
    try:
        sessions = len(list_sessions_db())
    except Exception:
        sessions = 0
    from rag import RAG_CHUNKS, RAG_INDEX
    return {
        "status": "ok",
        "model": MODEL,
        "planner": PLANNER_MODEL,
        "workspace": str(WORK_DIR),
        "sessions": sessions,
        "rag_chunks": len(RAG_CHUNKS or []),
        "rag_embeddings": len(RAG_INDEX or []),
        "uptime_s": round(time.time() - _SERVER_START, 1),
    }

_UPDATE_CACHE = {"at": 0, "data": None}

@app.get("/api/update")
def update_check():
    """Check for new versions (git origin/master). Cached for 1 hour; graceful
    when offline or not a git checkout."""
    now = time.time()
    if _UPDATE_CACHE["data"] and now - _UPDATE_CACHE["at"] < 3600:
        return _UPDATE_CACHE["data"]
    try:
        cur = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(WORK_DIR),
                             capture_output=True, text=True, timeout=10).stdout.strip()
        remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/master"],
                                cwd=str(WORK_DIR), capture_output=True, text=True, timeout=20)
        latest = remote.stdout.split()[0][:7] if remote.stdout.split() else ""
        behind = 0
        if latest:
            bc = subprocess.run(["git", "rev-list", "--count", "HEAD..origin/master"],
                                cwd=str(WORK_DIR), capture_output=True, text=True, timeout=20)
            try: behind = int(bc.stdout.strip() or 0)
            except ValueError: pass
        data = {"ok": True, "current": cur, "latest": latest,
                "behind": behind, "has_update": bool(latest) and behind > 0}
    except Exception as e:
        data = {"ok": False, "error": str(e)[:120]}
    _UPDATE_CACHE.update({"at": now, "data": data})
    return data

@app.get("/api/models")
def list_models():
    try: return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags",timeout=5).json().get("models",[])]
    except: return [MODEL]

@app.post("/api/models/pull")
def pull_model(name: str = ""):
    if not name: return {"error": "Model name required"}
    try:
        r = requests.post(f"{OLLAMA_URL}/api/pull", json={"name": name}, stream=True, timeout=600)
        last = ""
        for line in r.iter_lines(decode_unicode=True):
            if line:
                try: last = json.loads(line).get("status", "")
                except: pass
        return {"status": last or "done"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/models/pull/stream")
def pull_model_stream(name: str = ""):
    if not name: return {"error": "Model name required"}
    async def gen():
        try:
            r = requests.post(f"{OLLAMA_URL}/api/pull", json={"name": name}, stream=True, timeout=600)
            for line in r.iter_lines(decode_unicode=True):
                if line:
                    yield f"data: {line}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.delete("/api/models/{name}")
def delete_model(name: str):
    try:
        r = requests.delete(f"{OLLAMA_URL}/api/delete", json={"name": name}, timeout=30)
        return {"status": "deleted" if r.ok else r.text}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/project")
def get_project(): return {"name": WORK_DIR.name, "path": str(WORK_DIR)}

@app.get("/api/projects")
def list_projects():
    return load_projects()

@app.post("/api/projects")
def add_project(req: ProjectReq):
    projects = load_projects()
    for p in projects: p["active"] = False
    path = req.path or str(WORK_DIR)
    projects.append({"name": req.name or Path(path).name, "path": path, "active": True})
    save_projects(projects)
    switch_project(path)
    return {"ok": True, "projects": projects}

@app.post("/api/projects/switch")
def switch_project_api(req: ProjectSwitchReq):
    path = req.path
    if not path: return {"error": "path required"}
    projects = load_projects()
    for p in projects:
        p["active"] = (p["path"] == path)
    save_projects(projects)
    switch_project(path)
    return {"ok": True, "project": {"name": WORK_DIR.name, "path": str(WORK_DIR)}}

@app.delete("/api/projects/{idx}")
def delete_project_api(idx: int):
    projects = load_projects()
    if idx < 0 or idx >= len(projects): return {"error": "Invalid index"}
    removed = projects.pop(idx)
    if removed.get("active") and projects:
        projects[0]["active"] = True
        switch_project(projects[0]["path"])
    save_projects(projects)
    return {"ok": True}

@app.get("/api/task/{agent_type}")
async def run_task(agent_type: str, prompt: str = ""):
    if not prompt: return {"error": "prompt required"}
    from tools import SUBAGENT_PROMPTS, call_ollama, PLANNER_MODEL
    sub_prompt = SUBAGENT_PROMPTS.get(agent_type, SUBAGENT_PROMPTS["general"])
    msgs = [{"role": "system", "content": sub_prompt}, {"role": "user", "content": prompt}]
    result, _ = call_ollama(msgs, PLANNER_MODEL)
    return {"result": result[:3000]}

@app.get("/api/plugins")
def list_plugins():
    from tools import PLUGINS
    return [{"name": n, "tools": list(p["tools"].keys())} for n, p in PLUGINS.items()]

@app.get("/api/skills")
def list_skills():
    skills_dir = WORK_DIR / ".agent_skills"
    if not skills_dir.exists():
        skills_dir.mkdir(exist_ok=True)
    skills = []
    for f in sorted(skills_dir.glob("*.md")):
        try:
            content = f.read_text("utf-8", errors="ignore")[:500]
            skills.append({"name": f.stem, "path": str(f.relative_to(WORK_DIR)), "preview": content[:200]})
        except: pass
    return skills

@app.get("/api/files")
def get_files(path: str = "."):
    return {"tree": build_tree(path), "current": path}

@app.get("/api/file")
def get_file(path: str):
    p = WORK_DIR / path if not os.path.isabs(path) else Path(path)
    if not p.exists() or p.is_dir(): return {"error": "Not found"}
    return {"content": p.read_text("utf-8", errors="ignore"), "path": path}

@app.put("/api/file")
def save_file(req: FileUploadReq):
    p = WORK_DIR / req.path if not os.path.isabs(req.path) else Path(req.path)
    if p.is_dir(): return {"error": "Is a directory"}
    p.parent.mkdir(parents=True, exist_ok=True)
    from tools import backup
    backup(req.path)
    p.write_text(req.content, "utf-8")
    return {"ok": True, "path": req.path, "size": len(req.content)}

@app.post("/api/upload")
async def upload_file(req: FileUploadReq):
    p = WORK_DIR / req.path if not os.path.isabs(req.path) else Path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, "utf-8")
    return {"ok": True, "path": req.path, "size": len(req.content)}

@app.get("/api/sessions")
def list_sessions():
    sessions = list_sessions_db()
    for s in sessions:
        s["interrupted"] = session_interrupted(s["id"])
    return sessions

@app.get("/api/sessions/search")
def search_sessions(q: str = "", limit: int = 20):
    """Full-text search across session messages (SQLite LIKE + JSON fallback)."""
    if not q.strip():
        return []
    ql = q.lower().strip()
    results = []
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT id, title, messages, updated FROM sessions WHERE lower(messages) LIKE ? ORDER BY updated DESC LIMIT ?",
                (f"%{ql}%", limit)).fetchall()
        for sid, title, raw, updated in rows:
            snippets = []
            try:
                msgs = json.loads(raw)
                for m in msgs:
                    c = m.get("content", "")
                    if isinstance(c, str) and ql in c.lower():
                        i = c.lower().find(ql)
                        a = max(0, i - 80)
                        snippets.append("…" + c[a:i + len(q) + 80].replace("\n", " ") + "…")
            except Exception:
                pass
            results.append({"id": sid, "title": title, "updated": updated,
                            "snippets": snippets[:3], "matches": len(snippets)})
    except Exception as e:
        log.warning("Session search db: %s", e)
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if any(r["id"] == f.stem for r in results):
            continue
        try:
            data = json.loads(f.read_text())
            msgs = data.get("messages", [])
            snippets = []
            for m in msgs:
                c = m.get("content", "")
                if isinstance(c, str) and ql in c.lower():
                    i = c.lower().find(ql)
                    a = max(0, i - 80)
                    snippets.append("…" + c[a:i + len(q) + 80].replace("\n", " ") + "…")
            if snippets:
                results.append({"id": f.stem, "title": data.get("title", f.stem),
                                "updated": data.get("updated", ""),
                                "snippets": snippets[:3], "matches": len(snippets)})
        except Exception:
            continue
    return results[:limit]

@app.post("/api/sessions")
def create_session(req: SessionReq):
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = req.title or f"Session {sid}"
    save_session(sid, title, [], datetime.now().isoformat())
    return {"id": sid, "title": title}

@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = load_session(sid)
    if s is None: return {"error": "Not found"}
    s["interrupted"] = session_interrupted(sid)
    return s

@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    delete_session_db(sid)
    return {"ok": True}

@app.get("/api/sessions/{sid}/export")
def export_session(sid: str):
    s = load_session(sid)
    if s is None: return {"error": "Not found"}
    return JSONResponse(content=s)

@app.post("/api/sessions/import")
def import_session(req: ChatReq):
    data = json.loads(req.model_dump_json())
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = data.get("title", f"Imported {sid}")
    messages = data.get("messages", data.get("content", []))
    if isinstance(messages, str):
        try: messages = json.loads(messages)
        except: messages = []
    save_session(sid, title, messages, datetime.now().isoformat())
    return {"id": sid, "title": title}

TERMINAL_PROCS = {}

@app.post("/api/terminal")
async def terminal(req: TerminalReq):
    """Run a shell command, streaming output via SSE."""
    cmd = req.cmd.strip()
    if not cmd:
        return {"error": "Empty command"}
    async def gen():
        try:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=req.cwd or WORK_DIR,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            TERMINAL_PROCS[id(gen)] = proc
            yield f"data: {json.dumps({'line': f'$ {cmd}', 'done': False})}\n\n"
            for line in proc.stdout:
                yield f"data: {json.dumps({'line': line, 'done': False})}\n\n"
            proc.wait()
            code = proc.returncode
            yield f"data: {json.dumps({'line': '', 'done': True, 'code': code})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'line': f'Error: {e}', 'done': True, 'code': -1})}\n\n"
        finally:
            TERMINAL_PROCS.pop(id(gen), None)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/api/terminal/kill")
def terminal_kill():
    n = 0
    for proc in list(TERMINAL_PROCS.values()):
        try:
            proc.kill()
            n += 1
        except: pass
    return {"killed": n}

@app.websocket("/ws/term")
async def ws_term(ws: WebSocket):
    """Interactive WebSocket terminal (xterm.js frontend, core/pty_shell.py).

    Client messages (JSON): {"cmd": str|None, "cwd", "cols", "rows"} to start,
    {"input": str} to write, {"resize": {cols, rows}}, {"kill": true} to stop.
    Server messages: {"out": str} chunks, {"exit": code} when the process ends.
    """
    from core.pty_shell import PtyShell
    await ws.accept()
    shell = None
    async def reader():
        nonlocal shell
        while True:
            if shell is None:
                await asyncio.sleep(0.05)
                continue
            data = shell.read_available()
            if data:
                try:
                    await ws.send_text(json.dumps({"out": data.decode("utf-8", "replace")}))
                except Exception:
                    return
            elif shell.dead:
                try:
                    await ws.send_text(json.dumps({"exit": shell.exit_code}))
                except Exception:
                    return
                return
            await asyncio.sleep(0.05)
    rtask = asyncio.create_task(reader())
    try:
        while True:
            msg = await ws.receive_text()
            try:
                m = json.loads(msg)
            except json.JSONDecodeError:
                continue
            if "cmd" in m:
                if shell is not None:
                    shell.kill()
                shell = PtyShell(m.get("cmd") or None, cwd=m.get("cwd") or WORK_DIR,
                                 cols=m.get("cols", 100), rows=m.get("rows", 30))
                await ws.send_text(json.dumps({"out": f"$ {' '.join(m['cmd']) if isinstance(m.get('cmd'), list) else m.get('cmd', '')}\r\n"}))
            elif "input" in m and shell is not None:
                shell.feed(m["input"])
            elif "resize" in m and shell is not None:
                shell.resize(m["resize"].get("cols"), m["resize"].get("rows"))
            elif m.get("kill"):
                if shell is not None:
                    shell.kill()
                await ws.send_text(json.dumps({"exit": shell.exit_code if shell is not None else 0}))
                break
    except WebSocketDisconnect:
        pass
    finally:
        rtask.cancel()
        if shell is not None:
            shell.kill()

@app.post("/api/lsp/completion")
def lsp_completion(req: dict):
    """Editor autocomplete: LSP first, token-based fallback if no language server."""
    path = req.get("path", "")
    text = req.get("text")
    line = int(req.get("line", 0))
    character = int(req.get("character", 0))
    try:
        from lsp import LSPClient, token_completions
        client = LSPClient(WORK_DIR)
        items = client.completion(path, line, character, text)
        if items:
            return {"items": items, "source": "lsp"}
        return {"items": token_completions(path, text, line, character) or [], "source": "tokens"}
    except Exception as e:
        try:
            from lsp import token_completions
            return {"items": token_completions(path, text, line, character) or [], "source": "tokens"}
        except Exception:
            return {"items": [], "error": str(e)}

@app.post("/api/chat")
async def chat(req: ChatReq):
    session_msgs = []
    if req.session_id:
        s = load_session(req.session_id)
        if s:
            try: session_msgs = s.get("messages", [])
            except: pass
    mem_text = memory_prompt()
    sys_content = SYSTEM_PROMPT + mem_text
    msgs = [{"role": "system", "content": sys_content}] + session_msgs + req.messages
    q = asyncio.Queue()
    loop = asyncio.get_running_loop()
    def emit(ev):
        loop.call_soon_threadsafe(q.put_nowait, ev)
    task = asyncio.create_task(asyncio.to_thread(run_agent_loop, msgs, req.session_id, emit, req.model or None))
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
