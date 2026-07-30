#!/usr/bin/env python3
"""AI Coding Agent v2 — OpenCode Desktop alternative with DeepSeek support."""

import json, os, glob, webbrowser, re, time, logging, asyncio
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
    log.info("Switched project: %s → %s", old_wd.name, WORK_DIR.name)
    return True

# ─── sessions ────────────────────────────────────────────
SESSIONS_DIR = WORK_DIR / ".agent_sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

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
def run_agent_loop(msgs, session_id):
    msgs = summarize_context(msgs)
    full = ""
    tool_pat = re.compile('```(?:tool|json)\n(.*?)\n```', re.DOTALL)
    bare_tool_pat = re.compile(r'\{\s*"tool"\s*:\s*"[^"]+"\s*.*?\}', re.DOTALL)
    VALID_TOOLS = ("read","write","edit","bash","glob","grep","list","web","diff","commit","undo","verify","plan","search","websearch","question","skill","patch","task","todo","lsp")
    max_iter = int(os.environ.get("AGENT_MAX_ITER", "12"))
    max_time = float(os.environ.get("AGENT_TIMEOUT", "60.0"))
    start_time = time.time()
    total_tokens = sum(len(m.get("content", "")) / 4 for m in msgs)

    for it in range(max_iter):
        if time.time() - start_time > max_time:
            full += f"\n[tool: TIMEOUT — agent loop exceeded {int(max_time)}s]\n"
            break

        # Summarize context every 3 iterations to keep token usage in check
        if it > 0 and it % 3 == 0:
            msgs = summarize_context(msgs)

        current_model = PLANNER_MODEL if it == 0 else MODEL
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

        last_msg = msgs[-1]["content"].strip().lower() if msgs else ""
        if not tool_blocks and last_msg[:5] in ("yes","y","go a","да","ok","cont","proc","do i"):
            pn, pa = extract_pending_tool(msgs)
            if pn:
                log.info("Auto-exec pending %s after '%s'", pn, last_msg[:10])
                r = execute_tool(pn, pa)
                full += f"\n[tool:{pn}] {r[:2000]}\n"
                msgs.append({"role":"assistant","content":f"(auto-executed {pn})"})
                msgs.append({"role":"user","content":r[:2000]})
                continue

        if not tool_blocks:
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
                    all_results.append(f"[tool:{name}] {r[:2000]}")
                    calls_made.append(name)
                else:
                    ask = f"Allow {name}?\nArgs: {json.dumps(tc, ensure_ascii=False)[:300]}"
                    full += f"\n[CONFIRM] {ask}\nReply 'yes' to proceed.\n"
                    msgs.append({"role":"assistant","content":content})
                    hint = f"User must reply 'yes' to execute {name}."
                    msgs.append({"role":"system","content":hint})
                    msgs.append({"role":"user","content":ask})
                    needs_break=True; break
                continue
            r = execute_tool(name,tc)
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
        sf = SESSIONS_DIR / f"{session_id}.json"
        try:
            data = json.loads(sf.read_text()) if sf.exists() else {"title": session_id, "messages": []}
            data["messages"] = msgs[1:]
            data["updated"] = datetime.now().isoformat()
            sf.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        except Exception as e:
            log.warning("Save session %s: %s", session_id, e)

    return full

# ─── API models ──────────────────────────────────────────
class ChatReq(BaseModel): messages: list; model: str = ""; session_id: str = ""
class SessionReq(BaseModel): title: str = ""
class FileUploadReq(BaseModel): path: str = ""; content: str = ""
class ProjectReq(BaseModel): name: str = ""; path: str = ""
class ProjectSwitchReq(BaseModel): path: str = ""

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

@app.post("/api/upload")
async def upload_file(req: FileUploadReq):
    p = WORK_DIR / req.path if not os.path.isabs(req.path) else Path(req.path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(req.content, "utf-8")
    return {"ok": True, "path": req.path, "size": len(req.content)}

@app.get("/api/sessions")
def list_sessions():
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text())
            sessions.append({"id": f.stem, "title": data.get("title", f.stem),
                "updated": data.get("updated", ""), "messages": data.get("messages", [])})
        except Exception as e:
            log.warning("Bad session file %s: %s", f.name, e)
    return sessions

@app.post("/api/sessions")
def create_session(req: SessionReq):
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    data = {"title": req.title or f"Session {sid}", "messages": [], "updated": datetime.now().isoformat()}
    (SESSIONS_DIR / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return {"id": sid, "title": data["title"]}

@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    f = SESSIONS_DIR / f"{sid}.json"
    if not f.exists(): return {"error": "Not found"}
    return json.loads(f.read_text())

@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    f = SESSIONS_DIR / f"{sid}.json"
    if f.exists(): f.unlink()
    return {"ok": True}

@app.get("/api/sessions/{sid}/export")
def export_session(sid: str):
    f = SESSIONS_DIR / f"{sid}.json"
    if not f.exists(): return {"error": "Not found"}
    return JSONResponse(content=json.loads(f.read_text()))

@app.post("/api/sessions/import")
def import_session(req: ChatReq):
    data = json.loads(req.model_dump_json())
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    title = data.get("title", f"Imported {sid}")
    messages = data.get("messages", data.get("content", []))
    if isinstance(messages, str):
        try: messages = json.loads(messages)
        except: messages = []
    sf = SESSIONS_DIR / f"{sid}.json"
    sf.write_text(json.dumps({"title": title, "messages": messages, "updated": datetime.now().isoformat()}, ensure_ascii=False), "utf-8")
    return {"id": sid, "title": title}

@app.post("/api/chat")
async def chat(req: ChatReq):
    session_msgs = []
    if req.session_id:
        sf = SESSIONS_DIR / f"{req.session_id}.json"
        if sf.exists():
            try: session_msgs = json.loads(sf.read_text()).get("messages", [])
            except: pass
    mem_text = memory_prompt()
    sys_content = SYSTEM_PROMPT + mem_text
    msgs = [{"role": "system", "content": sys_content}] + session_msgs + req.messages
    full = await asyncio.to_thread(run_agent_loop, msgs, req.session_id)
    if req.session_id and msgs:
        try: save_memory(req.session_id, msgs)
        except: pass
    async def gen():
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
