#!/usr/bin/env python3
"""AI Coding Agent v2 — OpenCode Desktop alternative with DeepSeek support."""

import json, os, glob, webbrowser, re, time, logging, asyncio, subprocess, threading
from pathlib import Path
from datetime import datetime
import requests, uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
from ui import HTML

logging.basicConfig(level=logging.WARNING, format='%(levelname)s [%(name)s] %(message)s')
log = logging.getLogger('agent')
log.setLevel(logging.DEBUG if os.environ.get("DEBUG") else logging.INFO)

# ─── config ───────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AI_MODEL", "deepseek-r1:7b")
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "deepseek-r1:1.5b")
WORK_DIR = Path(os.environ.get("WORK_DIR", "E:\\My OpenCode"))
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

# ─── import tools & rag ───────────────────────────────────
from tools import (init_config, execute_tool, validate_tool, call_ollama,
    extract_pending_tool, SYSTEM_PROMPT, init_backup)
from rag import init_rag, rag_search

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
    except Exception:
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
    except Exception:
        try:
            (SESSIONS_DIR / f"{sid}.json").write_text(
                json.dumps({"title": title, "messages": messages, "updated": updated}, ensure_ascii=False), "utf-8")
            return True
        except Exception:
            return False

def load_session(sid):
    try:
        with _db() as conn:
            row = conn.execute("SELECT title, messages, updated FROM sessions WHERE id=?", (sid,)).fetchone()
        if row:
            return {"id": sid, "title": row[0], "messages": json.loads(row[1]), "updated": row[2]}
    except Exception:
        pass
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists():
        return {"id": sid, **json.loads(f.read_text())}
    return None

def delete_session_db(sid):
    try:
        with _db() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
    except Exception:
        pass
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists(): f.unlink()

def list_sessions_db():
    sessions = []
    try:
        with _db() as conn:
            rows = conn.execute("SELECT id, title, updated FROM sessions ORDER BY updated DESC").fetchall()
        sessions = [{"id": r[0], "title": r[1], "updated": r[2], "messages": []} for r in rows]
    except Exception:
        pass
    json_ids = {s["id"] for s in sessions}
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.stem in json_ids: continue
        try:
            data = json.loads(f.read_text())
            sessions.append({"id": f.stem, "title": data.get("title", f.stem),
                "updated": data.get("updated", ""), "messages": data.get("messages", [])})
        except Exception as e:
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
    except Exception:
        return 0
    for f in sorted(SESSIONS_DIR.glob("*.json")):
        if f.stem in existing: continue
        try:
            data = json.loads(f.read_text())
            messages = data.get("messages", [])
            updated = data.get("updated", datetime.now().isoformat())
            if save_session(f.stem, data.get("title", f.stem), messages, updated):
                count += 1
        except Exception:
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

# ─── context management ──────────────────────────────────
def summarize_context(msgs):
    total = sum(len(m.get("content","")) for m in msgs)
    if total < 4000: return msgs
    keep = msgs[:1]
    tail = msgs[-6:] if len(msgs) > 6 else msgs[1:]
    to_summarize = msgs[1:-6] if len(msgs) > 6 else []
    if to_summarize:
        text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in to_summarize)
        prompt = f"Summarize this conversation in 2-3 sentences:\n\n{text[:1500]}"
        try:
            r = requests.post(f"{OLLAMA_URL}/api/generate", json={
                "model": PLANNER_MODEL,
                "prompt": prompt, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 256}
            }, timeout=30)
            summary = r.json().get("response", "")
            if summary:
                keep.append({"role": "system", "content": f"[Summary]: {summary[:500]}"})
        except Exception as e:
            log.warning("Summarize failed: %s", e)
    keep.extend(tail)
    return keep

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

def run_agent_loop(msgs, session_id, events=None, model=None):
    """Run agent loop. events: optional callback(ev: dict) for live tool progress.
    model: user-selected model overrides MODEL (empty = default)."""
    def _emit(ev):
        if events:
            try: events(ev)
            except: pass
    msgs = summarize_context(msgs)
    full = ""
    tool_pat = re.compile('```(?:tool|json)\n(.*?)\n```', re.DOTALL)
    bare_tool_pat = re.compile(r'\{\s*"tool"\s*:\s*"[^"]+"\s*.*?\}', re.DOTALL)
    yaml_tool_pat = re.compile(r'```[^\n]*\ntool\s+(\w+)\n(.*?)\n```', re.DOTALL)
    VALID_TOOLS = ("read","write","edit","bash","glob","grep","list","web","diff","commit","undo","verify","plan","search","websearch","question","skill","patch","task","todo","lsp")
    max_iter = int(os.environ.get("AGENT_MAX_ITER", "12"))
    max_time = float(os.environ.get("AGENT_TIMEOUT", "60.0"))
    start_time = time.time()
    total_tokens = sum(len(m.get("content", "")) / 4 for m in msgs)
    format_retried = 0

    for it in range(max_iter):
        if time.time() - start_time > max_time:
            full += f"\n[tool: TIMEOUT — agent loop exceeded {int(max_time)}s]\n"
            break

        _emit({"type": "status", "msg": f"iteration {it+1}/{max_iter}"})

        # Summarize context every 3 iterations to keep token usage in check
        if it > 0 and it % 3 == 0:
            msgs = summarize_context(msgs)

        # pending confirmation: user said "yes" — execute the deferred tool without calling the model
        pending = _pending_get(session_id)
        if pending:
            name, tc = pending
            last = (msgs[-1]["content"].strip().lower() if msgs else "")[:5]
            if last in ("yes","y","go a","да","ok","cont","proc","do i"):
                r = execute_tool(name, tc)
                _emit({"type": "tool", "name": name, "args": tc, "result": r[:200]})
                full += f"\n[tool:{name}] {r[:2000]}\n"
                msgs.append({"role":"assistant","content":f"(confirmed: {name})"})
                msgs.append({"role":"user","content":r[:2000]})
                continue
            _pending_set(session_id, name, tc)  # not confirmed yet, keep waiting

        current_model = model or (PLANNER_MODEL if it == 0 else MODEL)
        if not model and it == 0 and PLANNER_MODEL not in _available_models:
            log.info("PLANNER_MODEL %s not installed, using %s", PLANNER_MODEL, MODEL)
            current_model = MODEL
        result = call_ollama(msgs, current_model)
        if isinstance(result, tuple):
            content, tokens_used = result
        else:
            content = result
            tokens_used = 0
        if not content: break
        total_tokens += tokens_used or (len(content) / 4)

        tool_blocks = []
        for m in tool_pat.finditer(content):
            raw = m.group(1).strip()
            try: j = json.loads(raw); tool_blocks.append((m, raw, j))
            except:
                try: j = json.loads(raw.replace("'", '"')); tool_blocks.append((m, raw, j))
                except:
                    log.debug("Failed to parse tool block: %.60s", raw)

        if not tool_blocks:
            for match in bare_tool_pat.finditer(content):
                try:
                    j = json.loads(match.group())
                    if "tool" in j and j["tool"] in VALID_TOOLS:
                        tool_blocks.append((match, match.group(), j))
                        break
                except: pass

        if not tool_blocks:
            # yaml-style fallback: models sometimes emit `tool <name>` blocks
            # (```python\ntool write\npath "demo.py"\ncontent "..."\n```)
            for m in yaml_tool_pat.finditer(content):
                name, body = m.group(1), m.group(2)
                if name not in VALID_TOOLS: continue
                args = {}
                for line in body.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or " " not in line: continue
                    k, _, v = line.partition(" ")
                    k = k.strip().rstrip(":")
                    v = v.strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                        v = v[1:-1]
                    elif v.startswith("[") or v.startswith("{"):
                        try: v = json.loads(v)
                        except: pass
                    args[k] = v
                if args:
                    tool_blocks.append((m, m.group(0), {"tool": name, **args}))
                    log.info("YAML-style tool block parsed: %s %s", name, list(args))

        last_msg = msgs[-1]["content"].strip().lower() if msgs else ""
        if not tool_blocks and last_msg[:5] in ("yes","y","go a","да","ok","cont","proc","do i"):
            pn, pa = extract_pending_tool(msgs)
            if pn:
                log.info("Auto-exec pending %s after '%s'", pn, last_msg[:10])
                r = execute_tool(pn, pa)
                _emit({"type": "tool", "name": pn, "args": pa, "result": r[:200]})
                full += f"\n[tool:{pn}] {r[:2000]}\n"
                msgs.append({"role":"assistant","content":f"(auto-executed {pn})"})
                msgs.append({"role":"user","content":r[:2000]})
                continue

        if not tool_blocks:
            if it == 0 and current_model != MODEL:
                # planner model (1.5b) often ignores tool format — retry with main model
                log.info("Planner iteration produced no tool blocks; retrying with %s", MODEL)
                full += content + "\n"
                continue
            if format_retried < 1 and len(content.strip()) > 20:
                # main model ignored tool format (free-form answer) — one strict retry
                hint = "[Format error: reply ONLY with ```tool JSON blocks. No prose, no code blocks.]"
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": hint})
                full += content + "\n[Format error — retrying with strict hint]\n"
                format_retried += 1
                continue
            full += content
            break

        before = content[:tool_blocks[0][0].start()].strip()
        if before:
            full += before + "\n"
            msgs.append({"role": "assistant", "content": before})

        all_results = []
        calls_made = []
        needs_break = False
        DESTRUCTIVE = () if NO_CONFIRM else ("write", "edit", "bash", "commit", "undo")
        for idx, (match, raw_json, tc) in enumerate(tool_blocks):
            name = tc.get("tool", "")
            raw_tc = dict(tc)
            tc.pop("tool", None)
            # Aliases: models often call python/shell/terminal instead of bash
            if name in ("python", "shell", "terminal", "cmd", "run"):
                tc["cmd"] = tc.get("cmd", tc.get("command", ""))
                name = "bash"
            if not name:
                all_results.append(f"[tool: missing 'tool' key in block {idx+1}]")
                continue
            ve = validate_tool({**tc, "tool": name})
            if ve:
                all_results.append(f"[tool:{name}] {ve}")
                calls_made.append(name)
                continue
            if name == "plan":
                steps = tc.get("steps", [])
                if isinstance(steps, str):
                    steps = [s.strip() for s in re.split(r'[.,;\n]+', steps) if s.strip()]
                plan_text = "\n".join(f"  {i+1}. {s}" for i,s in enumerate(steps))
                full += f"\n[PLAN]\n{plan_text}\n\nReply 'yes' to execute plan.\n"
                msgs.append({"role":"assistant","content":content})
                msgs.append({"role":"user","content":f"Plan proposed:\n{plan_text}\nReply 'yes' to execute."})
                needs_break=True; break
            if name in DESTRUCTIVE:
                last = (msgs[-1]["content"].strip().lower() if msgs else "")[:5]
                if last in ("yes","y","go a","да","ok","cont","proc","do i"):
                    r = execute_tool(name,tc)
                    _emit({"type": "tool", "name": name, "args": tc, "result": r[:200]})
                    all_results.append(f"[tool:{name}] {r[:2000]}")
                    calls_made.append(name)
                else:
                    ask = f"Allow {name}?\nArgs: {json.dumps(tc, ensure_ascii=False)[:300]}"
                    full += f"\n[CONFIRM] {ask}\nReply 'yes' to proceed.\n"
                    msgs.append({"role":"assistant","content":content})
                    hint = f"User must reply 'yes' to execute {name}."
                    msgs.append({"role":"system","content":hint})
                    msgs.append({"role":"user","content":ask})
                    _pending_set(session_id, name, tc)
                    needs_break=True; break
                continue
            r = execute_tool(name,tc)
            _emit({"type": "tool", "name": name, "args": tc, "result": r[:200]})
            all_results.append(f"[tool:{name}] {r[:2000]}")
            calls_made.append(name)

        if needs_break: break
        if all_results:
            combined = "\n".join(all_results)
            full += combined + "\n"
            msgs.append({"role":"assistant","content":f"(called: {', '.join(calls_made)})"})
            msgs.append({"role":"user","content":combined})
            total_tokens += len(combined) / 4

        if MAX_TOKENS and total_tokens > MAX_TOKENS:
            full += f"\n[tool: TOKEN_LIMIT — estimated {int(total_tokens)} tokens exceeded {MAX_TOKENS}]\n"
            break

    if session_id:
        try:
            old = load_session(session_id) or {}
            save_session(session_id, old.get("title", session_id), msgs[1:])
        except Exception as e:
            log.warning("Save session %s: %s", session_id, e)

    return full

# ─── API models ──────────────────────────────────────────
class ChatReq(BaseModel): messages: list; model: str = ""; session_id: str = ""
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
    return list_sessions_db()

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
                creationflags=subprocess.CREATE_NO_WINDOW,
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
    async def gen():
        # 1) live tool progress while the agent loop runs
        while True:
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.5)
                yield f"data: {json.dumps({'tool': ev})}\n\n"
            except asyncio.TimeoutError:
                if task.done():
                    while not q.empty():
                        yield f"data: {json.dumps({'tool': q.get_nowait()})}\n\n"
                    break
        # 2) final text stream
        try:
            full = await task
        except Exception as e:
            full = f"[Error: {e}]"
        if req.session_id and msgs:
            try: save_memory(req.session_id, msgs)
            except: pass
        for i in range(0, len(full), 3):
            chunk = full[i:i+3]
            if chunk.strip():
                yield f"data: {json.dumps({'text':chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

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

if __name__ == "__main__":
    main()
