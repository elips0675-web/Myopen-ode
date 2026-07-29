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
    """Resolve a path: absolute or relative to WORK_DIR."""
    p = Path(path)
    if p.is_absolute(): return p
    return WORK_DIR / path

# ─── tool definitions ────────────────────────────────────
SYSTEM_PROMPT = "CRITICAL: You are a coding AGENT with tools on Windows.\n\nWORKSPACE: " + str(WORK_DIR) + """ — project root.

RULES:
1. For complex tasks — FIRST call plan tool with steps, user confirms, then execute.
2. For simple tasks — call tool directly. Ask before destructive actions (write/edit/bash/commit/undo).
3. Your response MUST start with ```tool block if you need to do anything. NEVER describe tools.
4. NEVER write code blocks. ONLY ```tool blocks.

TOOLS:
```tool
{"tool": "plan", "steps": ["read config", "edit main.py", "verify", "commit"]}
```
```tool
{"tool": "read", "path": "..."}
```
```tool
{"tool": "list", "path": "..."}
```
```tool
{"tool": "bash", "cmd": "..."}
```
```tool
{"tool": "web", "url": "..."}
```
```tool
{"tool": "write", "path": "...", "content": "..."}
```
```tool
{"tool": "edit", "path": "...", "old": "...", "new": "..."}
```
```tool
{"tool": "glob", "pattern": "..."}
```
```tool
{"tool": "grep", "pattern": "...", "include": "..."}
```
```tool
{"tool": "diff"}
```
```tool
{"tool": "commit", "message": "..."}
```
```tool
{"tool": "undo", "path": "..."}
```
```tool
{"tool": "verify", "path": "..."}
```

Paths: use forward slashes. C:/Users/... works."""

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
    max_iter = 12
    max_time = 60.0  # total agent loop timeout in seconds
    start_time = __import__("time").time()
    retries = {}  # tool_name -> retry count

    for it in range(max_iter):
        if __import__("time").time() - start_time > max_time:
            full += "\n[tool: TIMEOUT — agent loop exceeded {}s]\n".format(int(max_time))
            break

        content = call_ollama(msgs)
        if not content:
            break

        m = tool_pat.search(content)
        bare = None
        if not m:
            for match in bare_tool_pat.finditer(content):
                try:
                    j = json.loads(match.group())
                    if "tool" in j and j["tool"] in ("read","write","edit","bash","glob","grep","list","web","diff","commit","undo","verify","plan"):
                        bare = match
                        break
                except: pass
            if bare:
                m = bare

        if not m:
            full += content
            break

        before = content[:m.start()].strip()
        if before:
            full += before + "\n"
            msgs.append({"role": "assistant", "content": before})

        try: raw_json = m.group(1).strip()
        except IndexError: raw_json = m.group(0).strip()

        tc = None
        parse_error = ""
        for attempt in range(3):
            try:
                tc = json.loads(raw_json)
                break
            except:
                import re as _re
                cleaned = _re.sub(r',\s*}', '}', raw_json)
                cleaned = _re.sub(r',\s*\]', ']', cleaned)
                cleaned = cleaned.replace("'", '"')
                cleaned = _re.sub(r'//.*?\n', '', cleaned)  # strip JS comments
                try:
                    tc = json.loads(cleaned)
                    break
                except Exception as e:
                    parse_error = str(e)
                    if attempt < 2:
                        raw_json = cleaned  # try again with cleaned version

        if tc is None:
            name_guess = "unknown"
            for guess in ("read","write","edit","bash","glob","grep","list","web","diff","commit","undo","verify","plan"):
                if guess in raw_json[:100].lower(): name_guess = guess; break
            retries[name_guess] = retries.get(name_guess, 0) + 1
            if retries[name_guess] >= 3:
                full += f"\n[tool: giving up on {name_guess} after 3 retries]\n"
                break
            full += f"\n[tool: parse error — {parse_error}]\n"
            msgs.append({"role": "assistant", "content": content})
            msgs.append({"role": "user", "content": f"JSON error: {parse_error}. Output ONLY: ```tool\n{{...}}\n``` Fix the JSON."})
            continue

        name = tc.pop("tool", "")
        if not name:
            full += "[tool: missing 'tool' key in JSON]"
            continue

        # plan tool — show plan to user, wait for confirmation
        if name == "plan":
            steps = tc.get("steps", [])
            plan_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
            full += f"\n[PLAN]\n{plan_text}\n\nReply 'yes' to execute plan.\n"
            msgs.append({"role": "assistant", "content": content})
            msgs.append({"role": "user", "content": f"Plan proposed:\n{plan_text}\nReply 'yes' to execute."})
            break

        # confirmation for destructive actions (only if no plan was shown)
        DESTRUCTIVE = ("write", "edit", "bash", "commit", "undo")
        if name in DESTRUCTIVE:
            last = msgs[-1]["content"].strip().lower() if msgs else ""
            if last in ("yes", "y", "go ahead", "да", "ok", "continue", "proceed", "do it"):
                result = execute_tool(name, tc)
                result_str = f"[tool:{name}] {result[:2000]}"
                full += result_str + "\n"
                msgs.append({"role": "assistant", "content": f"(called tool: {name})"})
                msgs.append({"role": "user", "content": result_str})
            else:
                ask_msg = f"Allow {name}?\nArgs: {json.dumps(tc, ensure_ascii=False)[:300]}\nReply 'yes' to proceed."
                full += f"\n[CONFIRM] {ask_msg}\n"
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": ask_msg})
                break
            continue

        result = execute_tool(name, tc)
        result_str = f"[tool:{name}] {result[:2000]}"
        full += result_str + "\n"
        msgs.append({"role": "assistant", "content": f"(called tool: {name})"})
        msgs.append({"role": "user", "content": result_str})

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
body{font-family:-apple-system,sans-serif;background:#f5f5f5;color:#1a1a1a;height:100vh;display:flex;flex-direction:column}
#bar{display:flex;align-items:center;padding:4px 10px;border-bottom:1px solid #ddd;background:#fff;gap:6px;flex-shrink:0;font-size:13px}
#bar .b{font-weight:700;color:#2563eb}
#bar select{font-size:11px;padding:1px 5px;border:1px solid #ccc;border-radius:3px}
#bar #prj{font-size:11px;color:#888;margin-left:auto}
#bar #st2{font-size:10px;color:#999;margin-left:8px}
#main{flex:1;display:flex;min-height:0}
#chat{flex:1;display:flex;flex-direction:column;min-width:0}
#msgs{flex:1;overflow-y:auto;padding:8px}
.msg{margin:5px 0;padding:7px 12px;border-radius:7px;font-size:13px;line-height:1.5;word-wrap:break-word}
.msg.u{background:#e8f0fe;margin-left:auto;border-bottom-right-radius:3px;max-width:88%}
.msg.a{background:#fff;margin-right:auto;border:1px solid #eee;border-bottom-left-radius:3px;max-width:88%}
.msg.t{font-size:11px;padding:3px 10px;margin:2px auto;text-align:center;max-width:none;border-radius:4px}
.msg.t.ok{background:#f0fdf4;color:#166534}
.msg.t.err{background:#fef2f2;color:#991b1b}
.msg.t.warn{background:#fffbeb;color:#92400e}
.msg.t.info{background:#eff6ff;color:#1e40af}
.msg.s{text-align:center;font-size:11px;color:#999;margin:3px 0;background:none!important;max-width:none}
.msg .l{font-size:10px;color:#999;margin-bottom:2px;font-weight:500}
.msg pre{background:#f8f9fa;padding:8px;border-radius:4px;overflow-x:auto;font-size:12px;margin:4px 0;border:1px solid #eee}
.msg code{background:#f0f0f0;padding:1px 3px;border-radius:2px;font-size:12px}
.msg pre code{background:none;padding:0;border:none}
.msg .dp{font-family:monospace;font-size:12px;line-height:1.4;white-space:pre-wrap;background:#f8f9fa;padding:6px;border-radius:4px;border:1px solid #eee;margin:4px 0}
.msg .dp .a{background:#dcfce7;color:#166534;display:block}
.msg .dp .d{background:#fce7f3;color:#991b1b;display:block}
.msg .dp .h{background:#f0f0f0;color:#666;display:block}
.msg .cn{font-size:11px;color:#2563eb;cursor:pointer;margin-top:2px;display:inline-block}
.msg .cn:hover{text-decoration:underline}
.sp{display:inline-block;width:10px;height:10px;border:2px solid #ddd;border-top-color:#2563eb;border-radius:50%;animation:s .5s infinite linear;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
#inp{display:flex;padding:6px 8px;border-top:1px solid #ddd;background:#fff;gap:6px;flex-shrink:0}
#inp textarea{flex:1;padding:7px;border:1px solid #ccc;border-radius:7px;resize:none;font-size:13px;outline:none;font-family:inherit;min-height:34px;max-height:90px}
#inp textarea:focus{border-color:#2563eb}
#inp button{background:#2563eb;color:#fff;border:none;border-radius:7px;padding:5px 16px;cursor:pointer;font-size:13px;font-weight:500;align-self:flex-end}
#inp button:hover{opacity:.85}
#inp button:disabled{opacity:.3}
#inp #cnl{background:#6b7280;display:none}
#inp #cnl:hover{opacity:.85}
#stat{height:17px;border-top:1px solid #ddd;background:#fff;font-size:10px;color:#999;padding:1px 10px;display:flex;align-items:center;gap:8px;flex-shrink:0}
#stat .g{width:6px;height:6px;border-radius:50%;background:#16a34a;display:inline-block}
#stat .r{width:6px;height:6px;border-radius:50%;background:#dc2626;display:inline-block}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#ddd;border-radius:3px}
</style></head><body>
<div id="bar"><span class="b">AI Coder</span><select id="chm"></select><span id="prj"></span><span id="st2"></span></div>
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
