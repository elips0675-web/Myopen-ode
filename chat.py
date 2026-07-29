#!/usr/bin/env python3
"""Чат с Ollama — открой http://localhost:8888 и общайся."""
import json, http.server, urllib.request, webbrowser, sys, os

OLLAMA = "http://localhost:11434"
PORT = 8888
HOST = "127.0.0.1"

HTML = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Чат с Ollama</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,sans-serif;background:#f5f5f5;color:#1a1a1a;height:100vh;display:flex;flex-direction:column}
@media(prefers-color-scheme:dark){body{background:#1a1a1a;color:#e0e0e0}}
h1{text-align:center;padding:12px;font-size:16px;font-weight:600;border-bottom:1px solid #e0e0e0;background:#fff;display:flex;align-items:center;justify-content:center;gap:8px;flex-shrink:0}
@media(prefers-color-scheme:dark){h1{background:#252525;border-color:#333}}
h1 select{font-size:12px;padding:3px 8px;border:1px solid #ddd;border-radius:6px;background:#fff;outline:none;cursor:pointer}
@media(prefers-color-scheme:dark){h1 select{background:#333;color:#e0e0e0;border-color:#555}}
#msgs{flex:1;overflow-y:auto;padding:12px;scroll-behavior:smooth}
.msg{margin-bottom:10px;padding:10px 14px;border-radius:10px;font-size:14px;line-height:1.5;max-width:85%;word-wrap:break-word}
.msg.u{background:#e8f0fe;margin-left:auto;border-bottom-right-radius:4px}
.msg.a{background:#fff;margin-right:auto;border-bottom-left-radius:4px;border:1px solid #e8e8e8}
@media(prefers-color-scheme:dark){.msg.u{background:#1e3a5f}.msg.a{background:#2a2a2a;border-color:#333}}
.msg.s{text-align:center;font-size:12px;color:#888;background:none;margin:8px auto;padding:4px}
.msg .h{font-size:11px;color:#888;margin-bottom:4px}
.msg pre{background:#f8f9fa;padding:10px;border-radius:6px;overflow-x:auto;font-size:13px;margin:8px 0;border:1px solid #e8e8e8;white-space:pre-wrap}
.msg code{background:#f0f0f0;padding:1px 4px;border-radius:3px;font-size:13px}
.msg pre code{background:none;padding:0;border:none}
@media(prefers-color-scheme:dark){.msg pre{background:#1e1e1e;border-color:#333}.msg code{background:#333}}
.sp{display:inline-block;width:14px;height:14px;border:2px solid #ddd;border-top-color:#2563eb;border-radius:50%;animation:s .6s linear infinite;margin-right:6px;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
#inparea{display:flex;padding:10px 14px;border-top:1px solid #e0e0e0;background:#fff;gap:8px;flex-shrink:0}
@media(prefers-color-scheme:dark){#inparea{background:#252525;border-color:#333}}
#inp{flex:1;padding:10px 14px;border:1px solid #ddd;border-radius:10px;font-size:14px;outline:none;resize:none;min-height:42px;max-height:120px;font-family:inherit}
#inp:focus{border-color:#2563eb}
@media(prefers-color-scheme:dark){#inp{background:#333;color:#e0e0e0;border-color:#555}#inp:focus{border-color:#3b82f6}}
#send{background:#2563eb;color:#fff;border:none;border-radius:10px;padding:8px 20px;font-size:14px;cursor:pointer;font-weight:500;align-self:flex-end}
#send:hover{background:#1d4ed8}#send:disabled{opacity:.4;cursor:default}
</style></head>
<body>
<h1>🤖 <select id="m"></select></h1>
<div id="msgs"><div class="msg s">Напиши сообщение</div></div>
<div id="inparea"><textarea id="inp" placeholder="..." rows="1"></textarea><button id="send">→</button></div>
<script>
let ms=[{role:'system',content:'Ты — полезный ассистент. Отвечай кратко.'}],st=false,ac=null;
async function load(){try{const r=await fetch('/api/tags');const d=await r.json();const s=document.getElementById('m');
s.innerHTML=d.models.map(m=>'<option value="'+m.name+'">'+m.name.replace(':latest','')+'</option>').join('')}catch(e){}}
function add(r,t){const c=document.getElementById('msgs');const m=document.createElement('div');m.className='msg '+(r==='u'?'u':'a');
if(r!=='s'){const h=document.createElement('div');h.className='h';h.textContent=r==='u'?'Вы':'AI';m.appendChild(h)}
const f=document.createElement('div');f.innerHTML=t;m.appendChild(f);c.appendChild(m);c.scrollTop=c.scrollHeight;return m}
async function send(){const i=document.getElementById('inp');const t=i.value.trim();if(!t||st)return;i.value='';add('u',esc(t));
ms.push({role:'user',content:t});const m=document.getElementById('m').value;const me=add('a','<span class="sp"></span>');st=true;
document.getElementById('send').disabled=true;ac=new AbortController();
try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({model:m||'qwen2.5-coder:7b',messages:ms,stream:true,options:{temperature:0.2,num_predict:4096}}),signal:ac.signal});
const rd=r.body.getReader(),dc=new TextDecoder();let fl='',bf='';
while(true){const{done,value}=await rd.read();if(done)break;bf+=dc.decode(value,{stream:true});const ls=bf.split('\n');bf=ls.pop()||'';
for(const l of ls){if(l){try{const j=JSON.parse(l);const c=j.message?.content||'';if(c)fl+=c}catch(e){}}}
me.innerHTML=fmt(fl)||'<span class="sp"></span>';me.scrollIntoView({behavior:'smooth',block:'end'})}
ms.push({role:'assistant',content:fl});me.innerHTML=fmt(fl)}catch(e){if(e.name!=='AbortError')me.innerHTML='Ошибка: '+e.message}
finally{st=false;document.getElementById('send').disabled=false}}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function fmt(t){let h=esc(t);h=h.replace(/```(\w*)\n?([\s\S]*?)```/g,'<pre><code>$2</code></pre>');h=h.replace(/`([^`]+)`/g,'<code>$1</code>');return h.replace(/\n/g,'<br>')}
document.getElementById('inp').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send()}});
document.getElementById('send').onclick=send;load();
</script></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == "/api/tags":
            try:
                r = urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5)
                d = r.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(d)
            except:
                self.send_error(503, "Ollama not running")
        else:
            self.send_error(404)
    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                r = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(r, timeout=120) as resp:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    while True:
                        c = resp.read(4096)
                        if not c: break
                        self.wfile.write(c)
                        self.wfile.flush()
            except Exception as e:
                self.send_error(503, str(e))
        else:
            self.send_error(404)
    def log_message(self, *a): pass

print(f"Чат с Ollama → http://localhost:{PORT}")
try:
    webbrowser.open(f"http://localhost:{PORT}")
except Exception:
    pass
try:
    http.server.HTTPServer((HOST, PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nПока!")
