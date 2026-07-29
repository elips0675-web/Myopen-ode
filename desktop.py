#!/usr/bin/env python3
import json, os, subprocess, glob, webbrowser
from pathlib import Path
import requests, uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AI_MODEL", "qwen2.5-coder:7b")
WORK_DIR = Path(os.environ.get("WORK_DIR", "E:\\Tickets cursor\\ticketscursor"))

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

try:
    requests.post(f"{OLLAMA_URL}/api/generate", json={"model": MODEL, "prompt": "", "keep_alive": -1, "options": {"num_ctx": 2048, "num_predict": 1}}, timeout=10)
except: pass

class ChatReq(BaseModel): messages: list; model: str = ""; stream: bool = True
class PathReq(BaseModel): path: str
class WriteReq(BaseModel): path: str; content: str
class CmdReq(BaseModel): cmd: str
class GlobReq(BaseModel): pattern: str

@app.get("/")
def index(): return HTMLResponse(INDEX_HTML)

@app.post("/api/chat")
def chat(req: ChatReq):
    model = req.model or MODEL
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": model, "messages": req.messages, "stream": req.stream, "keep_alive": -1,
            "options": {"temperature": 0.2, "num_predict": 4096, "num_ctx": 4096},
        }, stream=req.stream, timeout=120)
        r.raise_for_status()
        if req.stream:
            def gen():
                for line in r.iter_lines(decode_unicode=True):
                    if line:
                        try:
                            c = json.loads(line).get("message", {})
                            t = c.get("content","") or c.get("thinking","")
                            if t: yield "data: " + json.dumps({"text":t}) + "\n\n"
                        except: pass
                yield "data: [DONE]\n\n"
            return StreamingResponse(gen(), media_type="text/event-stream")
        data = r.json()
        msg = data.get("message", {})
        return {"content": msg.get("content","") or msg.get("thinking","")}
    except Exception as e:
        raise HTTPException(503, f"Ollama: {e}")

@app.get("/api/models")
def list_models():
    try: return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags",timeout=5).json().get("models",[])]
    except: return [MODEL]

@app.get("/api/project")
def get_project(): return {"name": WORK_DIR.name, "path": str(WORK_DIR)}

@app.post("/api/file/read")
def file_read(req: PathReq):
    p = WORK_DIR / req.path
    if not p.exists(): raise HTTPException(404)
    if p.is_dir():
        items = [{"n":x.name,"d":x.is_dir(),"s":x.stat().st_size if x.is_file() else 0} for x in sorted(p.iterdir())]
        return {"type":"dir","items":items}
    try: return {"type":"file","content":p.read_text("utf-8"),"size":p.stat().st_size}
    except: return {"type":"binary","size":p.stat().st_size}

@app.post("/api/file/write")
def file_write(req: WriteReq):
    p = WORK_DIR / req.path; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(req.content,"utf-8"); return {"ok":True}

@app.post("/api/command")
def command(req: CmdReq):
    try:
        r = subprocess.run(req.cmd, shell=True, cwd=str(WORK_DIR), capture_output=True, text=True, timeout=30)
        return {"stdout":r.stdout,"stderr":r.stderr,"code":r.returncode}
    except subprocess.TimeoutExpired: return {"stdout":"","stderr":"[TIMEOUT]","code":-1}
    except Exception as e: return {"stdout":"","stderr":str(e),"code":-1}

@app.post("/api/glob")
def glob_files(req: GlobReq):
    return [str(Path(f).relative_to(WORK_DIR)) for f in glob.glob(str(WORK_DIR/req.pattern),recursive=True)[:100]]

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Desktop</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f5f5f5;--surface:#fff;--border:#e0e0e0;--text:#1a1a1a;--text2:#666;--primary:#2563eb;--user:#e8f0fe;--ai:#fff;--code:#f8f9fa;--sb:#fafafa;--red:#dc2626;--green:#16a34a}
[data-theme=dark]{--bg:#1a1a1a;--surface:#252525;--border:#333;--text:#e0e0e0;--text2:#999;--primary:#3b82f6;--user:#1e3a5f;--ai:#2a2a2a;--code:#1e1e1e;--sb:#1e1e1e}
html,body{height:100%;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--text)}
#layout{display:flex;height:100vh}
#sidebar{width:180px;min-width:180px;background:var(--sb);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;transition:.2s}
#sidebar.hide{width:0;min-width:0;overflow:hidden}
#sidebar .head{padding:10px;font-size:11px;font-weight:600;color:var(--text2);border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:4px}
#sidebar select{padding:2px 4px;font-size:10px;border:1px solid var(--border);border-radius:3px;background:var(--surface);color:var(--text)}
#ftree{flex:1;overflow-y:auto;padding:2px 0;font-size:12px}
.ft{padding:3px 12px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text2)}
.ft:hover{background:var(--surface)}.ft.dir{color:var(--text);font-weight:500}.ft.file{color:#ce9178}.ft.sub{padding-left:24px}
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#toolbar{display:flex;align-items:center;padding:3px 8px;border-bottom:1px solid var(--border);background:var(--surface);gap:4px;flex-shrink:0;font-size:12px}
#toolbar .brand{font-weight:700;color:var(--primary);margin-right:6px}
#toolbar button{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:2px 8px;border-radius:4px;cursor:pointer;font-size:11px}
#toolbar button:hover{background:var(--bg)}
#toolbar #prj{font-size:10px;color:var(--text2);margin-left:auto;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#pane{flex:1;display:flex;min-height:0}
#editorPane{flex:1;display:flex;flex-direction:column;min-width:0}
#tabs{display:flex;background:var(--surface);border-bottom:1px solid var(--border);overflow-x:auto;flex-shrink:0;font-size:12px}
#tab{padding:4px 12px;cursor:pointer;border-right:1px solid var(--border);white-space:nowrap;display:flex;align-items:center;gap:4px;color:var(--text2);user-select:none}
#tab.active{background:var(--bg);color:var(--text);border-bottom:2px solid var(--primary)}
#tab .close{font-size:10px;opacity:.4;cursor:pointer;margin-left:4px}
#tab .close:hover{opacity:1;color:var(--red)}
#tab .dot{color:var(--amber);font-size:14px;line-height:1}
#editor{flex:1;min-height:0}
#chat{width:360px;min-width:280px;display:flex;flex-direction:column;border-left:1px solid var(--border);background:var(--bg);flex-shrink:0}
#chat.hide{width:0;min-width:0;overflow:hidden}
#chat .head{padding:6px 10px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;display:flex;align-items:center;gap:6px;flex-shrink:0;color:var(--text2)}
#chat .head select{font-size:10px;padding:1px 4px;border:1px solid var(--border);border-radius:3px;background:var(--surface);color:var(--text)}
#msgs{flex:1;overflow-y:auto;padding:8px;scroll-behavior:smooth}
.msg{margin-bottom:6px;padding:8px 12px;border-radius:8px;font-size:13px;line-height:1.5;word-wrap:break-word}
.msg.user{background:var(--user);margin-left:20px;border-bottom-right-radius:3px}
.msg.assistant{background:var(--ai);margin-right:20px;border-bottom-left-radius:3px;border:1px solid var(--border)}
.msg.system{text-align:center;font-size:11px;color:var(--text2);margin:3px 0;padding:3px 8px;background:none!important}
.msg .label{font-size:10px;color:var(--text2);margin-bottom:2px;font-weight:500}
.msg pre{background:var(--code);padding:8px;border-radius:4px;overflow-x:auto;font-size:12px;margin:4px 0;border:1px solid var(--border)}
.msg code{background:var(--code);padding:1px 3px;border-radius:2px;font-size:12px}
.msg pre code{background:none;padding:0;border:none}
.spinner{display:inline-block;width:10px;height:10px;border:2px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin .6s infinite linear;vertical-align:middle;margin-right:4px}
@keyframes spin{to{transform:rotate(360deg)}}
#inputArea{padding:6px 10px;border-top:1px solid var(--border);background:var(--surface);display:flex;gap:6px;flex-shrink:0}
#inp{flex:1;padding:8px 12px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:8px;resize:none;font-size:13px;outline:none;font-family:inherit;min-height:36px;max-height:100px}
#inp:focus{border-color:var(--primary)}
#sndBtn{background:var(--primary);color:#fff;border:none;border-radius:8px;padding:6px 16px;cursor:pointer;font-size:13px;font-weight:500;align-self:flex-end}
#sndBtn:hover{opacity:.85}
#sndBtn:disabled{opacity:.3;cursor:default}
#term{display:none;flex-direction:column;height:130px;border-top:1px solid var(--border);background:var(--surface);flex-shrink:0}
#term.show{display:flex}
#term .head{display:flex;padding:2px 10px;font-size:10px;color:var(--text2);border-bottom:1px solid var(--border);align-items:center;gap:6px;flex-shrink:0}
#termOut{flex:1;overflow-y:auto;padding:4px 10px;font-family:Consolas,monospace;font-size:11px;color:var(--text);white-space:pre-wrap;line-height:1.4}
#termInp{display:flex;padding:2px 10px 6px;gap:4px}
#termInp input{flex:1;padding:4px 8px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:4px;font-family:Consolas,monospace;font-size:11px;outline:none}
#termInp input:focus{border-color:var(--primary)}
#termInp button{background:var(--primary);color:#fff;border:none;border-radius:4px;padding:3px 10px;cursor:pointer;font-size:10px}
#status{height:18px;border-top:1px solid var(--border);background:var(--surface);font-size:10px;color:var(--text2);padding:2px 10px;display:flex;align-items:center;gap:10px;flex-shrink:0}
#status .dot{width:6px;height:6px;border-radius:50%;display:inline-block}
#status .dot.green{background:var(--green)}#status .dot.red{background:var(--red)}
#search{background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:11px;padding:2px 8px;outline:none;width:120px;margin-left:8px}
#search:focus{border-color:var(--primary)}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style></head><body>
<div id="layout">
<div id="sidebar"><div class="head">AI Desktop<select id="modelSelect"></select></div><div id="ftree"></div></div>
<div id="main">
<div id="toolbar">
<button onclick="tog('sidebar')">&equiv;</button><span class="brand">AI</span>
<button onclick="tog('term')">&gt;_</button><button onclick="tog('chat')">C</button><button onclick="togTheme()" id="themeBtn">S</button>
<input id="search" placeholder="search..." oninput="searchFiles(this.value)"><span id="prj"></span>
</div>
<div id="pane">
<div id="editorPane"><div id="tabs"></div><div id="editor"></div></div>
<div id="chat">
<div class="head">Chat <select id="chatModel"></select></div>
<div id="msgs"><div class="msg system">Ask me something</div></div>
<div id="inputArea"><textarea id="inp" placeholder="What to do?" rows="1" oninput="autoH(this)"></textarea><button id="sndBtn" onclick="send()">OK</button></div>
</div></div>
<div id="term">
<div class="head"><span>Terminal</span><span style="flex:1"></span></div>
<div id="termOut"></div>
<div id="termInp"><input id="termInput" placeholder="cmd..." onkeydown="if(event.key==='Enter')runCmd()"><button onclick="runCmd()">&gt;</button></div>
</div>
<div id="status"><span class="dot" id="olDot"></span><span id="olStat">Ollama...</span><span id="statusInfo"></span></div>
</div></div>
<script>
var API = window.location.origin;
var myFiles = {}; var curFile = null; var ed = null; var msgs = []; var sending = false; var ac = null;

function $(id){return document.getElementById(id)}
function tog(id){var e=$(id);if(e)e.classList.toggle('hide')}
function togTheme(){
    var d=document.body;
    if(d.getAttribute('data-theme')==='dark'){d.removeAttribute('data-theme');$('themeBtn').innerHTML='S'}
    else{d.setAttribute('data-theme','dark');$('themeBtn').innerHTML='M'}
    localStorage.setItem('theme',d.getAttribute('data-theme')||'light')
}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function fmt(t){
    var h=esc(t);
    h=h.replace(/```(\w*)\n?([\s\S]*?)```/g,'<pre><code>$2</code></pre>');
    h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
    return h.replace(/\n/g,'<br>');
}
function autoH(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,100)+'px'}

function init(){
    fetch(API+'/api/models').then(function(r){return r.json()}).then(function(ms){
        var h=ms.map(function(m){return '<option value="'+m+'">'+m.replace(':latest','')+'</option>'}).join('');
        $('modelSelect').innerHTML=h;$('chatModel').innerHTML=h;
        var sv=localStorage.getItem('m');if(sv){$('modelSelect').value=sv;$('chatModel').value=sv}
    }).catch(function(){});
    fetch(API+'/api/project').then(function(r){return r.json()}).then(function(p){$('prj').textContent=p.name}).catch(function(){});
    loadTree('.');checkOl();
}
function checkOl(){
    fetch(API+'/api/models').then(function(){$('olDot').className='dot green';$('olStat').textContent='Ollama OK'})
    .catch(function(){$('olDot').className='dot red';$('olStat').textContent='Ollama -';setTimeout(checkOl,3000)})
}
function loadTree(p){
    p=p||'.';
    fetch(API+'/api/file/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})})
    .then(function(r){return r.json()}).then(function(j){
        if(j.type!=='dir')return;var el=$('ftree');if(p==='.')el.innerHTML='';
        (j.items||[]).forEach(function(i){
            var d=document.createElement('div');d.className='ft '+(i.d?'dir':'file');
            d.textContent=(i.d?'[+] ':'[*] ')+i.n;
            if(i.d)d.onclick=function(e){e.stopPropagation();tgDir(this,p+'/'+i.n)};
            else d.onclick=function(){openFile(p+'/'+i.n)};
            el.appendChild(d);
        });
    }).catch(function(){});
}
function tgDir(el,p){
    var nxt=el.nextElementSibling;
    if(nxt&&nxt.classList.contains('sub')){nxt.style.display=nxt.style.display==='none'?'':'none';return}
    var w=document.createElement('div');w.className='sub';
    fetch(API+'/api/file/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})})
    .then(function(r){return r.json()}).then(function(j){
        if(j.type!=='dir')return;
        (j.items||[]).forEach(function(i){
            var c=document.createElement('div');c.className='ft '+(i.d?'dir':'file');
            c.textContent=(i.d?'[+] ':'[*] ')+i.n;
            if(i.d)c.onclick=function(e){e.stopPropagation();tgDir(c,p+'/'+i.n)};
            else c.onclick=function(){openFile(p+'/'+i.n)};w.appendChild(c);
        });el.parentNode.insertBefore(w,el.nextSibling);
    }).catch(function(){});
}
function openFile(p){
    fetch(API+'/api/file/read',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p})})
    .then(function(r){return r.json()}).then(function(j){
        if(j.type!=='file')return;
        var lang='plaintext';
        if(/\.(tsx?|jsx?)$/i.test(p)) lang=/\.tsx?$/i.test(p)?'typescript':'javascript';
        else if(/\.py$/i.test(p)) lang='python';else if(/\.css$/i.test(p)) lang='css';
        else if(/\.html?$/i.test(p)) lang='html';else if(/\.json$/i.test(p)) lang='json';
        else if(/\.md$/i.test(p)) lang='markdown';else if(/\.sql$/i.test(p)) lang='sql';
        curFile=p;myFiles[p]={content:j.content,dirty:false,lang:lang};
        if(ed){ed.setValue(j.content);monaco.editor.setModelLanguage(ed.getModel(),lang)}
        rendTabs();
    }).catch(function(){});
}
function rendTabs(){
    var c=$('tabs');c.innerHTML='';var paths=Object.keys(myFiles);
    if(!paths.length)return;
    paths.forEach(function(p){
        var t=document.createElement('div');t.id='tab';if(p===curFile)t.className='active';
        var f=myFiles[p];var n=p.split('/').pop()||p;
        t.innerHTML=(f.dirty?'<span class="dot">*</span> ':'')+esc(n)+'<span class="close">&times;</span>';
        t.onclick=function(){if(myFiles[curFile]&&myFiles[curFile].dirty)saveFile(curFile);curFile=p;if(ed){ed.setValue(myFiles[p].content);monaco.editor.setModelLanguage(ed.getModel(),myFiles[p].lang)}rendTabs()};
        t.querySelector('.close').onclick=function(ev){ev.stopPropagation();closeFile(p)};
        c.appendChild(t);
    });
}
function closeFile(p){
    if(myFiles[p]&&myFiles[p].dirty)saveFile(p);delete myFiles[p];
    if(p===curFile){var k=Object.keys(myFiles);curFile=k.length?k[0]:null;if(ed)ed.setValue(curFile?myFiles[curFile].content:'//')}
    rendTabs();
}
function saveFile(p){
    var f=myFiles[p];if(!f)return;
    fetch(API+'/api/file/write',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:p,content:f.content})})
    .then(function(){f.dirty=false;rendTabs()}).catch(function(){});
}
function addMsg(role,html){
    var c=$('msgs');var m=document.createElement('div');m.className='msg '+role;
    if(role!=='system'){var l=document.createElement('div');l.className='label';l.textContent=role==='user'?'You':'AI';m.appendChild(l)}
    var b=document.createElement('div');b.innerHTML=html||'';m.appendChild(b);
    c.appendChild(m);c.scrollTop=c.scrollHeight;return b;
}
function send(){
    var inp=$('inp');var text=inp.value.trim();if(!text||sending)return;
    inp.value='';autoH(inp);addMsg('user',fmt(text));
    var model=$('chatModel').value||'qwen2.5-coder:7b';
    msgs.push({role:'user',content:text});
    var bodyEl=addMsg('assistant','<span class="spinner"></span>');
    sending=true;$('sndBtn').disabled=true;ac=new AbortController();var full='';
    fetch(API+'/api/chat',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({model:model,messages:[{role:'system',content:'You are a code expert. Answer concisely.'}].concat(msgs),stream:true}),
        signal:ac.signal
    }).then(function(r){
        if(!r.ok)throw new Error(r.status+' '+r.statusText);
        var reader=r.body.getReader();var decoder=new TextDecoder();var buf='';
        function rd(){
            reader.read().then(function(result){
                if(result.done){msgs.push({role:'assistant',content:full});bodyEl.innerHTML=fmt(full)||'(empty)';sending=false;$('sndBtn').disabled=false;return;}
                buf+=decoder.decode(result.value,{stream:true});var lines=buf.split('\n');buf=lines.pop()||'';
                lines.forEach(function(l){if(l&&l.startsWith('data: ')){try{var d=JSON.parse(l.slice(6));if(d.text)full+=d.text}catch(e){}}});
                bodyEl.innerHTML=fmt(full)||'<span class="spinner"></span>';if(full)bodyEl.scrollIntoView({behavior:'smooth',block:'end'});
                rd();
            }).catch(function(err){if(err.name!=='AbortError')bodyEl.innerHTML='Error: '+esc(err.message);sending=false;$('sndBtn').disabled=false});
        }
        rd();
    }).catch(function(err){if(err.name!=='AbortError')bodyEl.innerHTML='Error: '+esc(err.message);sending=false;$('sndBtn').disabled=false});
}
function runCmd(){
    var inp=$('termInput');var cmd=inp.value.trim();if(!cmd)return;inp.value='';
    var out=$('termOut');out.textContent+='$ '+cmd+'\n';
    fetch(API+'/api/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd:cmd})})
    .then(function(r){return r.json()}).then(function(d){if(d.stdout)out.textContent+=d.stdout;if(d.stderr)out.textContent+=d.stderr;out.scrollTop=out.scrollHeight}).catch(function(){});
}
function searchFiles(q){
    if(!q){loadTree('.');return}
    fetch(API+'/api/glob',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pattern:'**/*'+q+'*'})})
    .then(function(r){return r.json()}).then(function(f){$('ftree').innerHTML=f.slice(0,50).map(function(f){return '<div class="ft file" onclick="openFile(\''+f+'\')">[*] '+esc(f)+'</div>'}).join('')}).catch(function(){});
}
function initM(){
    if(typeof monaco!=='undefined'&&monaco.editor){
        ed=monaco.editor.create($('editor'),{value:'// select a file',language:'javascript',theme:'vs',fontSize:12,minimap:{enabled:false},automaticLayout:true,wordWrap:'on',scrollBeyondLastLine:false});
        ed.onDidChangeModelContent(function(){if(curFile&&myFiles[curFile]){myFiles[curFile].content=ed.getValue();if(!myFiles[curFile].dirty){myFiles[curFile].dirty=true;rendTabs()}}});
    }else setTimeout(initM,200);
}
init();
</script>
<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs/loader.js"></script>
<script>
require.config({paths:{'vs':'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs'}});
require(['vs/editor/editor.main'],function(){initM();});
</script>
</body></html>"""

def main():
    port = int(os.environ.get("PORT", "8765"))
    url = f"http://localhost:{port}"
    print(f"\n  AI Desktop: {url}")
    print(f"  Project: {WORK_DIR}")
    print(f"  Model: {MODEL}")
    print(f"  Ctrl+C to exit\n")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

if __name__ == "__main__":
    main()
