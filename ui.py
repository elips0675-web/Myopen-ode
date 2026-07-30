"""HTML UI template."""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>AI Coder v2 — OpenCode Desktop</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#f5f5f5;--fg:#1a1a1a;--sidebar:#fff;--sidebar-border:#ddd;--accent:#2563eb;--accent-hover:#1d4ed8;--msg-u:#e8f0fe;--msg-a:#fff;--msg-a-border:#eee;--pre-bg:#f8f9fa;--code-bg:#f0f0f0;--inp-bg:#fff;--inp-border:#ccc;--btn:#2563eb;--btn-hover:#1d4ed8;--cnl-btn:#dc2626;--stat-bg:#fff;--st-c:#999;--diff-add:#dcfce7;--diff-add-fg:#166534;--diff-del:#fce7f3;--diff-del-fg:#991b1b;--diff-hdr:#f0f0f0;--plan:#eff6ff;--plan-fg:#1e40af;--tree-hover:#f0f0f0;--sp:10px;--s:#2563eb;--radius:8px;--font:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
[data-theme="dark"]{--bg:#0f1117;--fg:#e2e8f0;--sidebar:#161b22;--sidebar-border:#30363d;--accent:#58a6ff;--accent-hover:#79b8ff;--msg-u:#1f2937;--msg-a:#21262d;--msg-a-border:#30363d;--pre-bg:#0d1117;--code-bg:#161b22;--inp-bg:#21262d;--inp-border:#30363d;--btn:#238636;--btn-hover:#2ea043;--cnl-btn:#da3633;--stat-bg:#161b22;--st-c:#8b949e;--diff-add:#23863633;--diff-add-fg:#3fb950;--diff-del:#da363333;--diff-del-fg:#f85149;--diff-hdr:#30363d;--plan:#1f6feb22;--plan-fg:#58a6ff;--tree-hover:#21262d;--sp:10px;--s:#58a6ff;--radius:8px}
body{font-family:var(--font);background:var(--bg);color:var(--fg);height:100vh;display:flex;overflow:hidden}
body[data-theme="dark"]{--bg:#0f1117;--fg:#e2e8f0;--sidebar:#161b22;--sidebar-border:#30363d;--accent:#58a6ff;--accent-hover:#79b8ff;--msg-u:#1f2937;--msg-a:#21262d;--msg-a-border:#30363d;--pre-bg:#0d1117;--code-bg:#161b22;--inp-bg:#21262d;--inp-border:#30363d;--btn:#238636;--btn-hover:#2ea043;--cnl-btn:#da3633;--stat-bg:#161b22;--st-c:#8b949e;--diff-add:#23863633;--diff-add-fg:#3fb950;--diff-del:#da363333;--diff-del-fg:#f85149;--diff-hdr:#30363d;--plan:#1f6feb22;--plan-fg:#58a6ff;--tree-hover:#21262d;--sp:10px;--s:#58a6ff}

#sidebar{width:260px;background:var(--sidebar);border-right:1px solid var(--sidebar-border);display:flex;flex-direction:column;flex-shrink:0}
#sidebar .logo{padding:14px 16px;font-weight:700;font-size:14px;color:var(--fg);border-bottom:1px solid var(--sidebar-border);display:flex;align-items:center;gap:8px;letter-spacing:-0.3px}
#sidebar .logo svg{width:18px;height:18px;fill:var(--accent)}
#sidebar .logo span{color:var(--st-c);font-size:11px;margin-left:auto;font-weight:400}
#sidebar .section{padding:10px 16px 4px;font-size:10px;text-transform:uppercase;color:var(--st-c);letter-spacing:0.8px;font-weight:600;display:flex;align-items:center;gap:6px}
#sidebar .section .count{background:var(--sidebar-border);color:var(--st-c);font-size:9px;padding:0 6px;border-radius:8px;font-weight:500}
#sess-search{margin:6px 12px;padding:6px 10px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:6px;color:var(--fg);font-size:12px;outline:none;font-family:inherit}
#sess-search:focus{border-color:var(--accent)}
#sess-list{flex:1;overflow-y:auto;padding:4px 8px;max-height:40%}
.sess-group{font-size:10px;color:var(--st-c);padding:8px 8px 4px;font-weight:600;letter-spacing:0.5px}
.sess-card{padding:8px 10px;cursor:pointer;border-radius:6px;margin:1px 0;transition:background .1s;position:relative}
.sess-card:hover{background:var(--tree-hover)}
.sess-card.active{background:var(--accent);color:#fff}
.sess-card.active .sess-time,.sess-card.active .sess-count{color:rgba(255,255,255,.7)}
.sess-card .sess-title{font-size:12px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:16px}
.sess-card .sess-meta{display:flex;align-items:center;gap:8px;margin-top:2px;font-size:10px;color:var(--st-c)}
.sess-card .sess-count{background:var(--code-bg);padding:1px 5px;border-radius:4px;font-size:9px}
.sess-card.active .sess-count{background:rgba(255,255,255,.2)}
.sess-card .sess-del{position:absolute;top:6px;right:6px;width:18px;height:18px;border:none;background:none;color:var(--st-c);cursor:pointer;border-radius:4px;display:none;align-items:center;justify-content:center;font-size:12px;line-height:1;padding:0}
.sess-card:hover .sess-del{display:flex}
.sess-card .sess-del:hover{background:rgba(255,255,255,.1);color:var(--cnl-btn)}
.sess-card.active .sess-del{color:rgba(255,255,255,.6)}
#new-sess-btn{display:flex;align-items:center;gap:6px;margin:6px 12px;padding:7px 10px;background:var(--code-bg);border:1px dashed var(--sidebar-border);border-radius:6px;cursor:pointer;font-size:12px;color:var(--st-c);transition:all .15s;font-family:inherit}
#new-sess-btn:hover{border-color:var(--accent);color:var(--accent);background:var(--plan)}
#new-sess-btn svg{width:14px;height:14px;fill:currentColor}
#tree-wrap{overflow-y:auto}
#tree{font-size:12px;padding:2px 0}
#tree .item{padding:4px 16px;cursor:pointer;display:flex;align-items:center;gap:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#tree .item:hover{background:var(--tree-hover)}
#tree .item svg{width:13px;height:13px;flex-shrink:0;fill:var(--st-c)}
#tree .item.dir svg{fill:var(--accent)}
#tree .item.active{background:var(--accent);color:#fff}#tree .item.active svg{fill:#fff}
#tree .indent{display:inline-block;width:12px}
#tree .children{display:none}

#main{flex:1;display:flex;flex-direction:column;min-width:0}
#topbar{display:flex;align-items:center;padding:8px 16px;border-bottom:1px solid var(--sidebar-border);background:var(--sidebar);gap:10px;flex-shrink:0}
#topbar select{font-size:12px;padding:4px 8px;border:1px solid var(--inp-border);border-radius:var(--radius);background:var(--inp-bg);color:var(--fg);outline:none}
#topbar .badge{font-size:10px;padding:2px 8px;background:var(--accent);color:#fff;border-radius:10px}
#topbar .badge.off{background:var(--sidebar-border);color:var(--st-c)}
#topbar #prj{font-size:12px;color:var(--st-c);margin-left:auto}
#chat{flex:1;display:flex;flex-direction:column;min-width:0}
#msgs{flex:1;overflow-y:auto;padding:12px 16px}
.msg{margin:6px 0;padding:10px 14px;border-radius:var(--radius);font-size:13px;line-height:1.6;word-wrap:break-word;max-width:85%}
.msg.u{background:var(--msg-u);margin-left:auto;border-bottom-right-radius:3px}
.msg.a{background:var(--msg-a);margin-right:auto;border:1px solid var(--msg-a-border);border-bottom-left-radius:3px}
.msg.t{font-size:11px;padding:4px 12px;margin:3px auto;text-align:center;max-width:none;border-radius:4px}
.msg.t.ok{background:var(--diff-add);color:var(--diff-add-fg)}
.msg.t.err{background:var(--diff-del);color:var(--diff-del-fg)}
.msg.s{text-align:center;font-size:11px;color:var(--st-c);margin:4px 0;background:none!important;max-width:none}
.msg pre{background:var(--pre-bg);padding:10px;border-radius:6px;overflow-x:auto;font-size:12px;margin:6px 0;border:1px solid var(--msg-a-border)}
.msg code{background:var(--code-bg);padding:2px 5px;border-radius:3px;font-size:12px}
.msg pre code{background:none;padding:0;border:none}
.msg .dp{font-family:monospace;font-size:12px;line-height:1.5;white-space:pre-wrap;background:var(--pre-bg);padding:8px;border-radius:6px;border:1px solid var(--msg-a-border);margin:6px 0}
.msg .dp .a{background:var(--diff-add);color:var(--diff-add-fg);display:block;padding:1px 4px;margin:0 -4px}
.msg .dp .d{background:var(--diff-del);color:var(--diff-del-fg);display:block;padding:1px 4px;margin:0 -4px}
.msg .dp .h{background:var(--diff-hdr);color:var(--st-c);display:block;padding:1px 4px;margin:0 -4px}
.msg .confirm-box{background:var(--pre-bg);border:1px solid var(--inp-border);border-radius:6px;padding:10px;margin:8px 0}
.msg .confirm-box .c-title{font-weight:600;margin-bottom:6px;color:var(--accent)}
.msg .confirm-box .c-args{font-size:11px;color:var(--st-c);margin-bottom:8px;word-break:break-all}
.msg .confirm-box button{padding:5px 14px;border:none;border-radius:var(--radius);cursor:pointer;font-size:12px;font-weight:500;margin-right:6px}
.msg .confirm-box .c-yes{background:var(--btn);color:#fff}
.msg .confirm-box .c-yes:hover{background:var(--btn-hover)}
.msg .confirm-box .c-no{background:var(--sidebar-border);color:var(--fg)}
#inp{display:flex;padding:10px 16px;border-top:1px solid var(--sidebar-border);background:var(--sidebar);gap:8px;flex-shrink:0;align-items:flex-end}
#inp textarea{flex:1;padding:10px 14px;border:1px solid var(--inp-border);border-radius:var(--radius);resize:none;font-size:13px;outline:none;font-family:inherit;min-height:42px;max-height:120px;background:var(--inp-bg);color:var(--fg);line-height:1.5}
#inp textarea:focus{border-color:var(--accent)}
#inp button{background:var(--btn);color:#fff;border:none;border-radius:var(--radius);padding:8px 18px;cursor:pointer;font-size:13px;font-weight:500;align-self:flex-end;height:42px}
#inp button:hover{background:var(--btn-hover)}
#inp button:disabled{opacity:.3;cursor:not-allowed}
#inp #cnl{background:var(--cnl-btn);display:none}
#stat{height:22px;border-top:1px solid var(--sidebar-border);background:var(--stat-bg);font-size:11px;color:var(--st-c);padding:2px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}
#stat .g{width:7px;height:7px;border-radius:50%;background:#3fb950;display:inline-block}
#stat .r{width:7px;height:7px;border-radius:50%;background:#f85149;display:inline-block}
.sp{display:inline-block;width:var(--sp);height:var(--sp);border:2px solid var(--msg-a-border);border-top-color:var(--s);border-radius:50%;animation:s .5s infinite linear;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--sidebar-border);border-radius:3px}

#fileview{position:fixed;top:0;right:0;width:50%;height:100%;background:var(--sidebar);border-left:1px solid var(--sidebar-border);transform:translateX(100%);transition:transform .2s;z-index:100;display:flex;flex-direction:column}
#fileview.open{transform:translateX(0)}
#fileview .fv-bar{padding:10px 16px;border-bottom:1px solid var(--sidebar-border);display:flex;align-items:center;gap:10px}
#fileview .fv-bar .fv-name{font-weight:600;font-size:13px}
#fileview .fv-bar .fv-close{margin-left:auto;background:none;border:none;color:var(--st-c);cursor:pointer;font-size:18px}
#fileview .s{color:#ce9178}#fileview .k{color:#569cd6}#fileview .c{color:#6a9955}#fileview .n{color:#b5cea8}

#dropzone{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(37,99,235,.15);z-index:999;display:none;align-items:center;justify-content:center;pointer-events:none;backdrop-filter:blur(4px)}
#dropzone.show{display:flex}
#dropzone .dz-box{background:var(--sidebar);border:2px dashed var(--accent);border-radius:12px;padding:40px 60px;text-align:center;pointer-events:auto}
#dropzone .dz-box svg{width:40px;height:40px;fill:var(--accent);margin-bottom:12px}
#dropzone .dz-box .dz-title{font-size:16px;font-weight:600;color:var(--fg)}
#dropzone .dz-box .dz-sub{font-size:12px;color:var(--st-c);margin-top:4px}
</style></head><body>
<div id="sidebar">
  <div class="logo"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>OpenCode <span>v2</span></div>
  <div class="section">Sessions <span class="count" id="sess-count">0</span></div>
  <div id="new-sess-btn" onclick="newSession()"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>New Session</div>
  <input id="sess-search" placeholder="Search sessions..." oninput="filterSessions(this.value)">
  <div id="sess-list"></div>
  <div class="section">Files</div>
  <div id="tree-wrap"><div id="tree"></div></div>
</div>
<div id="main">
  <div id="topbar">
    <select id="chm" style="width:160px"></select>
    <button onclick="pullModel()" title="Pull model" style="background:var(--btn);color:#fff;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px">+Pull</button>
    <button onclick="delModel()" title="Delete model" style="background:var(--cnl-btn);color:#fff;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px">-Del</button>
    <span class="badge" id="model-badge">Model</span>
    <span id="prj"></span>
    <span id="st2"></span><button id="theme-btn" onclick="toggleTheme()" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:16px;margin-left:8px">&#127769;</button>
  </div>
  <div id="chat">
    <div id="msgs"><div class="msg s">Agent ready. Try: &quot;create a fibonacci function&quot;</div></div>
    <div id="inp">
      <textarea id="ta" rows="1" placeholder="Ask something..."></textarea>
      <button id="cnl" onclick="cancel()">Cancel</button>
      <button id="snd" onclick="send()">Send</button>
    </div>
  </div>
  <div id="stat"><span id="old"></span><span id="ols">Ollama...</span></div>
</div>
<div id="fileview"><div class="fv-bar"><span class="fv-name" id="fv-name"></span><button class="fv-close" onclick="closeFile()">&times;</button></div><div id="fv-content" style="flex:1;padding:16px;overflow:auto;font-size:12px;line-height:1.6;background:var(--pre-bg);margin:0;font-family:monospace;white-space:pre"></div></div>
<div id="dropzone"><div class="dz-box"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg><div class="dz-title">Drop files here</div><div class="dz-sub">Upload to workspace</div></div></div>
<script>
var A=window.location.origin,ms=[],sd=0,ac=null,curSid="",allSessions=[];
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
  h=h.replace(/```diff\n?([\s\S]*?)```/g,function(_,c){return fmtDiff(c)});
  h=h.replace(/```(\w*)\n?([\s\S]*?)```/g,'<pre><code>$2</code></pre>');
  h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
  h=h.replace(/\[CONFIRM\]/g,'<b>[CONFIRM]</b>');
  h=h.replace(/\[PLAN\]/g,'<b>[PLAN]</b>');
  h=h.replace(/\[tool:(\w+)\]/g,'<b>[tool:$1]</b>');
  return h.replace(/\n/g,'<br>');
}
function ah(){var e=$('ta');e.style.height='auto';e.style.height=Math.min(e.scrollHeight,120)+'px'}
function am(r,t){
  var m=document.createElement('div');m.className='msg '+r;
  var b=document.createElement('div');b.innerHTML=t;m.appendChild(b);
  $('msgs').appendChild(m);m.scrollIntoView({behavior:'smooth',block:'end'});return b
}
function cancel(){if(ac){ac.abort();sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent='cancelled'}}

// Sessions
function timeAgo(t){
  if(!t)return '';var d=new Date(t),n=new Date(),s=Math.floor((n-d)/1000);
  if(s<60)return 'now';if(s<3600)return Math.floor(s/60)+'m';
  if(s<86400)return Math.floor(s/3600)+'h';if(s<2592000)return Math.floor(s/86400)+'d';
  return d.toLocaleDateString();
}
function groupSessions(ss){
  var now=new Date(),today=[],week=[],older=[];
  ss.forEach(function(s){
    var u=s.updated?new Date(s.updated):null;
    if(!u){older.push(s);return}
    var diff=(now-u)/86400000;
    if(diff<1)today.push(s);else if(diff<7)week.push(s);else older.push(s);
  });
  var h='';
  [['Today',today],['Week',week],['Older',older]].forEach(function(g){
    if(!g[1].length)return;
    h+='<div class="sess-group">'+g[0]+'</div>';
    g[1].forEach(function(s){
      var cls=s.id===curSid?'sess-card active':'sess-card';
      var nmsg=s.messages?s.messages.length:0;
      h+='<div class="'+cls+'" onclick="openSession(\''+s.id+'\')"><div class="sess-title">'+esc(s.title)+'</div><div class="sess-meta"><span class="sess-time">'+timeAgo(s.updated)+'</span><span class="sess-count">'+nmsg+' msgs</span></div><button class="sess-del" onclick="event.stopPropagation();delSession(\''+s.id+'\')">&times;</button></div>';
    });
  });
  $('sess-list').innerHTML=h||'<div style="padding:20px 16px;color:var(--st-c);font-size:12px;text-align:center">No sessions</div>';
  $('sess-count').textContent=ss.length;
}
function loadSessions(){
  fetch(A+'/api/sessions').then(function(r){return r.json()}).then(function(ss){
    allSessions=ss;var q=$('sess-search').value.toLowerCase();
    groupSessions(q?ss.filter(function(s){return s.title.toLowerCase().includes(q)}):ss);
  });
}
function filterSessions(q){groupSessions(q?allSessions.filter(function(s){return s.title.toLowerCase().includes(q.toLowerCase())}):allSessions)}
function newSession(){
  var t=prompt('Session name:','Session '+new Date().toLocaleString());
  if(!t)return;
  fetch(A+'/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:t})})
  .then(function(r){return r.json()}).then(function(s){curSid=s.id;ms=[];$('msgs').innerHTML='<div class="msg s">New session: '+esc(s.title)+'</div>';loadSessions();$('sess-search').value='';});
}
function openSession(sid){
  curSid=sid;
  fetch(A+'/api/sessions/'+sid).then(function(r){return r.json()}).then(function(d){ms=d.messages||[];$('msgs').innerHTML='<div class="msg s">Loaded: '+esc(d.title)+'</div>';loadSessions();});
}
function delSession(sid){
  if(!confirm('Delete session?'))return;
  fetch(A+'/api/sessions/'+sid,{method:'DELETE'}).then(function(){if(curSid===sid){curSid='';ms=[];$('msgs').innerHTML='<div class="msg s">Session deleted</div>';}loadSessions();});
}

// Files
function loadFiles(path){
  fetch(A+'/api/files?path='+encodeURIComponent(path||'.')).then(function(r){return r.json()}).then(function(d){$('tree').innerHTML=renderTree(d.tree);});
}
function renderTree(nodes,depth){
  depth=depth||0;var h='';
  nodes.forEach(function(n){
    var indent='<span class="indent"></span>'.repeat(depth);
    var icon=n.type==='dir'?'<svg viewBox="0 0 24 24"><path d="M10 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2h-8l-2-2z"/></svg>':'<svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>';
    h+='<div class="item '+(n.type==='dir'?'dir':'file')+'" onclick="'+(n.type==='dir'?'toggleDir':'openFile')+'(\''+esc(n.path)+'\',this)">'+indent+icon+'<span>'+esc(n.name)+'</span></div>';
    if(n.children)h+='<div class="children" style="display:none">'+renderTree(n.children,depth+1)+'</div>';
  });
  return h;
}
function toggleDir(path,el){
  var next=el.nextElementSibling;
  if(next&&next.classList.contains('children')){next.style.display=next.style.display==='none'?'block':'none';}
}
function openFile(path){
  fetch(A+'/api/file?path='+encodeURIComponent(path)).then(function(r){return r.json()}).then(function(d){
    if(d.error)return;$('fv-name').textContent=path;$('fv-content').textContent=d.content;$('fileview').classList.add('open');
  });
}
function closeFile(){$('fileview').classList.remove('open')}

// Basic syntax highlighting for file viewer
function highlightSyntax(code, ext){
  var lang = ext.split('.').pop();
  var h = esc(code);
  if(['py','js','ts','jsx','tsx','java','go','rs','c','cpp','h','cs','json','yml','yaml','toml','ini','cfg','env'].includes(lang)){
    if(lang==='py') h=h.replace(/(^|\n)([ \t]*#.*?)(?=\n|$)/g, '$1<span class="c">$2</span>');
    else if(['yml','yaml'].includes(lang)) h=h.replace(/(^|\n)([ \t]*#.*?)(?=\n|$)/g, '$1<span class="c">$2</span>');
    else if(['ini','cfg','env'].includes(lang)) h=h.replace(/(^|\n)([ \t]*[;#].*?)(?=\n|$)/g, '$1<span class="c">$2</span>');
    else h=h.replace(/(^|\n)([ \t]*\/\/.*?)(?=\n|$)/g, '$1<span class="c">$2</span>');
  }
  if(['json','jsonc'].includes(lang)){
    h=h.replace(/(&quot;[^&quot;]*&quot;)(\s*:)/g,'<span class="k">$1</span>$2');
  }
  h=h.replace(/(&quot;[^&quot;]*&quot;|&#39;[^&#39;]*&#39;|`[^`]*`)/g,'<span class="s">$1</span>');
  var kw = lang==='py'
    ? ['\\b(def|class|if|else|elif|for|while|return|import|from|as|try|except|finally|with|yield|async|await|pass|raise|in|not|and|or|True|False|None)\\b']
    : ['\\b(function|class|if|else|for|while|return|import|from|try|catch|finally|throw|async|await|const|let|var|new|this|typeof|instanceof|switch|case|break|continue|export|default|extends|static|get|set|true|false|null|undefined|void|yield|of|in|interface|type|enum|implements|abstract|readonly|private|protected|public|declare|namespace|module|any|string|number|boolean)\\b'];
  kw.forEach(function(p){h=h.replace(new RegExp(p,'g'),'<span class="k">$1</span>')});
  h=h.replace(/\b(\d+\.?\d*)\b/g,'<span class="n">$1</span>');
  return h;
}
function openFile(path){
  fetch(A+'/api/file?path='+encodeURIComponent(path)).then(function(r){return r.json()}).then(function(d){
    if(d.error)return;$('fv-name').textContent=path;
    $('fv-content').innerHTML=highlightSyntax(d.content,path);$('fileview').classList.add('open');
  });
}

// Init
function toggleTheme(){var d=document.body.getAttribute("data-theme")==="dark";document.body.setAttribute("data-theme",d?"":"dark");$("theme-btn").textContent=d?"&#127769;":"&#9728;&#65039;";localStorage.setItem("theme",d?"":"dark")}
if(localStorage.getItem("theme")==="dark"){document.body.setAttribute("data-theme","dark");$("theme-btn").textContent="&#9728;&#65039;"}
function init(){
  fetch(A+'/api/models').then(function(r){return r.json()}).then(function(mm){
    $('chm').innerHTML=mm.map(function(m){return '<option>'+m+'</option>'}).join('');
    var ds=mm.find(function(m){return m.includes('deepseek')});
    if(ds){$('chm').value=ds;$('model-badge').textContent='DeepSeek'}
  }).catch(function(){});
  fetch(A+'/api/project').then(function(r){return r.json()}).then(function(p){$('prj').textContent=p.name}).catch(function(){});
  loadFiles();loadSessions();cl();$('ta').focus();
}
function cl(){fetch(A+'/api/models').then(function(){$('old').className='g';$('ols').textContent='Ollama OK'}).catch(function(){$('old').className='r';$('ols').textContent='Ollama -';setTimeout(cl,3000)})}

function send(){
  var ta=$('ta'),txt=ta.value.trim();if(!txt||sd)return;ta.value='';ah();
  am('u',fm(txt));ms.push({role:'user',content:txt});
  var m=$('chm').value||'deepseek-r1:7b';sd=1;$('snd').disabled=1;$('cnl').style.display='inline-block';ac=new AbortController();
  var fl='',be=am('a','<span class="sp"></span>');$('st2').textContent='thinking...';
  fetch(A+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({model:m,messages:ms,session_id:curSid}),signal:ac.signal})
  .then(function(r){if(!r.ok)throw Error(r.status);
    var rd=r.body.getReader(),dc=new TextDecoder(),bf='';
    (function rd2(){rd.read().then(function(v){
      if(v.done){ms.push({role:'assistant',content:fl});be.innerHTML=fm(fl)||'(empty)';sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent='';loadFiles();return}
      bf+=dc.decode(v.value,{stream:1});var ls=bf.split('\n');bf=ls.pop()||'';
      ls.forEach(function(l){if(l.startsWith('data: ')){try{var d=JSON.parse(l.slice(6));if(d.text)fl+=d.text}catch(e){}}});
      be.innerHTML=fm(fl)||'<span class="sp"></span>';rd2()
    }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent=''})})()
  }).catch(function(e){if(e.name!='AbortError'){be.innerHTML='Error: '+esc(e.message)}sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent=''})
}

function fmtMsg(t){
  t=t.replace(/\[CONFIRM\]\s*Allow\s+(\w+)\?\nArgs:\s*(.+?)(?=\nReply|$)/gs,function(_,tool,args){
    return '<div class="confirm-box"><div class="c-title">Confirm: '+esc(tool)+'</div><div class="c-args">'+esc(args)+'</div><button class="c-yes" onclick="confirmYes()">Yes</button><button class="c-no" onclick="confirmNo()">No</button></div>';
  });
  return fm(t);
}
function confirmYes(){$('ta').value='yes';send();var boxes=document.querySelectorAll('.confirm-box');boxes[boxes.length-1].style.display='none'}
function confirmNo(){var boxes=document.querySelectorAll('.confirm-box');boxes[boxes.length-1].style.display='none';am('u',fm('no'));ms.push({role:'user',content:'no'})}

// Drag & drop
var dz=$('dropzone'),ddCount=0;
document.addEventListener('dragenter',function(e){e.preventDefault();ddCount++;dz.classList.add('show')});
document.addEventListener('dragleave',function(e){e.preventDefault();ddCount--;if(!ddCount)dz.classList.remove('show')});
document.addEventListener('dragover',function(e){e.preventDefault()});
document.addEventListener('drop',function(e){
  e.preventDefault();ddCount=0;dz.classList.remove('show');
  var files=e.dataTransfer.files;
  for(var fi=0;fi<files.length;fi++){
    (function(file){
      var reader=new FileReader();
      reader.onload=function(ev){
        var content=ev.target.result,path=file.name,ta=$('ta');
        ta.value='I uploaded file: '+path+'\n```\n'+content.slice(0,2000)+'\n```';ah();
        fetch(A+'/api/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path,content:content})})
        .then(function(r){return r.json()}).then(function(d){if(d.ok)am('t ok','Uploaded: '+esc(path)+' ('+d.size+'b)');else am('t err','Upload failed');loadFiles()}).catch(function(e){am('t err','Upload error')});
      };reader.readAsText(file);
    })(files[fi]);
  }
});

// Model management
function pullModel(){
  var name=prompt('Model name to pull (e.g. llama3.2:3b):');if(!name)return;
  var btn=event.target;btn.disabled=1;btn.textContent='...';
  fetch(A+'/api/models/pull?name='+encodeURIComponent(name),{method:'POST'})
  .then(function(r){return r.json()}).then(function(d){alert(d.status||'done');init()})
  .catch(function(e){alert('Error')}).finally(function(){btn.disabled=0;btn.textContent='+Pull'});
}
function delModel(){
  var sel=$('chm'),name=sel.value;if(!confirm('Delete "'+name+'"?'))return;
  var btn=event.target;btn.disabled=1;btn.textContent='...';
  fetch(A+'/api/models/'+encodeURIComponent(name),{method:'DELETE'})
  .then(function(r){return r.json()}).then(function(d){alert(d.status||'deleted');init()})
  .catch(function(e){alert('Error')}).finally(function(){btn.disabled=0;btn.textContent='-Del'});
}

$('ta').addEventListener('keydown',function(e){if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}});
$('ta').addEventListener('input',ah);init();
</script>
</body></html>"""
