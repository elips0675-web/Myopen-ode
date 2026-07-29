#!/usr/bin/env python3
"""AI Coding Agent - full-featured."""

import json, os, subprocess, glob, webbrowser, re, shutil, hashlib, textwrap
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
    p = WORK_DIR / path
    if p.exists():
        b = BACKUP_DIR / path.replace("\\", "_").replace("/", "_") / datetime.now().strftime("%H%M%S_%f")
        b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, b)
        # cleanup old backups
        versions = sorted(b.parent.iterdir())
        for v in versions[:-MAX_BACKUPS]:
            v.unlink()

def undo(path):
    bd = BACKUP_DIR / path.replace("\\", "_").replace("/", "_")
    versions = sorted(bd.iterdir()) if bd.exists() else []
    if versions:
        shutil.copy2(versions[-1], WORK_DIR / path)
        versions[-1].unlink()
        return f"Undone: {path} restored to previous version"
    return f"No backup for {path}"

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
            fcmd = cmd.replace("{file}", str(WORK_DIR / path))
            r = subprocess.run(fcmd, shell=True, capture_output=True, text=True, timeout=15)
            return r.stdout.strip()[:1000] or r.stderr.strip()[:1000]
    return ""

# ─── tool definitions ────────────────────────────────────
SYSTEM_PROMPT = """You are a coding agent. Your source code lives in agent.py — when you read it, you are reading yourself. You are an AI running locally via Ollama.

Tools: read, write, edit, bash, glob, grep, list, diff, commit, undo, verify.

You NEVER write Python/shell code to simulate tools. You ONLY output tool JSON wrapped in ```tool blocks.

FORMAT:
```tool
{"tool": "TOOLNAME", ...args}
```

Read before edit. Verify after edit. Commit changes. Respond in user's language briefly.

User: "read agent.py"
Assistant:
```tool
{"tool": "read", "path": "agent.py"}
```"""

def call_ollama(messages):
    try:
        r = requests.post(f"{OLLAMA}/api/chat", json={
            "model": MODEL, "messages": [m for m in messages if m.get("content")],
            "stream": False, "keep_alive": -1,
            "options": {"temperature": 0.2, "num_predict": 4096, "num_ctx": 8192}
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
            p = WORK_DIR / args["path"]
            if not p.exists(): return f"Error: {args['path']} not found"
            return p.read_text("utf-8")
        elif name == "write":
            p = WORK_DIR / args["path"]
            backup(str(p.relative_to(WORK_DIR)))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"], "utf-8")
            v = verify_file(str(p.relative_to(WORK_DIR)))
            msg = f"Written {len(args['content'])}b to {args['path']}"
            if v: msg += f"\nVerify: {v[:500]}"
            return msg
        elif name == "edit":
            p = WORK_DIR / args["path"]
            if not p.exists(): return f"Error: {args['path']} not found"
            old = args.get("old", "")
            new = args.get("new", "")
            content = p.read_text("utf-8")
            if old not in content:
                return f"Error: text not found in {args['path']}"
            backup(str(p.relative_to(WORK_DIR)))
            p.write_text(content.replace(old, new), "utf-8")
            v = verify_file(str(p.relative_to(WORK_DIR)))
            count = content.count(old)
            msg = f"Replaced {count} occurrence(s) in {args['path']}"
            if v: msg += f"\nVerify: {v[:500]}"
            return msg
        elif name == "bash":
            r = subprocess.run(args["cmd"], shell=True, cwd=str(WORK_DIR), capture_output=True, text=True, timeout=60)
            out = (r.stdout or "")[-3000:]
            err = (r.stderr or "")[-1000:]
            return out + ("\nSTDERR:\n" + err if err else "")
        elif name == "glob":
            fs = [str(Path(f).relative_to(WORK_DIR)) for f in glob.glob(str(WORK_DIR/args["pattern"]), recursive=True)[:60]]
            return "\n".join(fs) if fs else "No matches"
        elif name == "grep":
            inc = args.get("include", "*")
            r = subprocess.run(f'rg -n "{args["pattern"]}" --glob "{inc}"', shell=True, cwd=str(WORK_DIR), capture_output=True, text=True)
            lines = r.stdout.split("\n")[:60]
            return "\n".join(lines) if lines else "No matches"
        elif name == "list":
            path = args.get("path", ".")
            items = [f"{'[DIR]' if x.is_dir() else '     '} {x.name}" for x in sorted((WORK_DIR/path).iterdir())]
            return "\n".join(items) if items else "(empty)"
        elif name == "diff":
            return git("diff", "--stat") + "\n\n" + git("diff")[:3000]
        elif name == "commit":
            msg = args.get("message", "update")
            git("add", "-A")
            return git("commit", "-m", msg)
        elif name == "undo":
            return undo(args.get("path", ""))
        elif name == "verify":
            path = args.get("path", "")
            return verify_file(path) if path else "No path specified"
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"

class ChatReq(BaseModel): messages: list; model: str = ""

@app.get("/")
def index(): return HTMLResponse(HTML)

@app.post("/api/chat")
def chat(req: ChatReq):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + req.messages
    full = ""
    tool_pat = re.compile('```tool\n(.*?)\n```', re.DOTALL)
    max_iter = 12

    for it in range(max_iter):
        content = call_ollama(msgs)
        if not content:
            break

        # check for tool block
        m = tool_pat.search(content)
        if not m:
            full += content
            break

        # text before tool block = assistant reply
        before = content[:m.start()].strip()
        if before:
            full += before + "\n"
            msgs.append({"role": "assistant", "content": before})

        # parse and execute tool
        raw_json = m.group(1).strip()
        try:
            tc = json.loads(raw_json)
        except:
            # try cleaning common model mistakes
            import re as _re
            cleaned = _re.sub(r',\s*}', '}', raw_json)
            cleaned = _re.sub(r',\s*\]', ']', cleaned)
            cleaned = cleaned.replace("'", '"')
            try: tc = json.loads(cleaned)
            except:
                full += f"[tool: parse error — invalid JSON in ```tool block]\n{raw_json[:300]}"
                msgs.append({"role": "assistant", "content": content})
                msgs.append({"role": "user", "content": f"JSON parse error. Fix and retry with valid JSON in ```tool block. Raw: {raw_json[:200]}"})
                continue

        name = tc.pop("tool", "")
        if not name:
            full += "[tool: missing 'tool' key in JSON]"
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
.msg.t{font-size:11px;padding:3px 10px;margin:2px auto;text-align:center;max-width:none}
.msg.t.ok{background:#f0fdf4;color:#166534;border:none;border-radius:4px}
.msg.t.err{background:#fef2f2;color:#991b1b;border:none;border-radius:4px}
.msg.t.warn{background:#fffbeb;color:#92400e;border:none;border-radius:4px}
.msg.s{text-align:center;font-size:11px;color:#999;margin:3px 0;background:none!important;max-width:none}
.msg .l{font-size:10px;color:#999;margin-bottom:2px;font-weight:500}
.msg pre{background:#f8f9fa;padding:8px;border-radius:4px;overflow-x:auto;font-size:12px;margin:4px 0;border:1px solid #eee}
.msg code{background:#f0f0f0;padding:1px 3px;border-radius:2px;font-size:12px}
.msg pre code{background:none;padding:0;border:none}
.msg .diff-add{background:#dcfce7;padding:1px 3px;border-radius:2px;font-size:12px;font-family:monospace}
.msg .diff-del{background:#fce7f3;padding:1px 3px;border-radius:2px;font-size:12px;font-family:monospace}
.sp{display:inline-block;width:10px;height:10px;border:2px solid #ddd;border-top-color:#2563eb;border-radius:50%;animation:s .5s infinite linear;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
#inp{display:flex;padding:6px 8px;border-top:1px solid #ddd;background:#fff;gap:6px;flex-shrink:0}
#inp textarea{flex:1;padding:7px;border:1px solid #ccc;border-radius:7px;resize:none;font-size:13px;outline:none;font-family:inherit;min-height:34px;max-height:90px}
#inp textarea:focus{border-color:#2563eb}
#inp button{background:#2563eb;color:#fff;border:none;border-radius:7px;padding:5px 16px;cursor:pointer;font-size:13px;font-weight:500;align-self:flex-end}
#inp button:hover{opacity:.85}
#inp button:disabled{opacity:.3}
#stat{height:17px;border-top:1px solid #ddd;background:#fff;font-size:10px;color:#999;padding:1px 10px;display:flex;align-items:center;gap:8px;flex-shrink:0}
#stat .g{width:6px;height:6px;border-radius:50%;background:#16a34a;display:inline-block}
#stat .r{width:6px;height:6px;border-radius:50%;background:#dc2626;display:inline-block}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:#ddd;border-radius:3px}
</style></head><body>
<div id="bar"><span class="b">AI Coder</span><select id="chm"></select><span id="prj"></span><span id="st2"></span></div>
<div id="main"><div id="chat">
<div id="msgs">
<div class="msg s">I can read, edit, write, search, diff, commit, verify, undo. Try: read package.json</div>
</div>
<div id="inp">
<textarea id="ta" rows="1" placeholder="e.g. read agent.py"></textarea>
<button id="snd" onclick="send()">OK</button>
</div>
</div></div>
<div id="stat"><span id="old"></span><span id="ols">Ollama...</span></div>
<script>
var A=window.location.origin,ms=[],sd=0,ac=null;
function $(i){return document.getElementById(i)}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function fm(t){
  var h=esc(t);
  h=h.replace(/```(\w*)\n?([\s\S]*?)```/g,'<pre><code>$2</code></pre>');
  h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
  return h.replace(/\n/g,'<br>');
}
function ah(){var e=$('ta');e.style.height='auto';e.style.height=Math.min(e.scrollHeight,90)+'px'}
function am(r,t,c){
  c=c||'';var m=document.createElement('div');m.className='msg '+r;
  var b=document.createElement('div');b.innerHTML=t;m.appendChild(b);
  $('msgs').appendChild(m);m.scrollIntoView({behavior:'smooth',block:'end'});return b
}
function init(){
  fetch(A+'/api/models').then(function(r){return r.json()}).then(function(ms){$('chm').innerHTML=ms.map(function(m){return '<option>'+m+'</option>'}).join('')}).catch(function(){});
  fetch(A+'/api/project').then(function(r){return r.json()}).then(function(p){$('prj').textContent=p.name}).catch(function(){});
  cl();$('ta').focus()
}
function cl(){fetch(A+'/api/models').then(function(){$('old').className='g';$('ols').textContent='Ollama OK'}).catch(function(){$('old').className='r';$('ols').textContent='Ollama -';setTimeout(cl,3000)})}
function send(){
  var ta=$('ta'),txt=ta.value.trim();if(!txt||sd)return;ta.value='';ah();
  am('u',fm(txt));ms.push({role:'user',content:txt});
  var m=$('chm').value||'qwen2.5-coder:7b';sd=1;$('snd').disabled=1;ac=new AbortController();
  var fl='',be=am('a','<span class="sp"></span>');$('st2').textContent='thinking...';
  fetch(A+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({model:m,messages:ms}),signal:ac.signal})
  .then(function(r){if(!r.ok)throw Error(r.status);
    var rd=r.body.getReader(),dc=new TextDecoder(),bf='';
    (function rd2(){rd.read().then(function(v){
      if(v.done){ms.push({role:'assistant',content:fl});be.innerHTML=fm(fl)||'(empty)';sd=0;$('snd').disabled=0;$('st2').textContent='';return}
      bf+=dc.decode(v.value,{stream:1});var ls=bf.split('\n');bf=ls.pop()||'';
      ls.forEach(function(l){if(l.startsWith('data: ')){try{var d=JSON.parse(l.slice(6));if(d.text)fl+=d.text}catch(e){}}});
      be.innerHTML=fm(fl)||'<span class="sp"></span>';rd2()
    }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('st2').textContent=''})})()
  }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('st2').textContent=''})
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
