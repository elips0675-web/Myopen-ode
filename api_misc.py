"""Misc API routes: stats, health, models, projects, terminal, skills, plugins
(extracted from agent.py)."""
import asyncio, json, os, subprocess, time
from pathlib import Path
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from core.container import work_dir
from agent import (MODEL, PLANNER_MODEL, OLLAMA_URL, load_projects, save_projects,
                   switch_project, list_sessions_db, ProjectReq, ProjectSwitchReq,
                   TerminalReq)
from tools import TOOL_STATS
import requests

router = APIRouter()
_SERVER_START = time.time()
_UPDATE_CACHE = {"at": 0, "data": None}
_VRAM_CACHE = {"at": 0, "data": None}


def _vram_info():
    """Stage 29: GPU VRAM via nvidia-smi, cached 10s; used by /api/vram and
    /health so the UI can show a live indicator."""
    now = time.time()
    if _VRAM_CACHE["data"] and now - _VRAM_CACHE["at"] < 10:
        return _VRAM_CACHE["data"]
    data = {"total_mb": 0, "used_mb": 0, "free_mb": 0, "ok": False}
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        total, used = r.stdout.strip().split(",")[:2]
        total, used = int(total), int(used)
        data = {"total_mb": total, "used_mb": used,
                "free_mb": max(0, total - used), "ok": True}
    except Exception:
        pass
    _VRAM_CACHE.update({"at": now, "data": data})
    return data


@router.get("/api/vram")
def vram_info():
    """GPU VRAM usage for the UI indicator (cached 10s; ok=False without
    nvidia-smi, e.g. iGPU-only machines)."""
    return _vram_info()

@router.get("/api/stats")
def tool_stats():
    """Per-tool call/error counters (diagnostics; shows repeated model failures)."""
    return TOOL_STATS

@router.get("/api/rag/status")
def rag_status():
    """RAG indexing progress (phase, files done/total, chunks) for the UI."""
    from rag import RAG_STATUS
    return dict(RAG_STATUS)

@router.get("/api/audit")
def audit_log(limit: str = "50"):
    """Last N lines of .agent_audit.log (action audit view in the UI)."""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, 500))
    try:
        lines = (work_dir() / ".agent_audit.log").read_text("utf-8", errors="ignore").splitlines()
        return {"lines": lines[-n:]}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/subagents/audit")
def subagents_audit(limit: str = "50"):
    """Stage 67: last N lines of .agent_subagent_audit.log (subagent trail)."""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, 500))
    try:
        lines = (work_dir() / ".agent_subagent_audit.log").read_text("utf-8", errors="ignore").splitlines()
        return {"lines": lines[-n:]}
    except Exception as e:
        return {"error": str(e)}

@router.get("/health")
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
        "workspace": str(work_dir()),
        "sessions": sessions,
        "rag_chunks": len(RAG_CHUNKS or []),
        "rag_embeddings": len(RAG_INDEX or []),
        "vram": _vram_info(),
        "uptime_s": round(time.time() - _SERVER_START, 1),
    }

@router.get("/api/update")
def update_check():
    """Check for new versions (git origin/master). Cached for 1 hour; graceful
    when offline or not a git checkout."""
    now = time.time()
    if _UPDATE_CACHE["data"] and now - _UPDATE_CACHE["at"] < 3600:
        return _UPDATE_CACHE["data"]
    try:
        cur = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(work_dir()),
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10).stdout.strip()
        remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/master"],
                                cwd=str(work_dir()), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
        latest = remote.stdout.split()[0][:7] if remote.stdout.split() else ""
        behind = 0
        if latest:
            bc = subprocess.run(["git", "rev-list", "--count", "HEAD..origin/master"],
                                cwd=str(work_dir()), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
            try: behind = int(bc.stdout.strip() or 0)
            except ValueError: pass
        data = {"ok": True, "current": cur, "latest": latest,
                "behind": behind, "has_update": bool(latest) and behind > 0}
    except Exception as e:
        data = {"ok": False, "error": str(e)[:120]}
    _UPDATE_CACHE.update({"at": now, "data": data})
    return data

@router.get("/api/models")
def list_models():
    try: return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags",timeout=5).json().get("models",[])]
    except: return [MODEL]

@router.post("/api/models/pull")
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

@router.get("/api/models/pull/stream")
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

@router.delete("/api/models/{name}")
def delete_model(name: str):
    try:
        r = requests.delete(f"{OLLAMA_URL}/api/delete", json={"name": name}, timeout=30)
        return {"status": "deleted" if r.ok else r.text}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/project")
def get_project(): return {"name": work_dir().name, "path": str(work_dir())}

@router.get("/api/projects")
def list_projects():
    return load_projects()

@router.post("/api/projects")
def add_project(req: ProjectReq):
    projects = load_projects()
    for p in projects: p["active"] = False
    path = req.path or str(work_dir())
    projects.append({"name": req.name or Path(path).name, "path": path, "active": True})
    save_projects(projects)
    switch_project(path)
    return {"ok": True, "projects": projects}

@router.post("/api/projects/switch")
def switch_project_api(req: ProjectSwitchReq):
    path = req.path
    if not path: return {"error": "path required"}
    projects = load_projects()
    for p in projects:
        p["active"] = (p["path"] == path)
    save_projects(projects)
    switch_project(path)
    return {"ok": True, "project": {"name": work_dir().name, "path": str(work_dir())}}

@router.delete("/api/projects/{idx}")
def delete_project_api(idx: int):
    projects = load_projects()
    if idx < 0 or idx >= len(projects): return {"error": "Invalid index"}
    removed = projects.pop(idx)
    if removed.get("active") and projects:
        projects[0]["active"] = True
        switch_project(projects[0]["path"])
    save_projects(projects)
    return {"ok": True}

@router.get("/api/task/{agent_type}")
async def run_task(agent_type: str, prompt: str = ""):
    if not prompt: return {"error": "prompt required"}
    from tools import SUBAGENT_PROMPTS, call_ollama, PLANNER_MODEL
    sub_prompt = SUBAGENT_PROMPTS.get(agent_type, SUBAGENT_PROMPTS["general"])
    msgs = [{"role": "system", "content": sub_prompt}, {"role": "user", "content": prompt}]
    result, _ = call_ollama(msgs, PLANNER_MODEL)
    return {"result": result[:3000]}

@router.get("/api/subagents")
def list_subagents():
    """Stage 61: subagent catalogue (markers + descriptions) for UI/API."""
    from tools import SUBAGENT_PROMPTS, SUBAGENT_DESCS
    return [{"name": n, "marker": "@" + n, "desc": SUBAGENT_DESCS.get(n, ""),
             "tools": _subagent_tool_hint(n)} for n in SUBAGENT_PROMPTS]

def _subagent_tool_hint(name):
    from tools import SUBAGENT_PROMPTS
    import re as _re
    m = _re.search(r"can ONLY use: ([^\n]+)", SUBAGENT_PROMPTS[name])
    return m.group(1) if m else "all tools"

@router.get("/api/plugins")
def list_plugins():
    from tools import PLUGINS
    return [{"name": n, "tools": list(p["tools"].keys())} for n, p in PLUGINS.items()]

@router.get("/api/skills")
def list_skills():
    skills_dir = work_dir() / ".agent_skills"
    if not skills_dir.exists():
        skills_dir.mkdir(exist_ok=True)
    skills = []
    for f in sorted(skills_dir.glob("*.md")):
        try:
            content = f.read_text("utf-8", errors="ignore")[:500]
            skills.append({"name": f.stem, "path": str(f.relative_to(work_dir())), "preview": content[:200]})
        except: pass
    return skills

TERMINAL_PROCS = {}

@router.post("/api/terminal")
async def terminal(req: TerminalReq):
    """Run a shell command, streaming output via SSE."""
    cmd = req.cmd.strip()
    if not cmd:
        return {"error": "Empty command"}
    async def gen():
        try:
            proc = subprocess.Popen(
                cmd, shell=True, cwd=req.cwd or work_dir(),
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

@router.post("/api/terminal/kill")
def terminal_kill():
    n = 0
    for proc in list(TERMINAL_PROCS.values()):
        try:
            proc.kill()
            n += 1
        except: pass
    return {"killed": n}

@router.websocket("/ws/term")
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
                shell = PtyShell(m.get("cmd") or None, cwd=m.get("cwd") or work_dir(),
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

@router.post("/api/lsp/completion")
def lsp_completion(req: dict):
    """Editor autocomplete: LSP first, token-based fallback if no language server."""
    path = req.get("path", "")
    text = req.get("text")
    line = int(req.get("line", 0))
    character = int(req.get("character", 0))
    try:
        from lsp import LSPClient, token_completions
        client = LSPClient(work_dir())
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
