#!/usr/bin/env python3
"""AI Coding Agent - full-featured."""

import json, os, subprocess, glob, webbrowser, re, shutil, hashlib, textwrap, urllib.parse
from pathlib import Path
from datetime import datetime
import requests, uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AI_MODEL", "qwen2.5-coder:7b")
WORK_DIR = Path(os.environ.get("WORK_DIR", "E:\\My OpenCode"))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── file versioning (for undo) ──────────────────────────
BACKUP_DIR = WORK_DIR / ".agent_backups"
BACKUP_DIR.mkdir(exist_ok=True)
MAX_BACKUPS = 50

def backup(path):
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

# ─── git helpers ──────────────────────────────────────────
def git(*args):
    try:
        r = subprocess.run(["git"] + list(args), cwd=str(WORK_DIR), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or r.stderr.strip()
    except: return "(git not available)"

# ─── verify helpers ───────────────────────────────────────
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

# ─── path resolver ────────────────────────────────────────
def resolve(path):
    p = Path(path)
    if p.is_absolute(): return p
    return WORK_DIR / path

# ─── RAG / embeddings ────────────────────────────────────
RAG_INDEX = None
RAG_CHUNKS = []
RAG_DIRTY = True

def rag_index():
    global RAG_INDEX, RAG_CHUNKS, RAG_DIRTY
    if not RAG_DIRTY and RAG_INDEX: return
    RAG_CHUNKS = []
    files = list(glob.glob(str(WORK_DIR / "**/*.py"), recursive=True))[:200]
    files += list(glob.glob(str(WORK_DIR / "**/*.js"), recursive=True))[:100]
    files += list(glob.glob(str(WORK_DIR / "**/*.ts"), recursive=True))[:100]
    files += list(glob.glob(str(WORK_DIR / "**/*.json"), recursive=True))[:50]
    files += list(glob.glob(str(WORK_DIR / "**/*.md"), recursive=True))[:50]
    for fp in files:
        p = Path(fp)
        if ".git" in p.parts or "__pycache__" in p.parts or ".agent_backups" in p.parts: continue
        try:
            text = p.read_text("utf-8", errors="ignore")
            rel = str(p.relative_to(WORK_DIR))
            # split into chunks by function/class boundaries
            chunks = []
            parts = text.split("\n")
            current = []; current_start = 0
            for i, line in enumerate(parts):
                if line.startswith(("def ", "class ", "async def ")) and len(current) > 5:
                    chunks.append(("\n".join(current), rel, current_start))
                    current = [line]; current_start = i
                else:
                    current.append(line)
            if current:
                chunks.append(("\n".join(current), rel, current_start))
            for chunk_text, chunk_file, chunk_line in chunks:
                RAG_CHUNKS.append({"text": chunk_text[:500], "file": chunk_file, "line": chunk_line})
        except: pass

    if not RAG_CHUNKS: return

    # embed all chunks using Ollama
    try:
        texts = [c["text"] for c in RAG_CHUNKS]
        r = requests.post(f"{OLLAMA}/api/embed", json={
            "model": "qwen2.5-coder:1.5b", "input": texts
        }, timeout=120)
        data = r.json()
        if "embeddings" in data:
            RAG_INDEX = data["embeddings"]
            RAG_DIRTY = False
    except: pass

def _cos_sim(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = sum(x*x for x in a)**0.5
    nb = sum(y*y for y in b)**0.5
    return dot / (na * nb + 1e-10)

def rag_search(query, top_k=5):
    rag_index()
    if RAG_INDEX is None or not RAG_CHUNKS: return "RAG not available"
    try:
        r = requests.post(f"{OLLAMA}/api/embed", json={
            "model": "qwen2.5-coder:1.5b", "input": [query]
        }, timeout=30)
        q_emb = r.json().get("embeddings", [[]])[0]
        if not q_emb: return "No embedding for query"
        scores = [(_cos_sim(q_emb, emb), i) for i, emb in enumerate(RAG_INDEX)]
        scores.sort(key=lambda x: -x[0])
        results = []
        for score, idx in scores[:top_k]:
            c = RAG_CHUNKS[idx]
            results.append(f"[{score:.2f}] {c['file']}:{c['line']}\n{c['text'][:300]}")
        return "\n---\n".join(results)
    except Exception as e:
        return f"RAG search error: {e}"

# ─── tool schema validation ──────────────────────────────
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
}

def validate_tool(tc):
    name = tc.get("tool", "")
    schema = TOOL_SCHEMAS.get(name)
    if not schema: return f"Unknown tool '{name}'"
    missing = [k for k in schema.get("required", []) if k not in tc]
    if missing: return f"Missing required fields: {', '.join(missing)} in {name}"
    extra = [k for k in tc if k not in ("tool", *schema.get("required", []), *schema.get("optional", []),
              "old","new","content","path","cmd","pattern","include","url","steps","message","cwd")]
    # type check common fields
    if "path" in tc and not isinstance(tc["path"], str): return "path must be string"
    if "content" in tc and not isinstance(tc["content"], str): return "content must be string"
    return ""

# ─── tool definitions ────────────────────────────────────
SYSTEM_PROMPT = "CRITICAL: You are a coding AGENT with tools on Windows.\n\nWORKSPACE: " + str(WORK_DIR) + """ — project root.

RULES:
1. Complex tasks: call plan FIRST with steps, user confirms, then execute.
2. Simple tasks: call tool directly. Ask before write/edit/bash/commit/undo.
3. Your response MUST start with a ```tool block. NEVER describe tools.
4. NEVER write code blocks. ONLY ```tool blocks.
5. Every tool call MUST include ALL required fields. Missing fields will be rejected.

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

Paths: forward slashes. C:/Users/... or relative to workspace.
Search: semantic code search — type what you're looking for in plain words."""

def call_ollama(messages):
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json={
            "model": MODEL, "messages": [m for m in messages if m.get("content")],
            "stream": False, "keep_alive": -1,
            "options": {"temperature": 0.2, "num_predict": 4096, "num_ctx": 32768}
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        msg = data.get("message", {}).get("content", "")
        return msg if msg else "No response from model"
    except Exception as e:
        return f"[Error: {e}]"

def execute_tool(name, args):
    try:
        if name == "read":
            p = args["path"]
            if p.startswith(("http://", "https://")):
                try:
                    r = requests.get(p, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                    return r.text[:5000]
                except Exception as e: return f"Error fetching URL: {e}"
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
            cwd = resolve(args.get("cwd", ".")) if args.get("cwd") else WORK_DIR
            r = subprocess.run(args["cmd"], shell=True, cwd=str(cwd) if cwd else str(WORK_DIR), capture_output=True, text=True, timeout=60)
            return ((r.stdout or "")[-3000:] + ("\nSTDERR:\n" + (r.stderr or "")[-1000:] if r.stderr else ""))
        elif name == "glob":
            pattern = args["pattern"]
            base = Path(args.get("cwd", ".")) if args.get("cwd") else WORK_DIR
            if not base.is_absolute():
                if "\\" in pattern or pattern.startswith("/") or ":" in pattern:
                    p = Path(pattern)
                    if p.is_absolute():
                        base = p.root; pattern = str(p.relative_to(p.root))
            fs = list(glob.glob(str(base / pattern), recursive=True))[:60]
            return "\n".join(fs) if fs else "No matches"
        elif name == "grep":
            pat, inc = args["pattern"], args.get("include", "*")
            cwd = args.get("cwd", str(WORK_DIR))
            r = subprocess.run(f'rg -n "{pat}" --glob "{inc}"', shell=True, cwd=cwd, capture_output=True, text=True, timeout=30)
            return "\n".join(r.stdout.split("\n")[:60]) or "No matches"
        elif name == "list":
            p = resolve(args.get("path", "."))
            items = [f"{'[DIR]' if x.is_dir() else '     '} {x.name}" for x in sorted(p.iterdir())]
            return "\n".join(items) if items else "(empty)"
        elif name == "diff":
            return git("diff", "--stat") + "\n\n" + git("diff")[:3000]
        elif name == "commit":
            git("add", "-A"); return git("commit", "-m", args.get("message", "update"))
        elif name == "undo":
            return undo(args.get("path", ""))
        elif name == "verify":
            path = args.get("path", "")
            return verify_file(path) if path else "No path specified"
        elif name == "search":
            return rag_search(args.get("query", ""), args.get("top_k", 5))
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"

# ─── context management ──────────────────────────────────
def summarize_context(msgs):
    """Summarize old messages when context gets too long."""
    total = sum(len(m.get("content","")) for m in msgs)
    if total < 4000: return msgs  # no need to summarize

    keep = msgs[:1]  # system prompt
    # keep the last user+assistant exchange
    tail = msgs[-6:] if len(msgs) > 6 else msgs[1:]
    to_summarize = msgs[1:-6] if len(msgs) > 6 else []

    if to_summarize:
        text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in to_summarize)
        prompt = f"Summarize this conversation in 2-3 sentences:\n\n{text[:1500]}"
        try:
            r = requests.post(f"{OLLAMA}/api/generate", json={
                "model": "qwen2.5-coder:1.5b", "prompt": prompt,
                "stream": False, "options": {"temperature": 0.1, "num_predict": 256}
            }, timeout=30)
            summary = r.json().get("response", "")
            if summary:
                keep.append({"role": "system", "content": f"[Summary of previous conversation]: {summary[:500]}"})
        except: pass

    keep.extend(tail)
    return keep

class ChatReq(BaseModel): messages: list; model: str = ""

@app.get("/")
def index(): return HTMLResponse(HTML)

@app.post("/api/chat")
def chat(req: ChatReq):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + req.messages
    msgs = summarize_context(msgs)
    full = ""
    tool_pat = re.compile('```(?:tool|json)\n(.*?)\n```', re.DOTALL)
    bare_tool_pat = re.compile(r'\{\s*"tool"\s*:\s*"[^"]+"\s*.*?\}', re.DOTALL)
    VALID_TOOLS = ("read","write","edit","bash","glob","grep","list","web","diff","commit","undo","verify","plan","search")
    max_iter = 12
    max_time = 60.0
    start_time = __import__("time").time()
    retries = {}  # tool_name -> retry count

    for it in range(max_iter):
        if __import__("time").time() - start_time > max_time:
            full += "\n[tool: TIMEOUT — agent loop exceeded {}s]\n".format(int(max_time))
            break

        content = call_ollama(msgs)
        if not content:
            break

        # find ALL tool blocks in this response
        tool_blocks = []
        for m in tool_pat.finditer(content):
            raw = m.group(1).strip()
            try: j = json.loads(raw); tool_blocks.append((m, raw, j))
            except:
                try: j = json.loads(raw.replace("'", '"')); tool_blocks.append((m, raw, j))
                except: pass

        # also find bare JSON tool blocks
        if not tool_blocks:
            for match in bare_tool_pat.finditer(content):
                try:
                    j = json.loads(match.group())
                    if "tool" in j and j["tool"] in VALID_TOOLS:
                        tool_blocks.append((match, match.group(), j))
                        break
                except: pass

        if not tool_blocks:
            full += content
            break

        # text before first tool block = assistant reply
        before = content[:tool_blocks[0][0].start()].strip()
        if before:
            full += before + "\n"
            msgs.append({"role": "assistant", "content": before})

        # execute all tool blocks (until one needs confirmation)
        all_results = []
        calls_made = []
        needs_break = False
        DESTRUCTIVE = ("write", "edit", "bash", "commit", "undo")
        for idx, (match, raw_json, tc) in enumerate(tool_blocks):
            name = tc.get("tool", "")
            raw_tc = dict(tc)  # keep original for logging
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
                plan_text = "\n".join(f"  {i+1}. {s}" for i,s in enumerate(tc.get("steps",[])))
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

    def gen():
        for chunk in [full[i:i+3] for i in range(0, len(full), 3)]:
            if chunk.strip():
                yield f"data: {json.dumps({'text':chunk})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.get("/api/models")
def list_models():
    try: return [m["name"] for m in requests.get(f"{OLLAMA}/api/tags",timeout=5).json().get("models",[])]
    except: return [MODEL]

@app.get("/api/project")
def get_project(): return {"name": WORK_DIR.name, "path": str(WORK_DIR)}

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>AI Coder</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f5f5f5;--fg:#1a1a1a;--bar-bg:#fff;--bar-border:#ddd;--msg-u:#e8f0fe;--msg-a:#fff;--msg-a-border:#eee;--pre-bg:#f8f9fa;--code-bg:#f0f0f0;--inp-bg:#fff;--inp-border:#ccc;--btn:#2563eb;--cnl-btn:#6b7280;--stat-bg:#fff;--st-c:#999;--diff-add:#dcfce7;--diff-add-fg:#166534;--diff-del:#fce7f3;--diff-del-fg:#991b1b;--diff-hdr:#f0f0f0;--plan:#eff6ff;--plan-fg:#1e40af;--sp:10px;--s:#2563eb}
body.dark{--bg:#1a1a2e;--fg:#e0e0e0;--bar-bg:#16213e;--bar-border:#2a2a4a;--msg-u:#1e3a5f;--msg-a:#16213e;--msg-a-border:#2a2a4a;--pre-bg:#0f3460;--code-bg:#0f3460;--inp-bg:#16213e;--inp-border:#2a2a4a;--btn:#0f3460;--cnl-btn:#533483;--stat-bg:#16213e;--st-c:#888;--diff-add:#064e3b;--diff-add-fg:#6ee7b7;--diff-del:#7f1d1d;--diff-del-fg:#fca5a5;--diff-hdr:#374151;--plan:#1e3a5f;--plan-fg:#93c5fd;--sp:5px}
body{font-family:-apple-system,sans-serif;background:var(--bg);color:var(--fg);height:100vh;display:flex;flex-direction:column}
#bar{display:flex;align-items:center;padding:4px 10px;border-bottom:1px solid var(--bar-border);background:var(--bar-bg);gap:6px;flex-shrink:0;font-size:13px}
#bar .b{font-weight:700;color:var(--btn)}
#bar select{font-size:11px;padding:1px 5px;border:1px solid var(--inp-border);border-radius:3px;background:var(--inp-bg);color:var(--fg)}
#bar #prj{font-size:11px;color:var(--st-c);margin-left:auto}
#bar #st2{font-size:10px;color:var(--st-c);margin-left:8px}
#bar #tm{font-size:10px;color:var(--st-c);cursor:pointer;margin-left:6px;padding:0 4px;border:1px solid var(--bar-border);border-radius:3px}
#main{flex:1;display:flex;min-height:0}
#chat{flex:1;display:flex;flex-direction:column;min-width:0}
#msgs{flex:1;overflow-y:auto;padding:8px}
.msg{margin:5px 0;padding:7px 12px;border-radius:7px;font-size:13px;line-height:1.5;word-wrap:break-word}
.msg.u{background:var(--msg-u);margin-left:auto;border-bottom-right-radius:3px;max-width:88%}
.msg.a{background:var(--msg-a);margin-right:auto;border:1px solid var(--msg-a-border);border-bottom-left-radius:3px;max-width:88%}
.msg.t{font-size:11px;padding:3px 10px;margin:2px auto;text-align:center;max-width:none;border-radius:4px}
.msg.t.ok{background:var(--diff-add);color:var(--diff-add-fg)}
.msg.t.err{background:var(--diff-del);color:var(--diff-del-fg)}
.msg.t.warn{background:#fffbeb;color:#92400e}
.msg.t.info{background:var(--plan);color:var(--plan-fg)}
.msg.s{text-align:center;font-size:11px;color:var(--st-c);margin:3px 0;background:none!important;max-width:none}
.msg pre{background:var(--pre-bg);padding:8px;border-radius:4px;overflow-x:auto;font-size:12px;margin:4px 0;border:1px solid var(--msg-a-border)}
.msg code{background:var(--code-bg);padding:1px 3px;border-radius:2px;font-size:12px}
.msg pre code{background:none;padding:0;border:none}
.msg .dp{font-family:monospace;font-size:12px;line-height:1.4;white-space:pre-wrap;background:var(--pre-bg);padding:6px;border-radius:4px;border:1px solid var(--msg-a-border);margin:4px 0}
.msg .dp .a{background:var(--diff-add);color:var(--diff-add-fg);display:block}
.msg .dp .d{background:var(--diff-del);color:var(--diff-del-fg);display:block}
.msg .dp .h{background:var(--diff-hdr);color:var(--st-c);display:block}
.sp{display:inline-block;width:var(--sp);height:var(--sp);border:2px solid var(--msg-a-border);border-top-color:var(--s);border-radius:50%;animation:s .5s infinite linear;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
#inp{display:flex;padding:6px 8px;border-top:1px solid var(--bar-border);background:var(--inp-bg);gap:6px;flex-shrink:0}
#inp textarea{flex:1;padding:7px;border:1px solid var(--inp-border);border-radius:7px;resize:none;font-size:13px;outline:none;font-family:inherit;min-height:34px;max-height:90px;background:var(--msg-a);color:var(--fg)}
#inp textarea:focus{border-color:var(--btn)}
#inp button{background:var(--btn);color:#fff;border:none;border-radius:7px;padding:5px 16px;cursor:pointer;font-size:13px;font-weight:500;align-self:flex-end}
#inp button:hover{opacity:.85}
#inp button:disabled{opacity:.3}
#inp #cnl{background:var(--cnl-btn);display:none}
#stat{height:17px;border-top:1px solid var(--bar-border);background:var(--stat-bg);font-size:10px;color:var(--st-c);padding:1px 10px;display:flex;align-items:center;gap:8px;flex-shrink:0}
#stat .g{width:6px;height:6px;border-radius:50%;background:#16a34a;display:inline-block}
#stat .r{width:6px;height:6px;border-radius:50%;background:#dc2626;display:inline-block}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:var(--bar-border);border-radius:3px}
</style></head><body>
<div id="bar"><span class="b">AI Coder</span><select id="chm"></select><span id="tm" onclick="toggleTheme()">&#9790;</span><span id="prj"></span><span id="st2"></span></div>
<div id="main"><div id="chat">
<div id="msgs">
<div class="msg s">Agent ready. Try: "list project" or "read agent.py"</div>
</div>
<div id="inp">
<textarea id="ta" rows="1" placeholder="ask something..."></textarea>
<button id="cnl" onclick="cancel()">X</button>
<button id="snd" onclick="send()">OK</button>
</div>
</div></div>
<div id="stat"><span id="old"></span><span id="ols">Ollama...</span></div>
<script>
var A=window.location.origin,ms=[],sd=0,ac=null;
function $(i){return document.getElementById(i)}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function fmtDiff(t){
  var h='<div class="dp">';
  t.split('\n').forEach(function(l){
    if(l.startsWith('+')) h+='<span class="a">'+esc(l)+'</span>';
    else if(l.startsWith('-')) h+='<span class="d">'+esc(l)+'</span>';
    else if(l.startsWith('@@')) h+='<span class="h">'+esc(l)+'</span>';
    else h+=esc(l)+'\n';
  });
  return h+'</div>';
}
function fm(t){
  var h=esc(t);
  // diff blocks
  h=h.replace(/```diff\n?([\s\S]*?)```/g,function(_,c){return fmtDiff(c)});
  // code blocks
  h=h.replace(/```(\w*)\n?([\s\S]*?)```/g,'<pre><code>$2</code></pre>');
  h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
  // confirm/plan/tool markers
  h=h.replace(/\[CONFIRM\]/g,'<b>[CONFIRM]</b>');
  h=h.replace(/\[PLAN\]/g,'<b>[PLAN]</b>');
  h=h.replace(/\[tool:(\w+)\]/g,'<b>[tool:$1]</b>');
  return h.replace(/\n/g,'<br>');
}
function ah(){var e=$('ta');e.style.height='auto';e.style.height=Math.min(e.scrollHeight,90)+'px'}
function am(r,t,c){
  var m=document.createElement('div');m.className='msg '+r;
  var b=document.createElement('div');b.innerHTML=t;m.appendChild(b);
  $('msgs').appendChild(m);m.scrollIntoView({behavior:'smooth',block:'end'});return b
}
function cancel(){if(ac){ac.abort();sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent='cancelled'}}
function init(){
  fetch(A+'/api/models').then(function(r){return r.json()}).then(function(ms){$('chm').innerHTML=ms.map(function(m){return '<option>'+m+'</option>'}).join('')}).catch(function(){});
  fetch(A+'/api/project').then(function(r){return r.json()}).then(function(p){$('prj').textContent=p.name}).catch(function(){});
  cl();$('ta').focus()
}
function cl(){fetch(A+'/api/models').then(function(){$('old').className='g';$('ols').textContent='Ollama OK'}).catch(function(){$('old').className='r';$('ols').textContent='Ollama -';setTimeout(cl,3000)})}
function toggleTheme(){document.body.classList.toggle('dark');localStorage.setItem('theme',document.body.classList.contains('dark')?'dark':'light')}
if(localStorage.getItem('theme')=='dark')document.body.classList.add('dark')
function send(){
  var ta=$('ta'),txt=ta.value.trim();if(!txt||sd)return;ta.value='';ah();
  am('u',fm(txt));ms.push({role:'user',content:txt});
  var m=$('chm').value||'qwen2.5-coder:7b';sd=1;$('snd').disabled=1;$('cnl').style.display='inline-block';ac=new AbortController();
  var fl='',be=am('a','<span class="sp"></span>');$('st2').textContent='thinking...';
  fetch(A+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({model:m,messages:ms}),signal:ac.signal})
  .then(function(r){if(!r.ok)throw Error(r.status);
    var rd=r.body.getReader(),dc=new TextDecoder(),bf='';
    (function rd2(){rd.read().then(function(v){
      if(v.done){ms.push({role:'assistant',content:fl});be.innerHTML=fm(fl)||'(empty)';sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent='';return}
      bf+=dc.decode(v.value,{stream:1});var ls=bf.split('\n');bf=ls.pop()||'';
      ls.forEach(function(l){if(l.startsWith('data: ')){try{var d=JSON.parse(l.slice(6));if(d.text)fl+=d.text}catch(e){}}});
      be.innerHTML=fm(fl)||'<span class="sp"></span>';rd2()
    }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent=''})})()
  }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent=''})
}
$('ta').addEventListener('keydown',function(e){if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}});
$('ta').addEventListener('input',ah);init();
</script>
</body></html>"""

def main():
    port = int(os.environ.get("PORT", "8765"))
    url = f"http://localhost:{port}"
    print(f"\n  AI Coder Agent: {url}")
    print(f"  Project: {WORK_DIR.name}")
    print(f"  Model: {MODEL}")
    print(f"  Tools: read write edit bash glob grep diff commit undo verify")
    print(f"  Ctrl+C to exit\n")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

if __name__ == "__main__":
    main()
