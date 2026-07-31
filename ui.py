"""HTML UI template."""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>AI Coder v2 — OpenCode Desktop</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/theme/dracula.min.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.css">
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
#hint-box{position:fixed;display:none;z-index:999;background:var(--sidebar);border:1px solid var(--sidebar-border);border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,.25);max-height:200px;overflow-y:auto;min-width:200px}
#hint-box .hint-item{padding:6px 12px;font-size:12px;cursor:pointer;white-space:nowrap}
#hint-box .hint-item.sel{background:var(--accent);color:#fff}
#stat{height:22px;border-top:1px solid var(--sidebar-border);background:var(--stat-bg);font-size:11px;color:var(--st-c);padding:2px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0}
#stat .g{width:7px;height:7px;border-radius:50%;background:#3fb950;display:inline-block}
#stat .r{width:7px;height:7px;border-radius:50%;background:#f85149;display:inline-block}
.sp{display:inline-block;width:var(--sp);height:var(--sp);border:2px solid var(--msg-a-border);border-top-color:var(--s);border-radius:50%;animation:s .5s infinite linear;vertical-align:middle}
@keyframes s{to{transform:rotate(360deg)}}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-thumb{background:var(--sidebar-border);border-radius:3px}
@media(max-width:768px){#sidebar{width:100%;position:fixed;z-index:50;height:auto;max-height:40%;border-right:none;border-bottom:1px solid var(--sidebar-border);display:none}#sidebar.open{display:flex}#main{padding-top:0}#menu-toggle{display:block!important;background:none;border:none;color:var(--st-c);cursor:pointer;font-size:18px;padding:4px 8px;margin-right:4px}#fileview{width:100%}}
#menu-toggle{display:none}

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

#term-panel{position:fixed;left:230px;right:0;bottom:0;height:220px;background:var(--pre-bg);border-top:1px solid var(--sidebar-border);display:none;flex-direction:column;z-index:50;font-family:Consolas,monospace}
#term-panel.open{display:flex}
#term-bar{padding:4px 10px;background:var(--sidebar);border-bottom:1px solid var(--sidebar-border);display:flex;align-items:center;gap:8px}
#term-bar .t-title{font-size:11px;font-weight:600;color:var(--st-c)}
#term-out{flex:1;overflow-y:auto;padding:6px 10px;font-size:12px;white-space:pre-wrap;word-break:break-all;line-height:1.4}
#term-out .t-cmd{color:var(--accent);font-weight:600}
#term-out .t-done{color:var(--st-c)}
#term-in{display:flex;border-top:1px solid var(--sidebar-border)}
#term-in input{flex:1;background:transparent;border:none;color:var(--fg);font-family:inherit;font-size:12px;padding:6px 10px;outline:none}
#term-in .t-kill{background:var(--cnl-btn);color:#fff;border:none;padding:0 12px;cursor:pointer;font-size:11px}
</style></head><body>
<div id="sidebar">
  <div class="logo"><svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>OpenCode <span>v2</span></div>
  <div style="display:flex;align-items:center;gap:4px;padding:6px 12px;border-bottom:1px solid var(--sidebar-border)">
    <select id="project-select" onchange="switchProject(this.value)" style="flex:1;font-size:11px;padding:3px 6px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;color:var(--fg);outline:none;font-family:inherit"></select>
    <button onclick="addProject()" style="background:none;border:1px dashed var(--sidebar-border);border-radius:4px;color:var(--st-c);cursor:pointer;font-size:14px;padding:1px 6px;line-height:1">+</button>
  </div>
  <div class="section">Sessions <span class="count" id="sess-count">0</span></div>
  <div id="new-sess-btn" onclick="newSession()"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>New Session</div>
  <div style="display:flex;gap:4px;margin:4px 12px">
    <button onclick="exportSession()" style="flex:1;padding:4px 8px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;cursor:pointer;font-size:10px;color:var(--st-c);font-family:inherit">Export</button>
    <button onclick="importSession()" style="flex:1;padding:4px 8px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;cursor:pointer;font-size:10px;color:var(--st-c);font-family:inherit">Import</button>
  </div>
  <input id="sess-search" placeholder="Search sessions..." oninput="filterSessions(this.value)">
  <div id="sess-list"></div>
  <div class="section">Agents</div>
  <div style="display:flex;gap:4px;padding:4px 12px;flex-wrap:wrap">
    <button onclick="useAgent('explore')" style="padding:3px 8px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;cursor:pointer;font-size:10px;color:var(--st-c);font-family:inherit">@explore</button>
    <button onclick="useAgent('scout')" style="padding:3px 8px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;cursor:pointer;font-size:10px;color:var(--st-c);font-family:inherit">@scout</button>
    <button onclick="useAgent('general')" style="padding:3px 8px;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;cursor:pointer;font-size:10px;color:var(--st-c);font-family:inherit">@general</button>
  </div>
  <div class="section">Skills</div>
  <div id="skills-list" style="padding:4px 12px;font-size:11px;color:var(--st-c);max-height:100px;overflow-y:auto"></div>
  <div class="section">Files</div>
  <div id="tree-wrap"><div id="tree"></div></div>
</div>
<div id="main">
  <div id="topbar">
    <button id="menu-toggle" onclick="toggleSidebar()">☰</button>
    <select id="chm" style="width:160px"></select>
    <button onclick="pullModel()" title="Pull model" style="background:var(--btn);color:#fff;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px">+Pull</button>
    <button onclick="delModel()" title="Delete model" style="background:var(--cnl-btn);color:#fff;border:none;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:11px">-Del</button>
    <span class="badge" id="model-badge">Model</span>
    <span id="prj"></span>
    <span id="st2"></span><a href="/docs" target="_blank" style="font-size:11px;color:var(--st-c);text-decoration:none;margin-left:8px">API</a><button onclick="toggleTerm()" title="Terminal" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:14px;margin-left:8px">&#9654;_</button><button id="theme-btn" onclick="toggleTheme()" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:16px;margin-left:8px">&#127769;</button>
  </div>
  <div id="chat">
    <div id="msgs"><div class="msg s">Agent ready. Try: &quot;create a fibonacci function&quot;</div></div>
    <div id="inp">
      <textarea id="ta" rows="1" placeholder="Ask something... /test /review /fix /doc /deploy"></textarea>
      <div id="hint-box"></div>
      <div style="display:flex;flex-direction:column;gap:4px;align-self:flex-end">
        <button id="snd" onclick="send()" style="height:auto;padding:4px 14px">Send</button>
        <button id="cnl" onclick="cancel()" style="display:none;height:auto;padding:4px 14px">Cancel</button>
      </div>
    </div>
  </div>
  <div id="stat"><span id="old"></span><span id="ols">Ollama...</span></div>
</div>
<div id="fileview"><div class="fv-bar"><div id="fv-tabs" style="display:flex;gap:2px;overflow-x:auto;flex:1"></div><button id="fv-save" onclick="saveFile()" style="display:none;background:var(--btn);color:#fff;border:none;border-radius:4px;padding:4px 12px;cursor:pointer;font-size:11px">Save (Ctrl+S)</button><button class="fv-close" onclick="closeFile()">&times;</button></div><div id="fv-content" style="flex:1;padding:0;overflow:hidden;background:var(--pre-bg);margin:0;font-family:monospace;white-space:pre"></div></div>
<div id="term-panel">
  <div id="term-bar"><span class="t-title">Terminal</span><span id="term-cwd" style="font-size:10px;color:var(--st-c)"></span></div>
  <div id="term-out"></div>
  <div id="term-in"><input id="term-input" placeholder="Run command... (Enter to run, Ctrl+C to kill)"><button class="t-kill" onclick="termKill()">Kill</button></div>
</div>
<div id="dropzone"><div class="dz-box"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg><div class="dz-title">Drop files here</div><div class="dz-sub">Upload to workspace</div></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/python/python.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/javascript/javascript.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/xml/xml.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/css/css.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/htmlmixed/htmlmixed.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/markdown/markdown.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/json/json.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/shell/shell.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/go/go.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/rust/rust.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/clike/clike.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/yaml/yaml.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldcode.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/fold/foldgutter.min.js"></script>
<script>
var CM_READY = typeof CodeMirror !== 'undefined';
</script>
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
  h=h.replace(/\[QUESTION\]\s*(.*?)(?:\n(\d+\.\s*.*(?:\n\d+\.\s*.*)*))?/g,function(_,q,o){
    var html='<div class="confirm-box"><div class="c-title">Question</div><div class="c-args">'+esc(q)+'</div>';
    if(o){
      o.split('\n').forEach(function(opt,i){
        var val=opt.replace(/^\d+\.\s*/,'').trim();
        if(val) html+='<button class="c-yes" onclick="answerQuestion(\''+esc(val)+'\')" style="margin:3px">'+esc(val)+'</button>';
      });
    }
    return html+'</div>';
  });
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
// CodeMirror editor with tabs
var openTabs=[],curTab=null,cmEditor=null;
function langFor(path){
  var ext=('.'+path).split('.').pop().toLowerCase();
  var map={py:'python',js:'javascript',jsx:'javascript',ts:'javascript',tsx:'javascript',mjs:'javascript',
    html:'htmlmixed',htm:'htmlmixed',vue:'htmlmixed',css:'css',scss:'css',md:'markdown',
    json:'json',jsonc:'json',sh:'shell',bat:'shell',ps1:'shell',go:'go',rs:'rust',
    c:'clike',h:'clike',cpp:'clike',cc:'clike',java:'clike',cs:'clike',yaml:'yaml',yml:'yaml',toml:'shell'};
  return map[ext]||'';
}
function makeEditor(el){
  if(!CM_READY){
    var ta=document.createElement('textarea');
    ta.style.cssText='width:100%;height:100%;background:var(--pre-bg);color:var(--fg);border:none;outline:none;font-family:monospace;font-size:12px;padding:12px;resize:none';
    el.appendChild(ta);
    return {getValue:function(){return ta.value},setValue:function(v){ta.value=v},refresh:function(){},getWrapperElement:function(){return ta}};
  }
  var cm=CodeMirror(el,{
    value:'',lineNumbers:true,matchBrackets:true,theme:'dracula',
    foldGutter:true,gutters:['CodeMirror-linenumbers','CodeMirror-foldgutter'],
    tabSize:2,indentUnit:2,lineWrapping:false
  });
  cm.setOption('extraKeys',{'Ctrl-S':function(){saveFile()},'Cmd-S':function(){saveFile()},'Ctrl-Space':function(){editorComplete()}});
  return cm;
}
function openFile(path){
  fetch(A+'/api/file?path='+encodeURIComponent(path)).then(function(r){return r.json()}).then(function(d){
    if(d.error)return;
    if(openTabs.indexOf(path)<0)openTabs.push(path);
    curTab=path;renderTabs();renderEditor(d.content,path);$('fileview').classList.add('open');
  });
}
function renderTabs(){
  var el=$('fv-tabs');
  el.innerHTML=openTabs.map(function(p){
    return '<span onclick="selectTab(\''+p.replace(/'/g,"\\'")+'\')" style="padding:3px 10px;font-size:11px;cursor:pointer;border-radius:4px;white-space:nowrap;'+(p===curTab?'background:var(--accent);color:#fff':'background:var(--code-bg);color:var(--fg)')+'">'+esc(p.split('/').pop())+' <span onclick="event.stopPropagation();closeTab(\''+p.replace(/'/g,"\\'")+'\')" style="opacity:.6">&times;</span></span>';
  }).join('');
}
function selectTab(p){curTab=p;renderTabs();fetch(A+'/api/file?path='+encodeURIComponent(p)).then(function(r){return r.json()}).then(function(d){if(!d.error)renderEditor(d.content,p)})}
function closeTab(p){
  openTabs.splice(openTabs.indexOf(p),1);
  if(curTab===p){curTab=openTabs.length?openTabs[openTabs.length-1]:null;
    if(curTab){fetch(A+'/api/file?path='+encodeURIComponent(curTab)).then(function(r){return r.json()}).then(function(d){if(!d.error)renderEditor(d.content,curTab)})}
    else{if(cmEditor)cmEditor.getWrapperElement().remove();cmEditor=null;$('fv-save').style.display='none'}}
  renderTabs();if(!openTabs.length)closeFile();
}
function renderEditor(content,path){
  var el=$('fv-content');el.innerHTML='';
  if(cmEditor)cmEditor.getWrapperElement().remove();
  cmEditor=makeEditor(el);
  cmEditor.setValue(content);
  if(CM_READY)cmEditor.setOption('mode',langFor(path));
  $('fv-save').style.display='inline-block';
  setTimeout(function(){cmEditor.refresh&&cmEditor.refresh()},50);
}
function saveFile(){
  if(!curTab||!cmEditor)return;
  fetch(A+'/api/file',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:curTab,content:cmEditor.getValue()})})
  .then(function(r){return r.json()}).then(function(d){
    if(d.error)am('t err','Save error: '+d.error);
    else{am('t ok','Saved: '+esc(curTab));loadFiles()}
  }).catch(function(e){am('t err','Save failed: '+e.message)});
}
function closeFile(){$('fileview').classList.remove('open')}
function editorComplete(){
  if(!curTab||!cmEditor)return;
  var pos=cmEditor.getCursor(),txt=cmEditor.getValue();
  fetch(A+'/api/lsp/completion',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({path:curTab,text:txt,line:pos.line,character:pos.ch})})
  .then(function(r){return r.json()}).then(function(d){
    if(!d.items||!d.items.length)return;
    var cw=cmEditor.getWrapperElement(),rect=cw.getBoundingClientRect();
    var tip=document.createElement('div');
    tip.style.cssText='position:fixed;z-index:1000;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;max-height:220px;overflow-y:auto;min-width:240px;box-shadow:0 4px 16px rgba(0,0,0,.35)';
    d.items.forEach(function(it,i){
      var row=document.createElement('div');
      row.style.cssText='padding:4px 10px;font-family:Consolas,monospace;font-size:12px;cursor:pointer;color:var(--fg);display:flex;justify-content:space-between;gap:16px';
      row.innerHTML='<span>'+esc(it.label)+'</span><span style="color:var(--st-c);font-size:10px;white-space:nowrap">'+esc((it.detail||'').slice(0,40))+'</span>';
      row.onmousedown=function(ev){ev.preventDefault();var cur=cmEditor.getCursor();cmEditor.replaceRange(it.insertText||it.label,cur);document.body.removeChild(tip)};
      row.onmouseenter=function(){d.items.forEach(function(_,j){rows[j].style.background='transparent'});this.style.background='var(--accent)'};
      tip.appendChild(row);
    });
    var rows=tip.children;
    tip.style.left=Math.min(rect.left+pos.ch*7+10,window.innerWidth-260)+'px';
    tip.style.top=(rect.top+22)+'px';
    var hd=function(e){if(!tip.parentNode)return;if(!tip.contains(e.target)){document.body.removeChild(tip);document.removeEventListener('mousedown',hd,true)}};
    document.addEventListener('mousedown',hd,true);
    document.body.appendChild(tip);
  }).catch(function(){});
}
function closeFile(){$('fileview').classList.remove('open')}

// Init
function toggleTheme(){var d=document.body.getAttribute("data-theme")==="dark";document.body.setAttribute("data-theme",d?"":"dark");$("theme-btn").textContent=d?"&#127769;":"&#9728;&#65039;";localStorage.setItem("theme",d?"":"dark")}
if(localStorage.getItem("theme")==="dark"){document.body.setAttribute("data-theme","dark");$("theme-btn").textContent="&#9728;&#65039;"}
function exportSession(){
  if(!curSid){alert('No active session');return}
  fetch(A+'/api/sessions/'+curSid+'/export').then(function(r){return r.json()}).then(function(d){
    var blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'});
    var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=curSid+'.json';a.click()
  })
}
function importSession(){
  var inp=document.createElement('input');inp.type='file';inp.accept='.json';
  inp.onchange=function(e){
    var file=e.target.files[0];if(!file)return;
    var reader=new FileReader();
    reader.onload=function(ev){
      fetch(A+'/api/sessions/import',{method:'POST',headers:{'Content-Type':'application/json'},body:ev.target.result})
      .then(function(r){return r.json()}).then(function(s){alert('Imported: '+s.title);loadSessions()})
    };reader.readAsText(file)
  };inp.click()
}
function loadSkills(){
  fetch(A+'/api/skills').then(function(r){return r.json()}).then(function(sk){
    var el=$('skills-list');
    if(!sk.length){el.innerHTML='<span style="color:var(--st-c);font-size:10px">No skills. Create .agent_skills/*.md</span>';return}
    el.innerHTML=sk.map(function(s){return '<span style="cursor:pointer;margin-right:6px;padding:1px 5px;background:var(--code-bg);border-radius:3px" onclick="loadSkill(\''+s.name+'\')">'+esc(s.name)+'</span>'}).join('')
  }).catch(function(){})
}
function loadSkill(name){$('ta').value='@skill '+name;ah()}
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open')}
function useAgent(type){var ta=$('ta');ta.value='@'+type+' ';ta.focus();ah()}

// Project management
function loadProjects(){
  fetch(A+'/api/projects').then(function(r){return r.json()}).then(function(ps){
    var sel=$('project-select');
    if(!ps.length){sel.innerHTML='<option>No projects</option>';return}
    sel.innerHTML=ps.map(function(p){return '<option value="'+esc(p.path)+'"'+(p.active?' selected':'')+'>'+esc(p.name)+'</option>'}).join('');
    if(ps.some(function(p){return p.active}))loadFiles();loadSessions();
  }).catch(function(){});
}
function switchProject(path){
  fetch(A+'/api/projects/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path})})
  .then(function(r){return r.json()}).then(function(d){
    curSid='';ms=[];$('msgs').innerHTML='<div class="msg s">Switched to: '+esc(d.project.name)+'</div>';
    loadProjects();loadFiles();loadSessions();$('ta').focus();
  }).catch(function(e){alert('Error: '+e.message)});
}
function addProject(){
  var name=prompt('Project name:','New Project');if(!name)return;
  var path=prompt('Project path (absolute):',A.replace('http://localhost:8765','').replace('http://localhost:','')||'C:\\projects\\'+name);if(!path)return;
  fetch(A+'/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,path:path})})
  .then(function(r){return r.json()}).then(function(d){loadProjects()}).catch(function(e){alert('Error')});
}

function init(){
  fetch(A+'/api/models').then(function(r){return r.json()}).then(function(mm){
    $('chm').innerHTML=mm.map(function(m){return '<option>'+m+'</option>'}).join('');
    var ds=mm.find(function(m){return m.includes('deepseek')});
    if(ds){$('chm').value=ds;$('model-badge').textContent='DeepSeek'}
  }).catch(function(){});
  fetch(A+'/api/project').then(function(r){return r.json()}).then(function(p){$('prj').textContent=p.name}).catch(function(){});
  loadProjects();loadFiles();loadSessions();loadSkills();loadTabPaths();cl();$('ta').focus();
}
function cl(){fetch(A+'/api/models').then(function(){$('old').className='g';$('ols').textContent='Ollama OK'}).catch(function(){$('old').className='r';$('ols').textContent='Ollama -';setTimeout(cl,3000)})}

// Slash commands config
var SLASH_COMMANDS={
  'test': {icon:'🧪',desc:'Run tests',prompt:'Run the project tests and report results.'},
  'deploy': {icon:'🚀',desc:'Deploy project',prompt:'Prepare a deployment plan for this project.'},
  'review': {icon:'🔍',desc:'Review changes',prompt:'Review all uncommitted changes and suggest improvements.'},
  'fix': {icon:'🔧',desc:'Fix errors',prompt:'Find and fix any errors in the codebase.'},
  'doc': {icon:'📝',desc:'Generate docs',prompt:'Generate documentation for the project.'},
};

function send(){
  var ta=$('ta'),txt=ta.value.trim();if(!txt||sd)return;
  hist.unshift(txt);if(hist.length>50)hist.pop();histIdx=0;
  ta.value='';ah();
  // Handle @agent and @skill shortcuts
  var agentMatch=txt.match(/^@(explore|scout|general)\s+(.*)/);
  var skillMatch=txt.match(/^@skill\s+(\w+)\s*(.*)/);
  var slashMatch=txt.match(/^\/(\w+)\s*(.*)/);
  if(agentMatch){var agent=agentMatch[1],prompt=agentMatch[2];am('u',fm('[@'+agent+'] '+prompt));ms.push({role:'user',content:'[@'+agent+'] '+prompt});sd=1;$('snd').disabled=1;$('cnl').style.display='inline-block';ac=new AbortController();var fl='',be=am('a','<span class="sp"></span>');$('st2').textContent='['+agent+']...';fetch(A+'/api/task/'+agent+'?prompt='+encodeURIComponent(prompt)).then(function(r){return r.json()}).then(function(d){fl=d.result||'No response';ms.push({role:'assistant',content:fl});be.innerHTML=fm(fl);sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent=''}).catch(function(e){be.innerHTML='Error: '+esc(e.message);sd=0;$('snd').disabled=0;$('cnl').style.display='none'});return}
  if(skillMatch){var sk=skillMatch[1];fetch(A+'/api/skills').then(function(r){return r.json()}).then(function(skills){var found=skills.find(function(s){return s.name===sk});if(found){txt='I loaded the '+sk+' skill. '+found.preview+(skillMatch[2]?'\n\n'+skillMatch[2]:'')}else{txt='Skill "'+sk+'" not found'};am('u',fm(txt));ms.push({role:'user',content:txt})});}
  // Handle slash commands
  if(slashMatch){
    var cmd=SLASH_COMMANDS[slashMatch[1]];
    if(cmd){txt=cmd.prompt+(slashMatch[2]?'\n\n'+slashMatch[2]:'');am('u',fm('/'+slashMatch[1]+' '+slashMatch[2]));ms.push({role:'user',content:txt})}
    else{am('t err','Unknown command: /'+slashMatch[1]+'. Available: '+Object.keys(SLASH_COMMANDS).join(', '));return}
  }
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
function answerQuestion(val){am('u',fm(val));ms.push({role:'user',content:val});send()}

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
  var msgEl=am('t info','<span class="sp"></span> Pulling <b>'+esc(name)+'</b>...');
  var evtSrc=new EventSource(A+'/api/models/pull/stream?name='+encodeURIComponent(name));
  evtSrc.onmessage=function(e){
    if(e.data=='[DONE]'){msgEl.innerHTML='<span style="color:var(--diff-add-fg)">✅ Pulled: '+esc(name)+'</span>';evtSrc.close();init();btn.disabled=0;btn.textContent='+Pull'}
    else{try{var d=JSON.parse(e.data);msgEl.innerHTML='<span class="sp"></span> '+esc(d.status||d.digest||e.data)}catch(ex){msgEl.innerHTML='<span class="sp"></span> '+esc(e.data)}}
  };
  evtSrc.onerror=function(){evtSrc.close();msgEl.innerHTML='❌ Error pulling '+esc(name);btn.disabled=0;btn.textContent='+Pull'};
}
function delModel(){
  var sel=$('chm'),name=sel.value;if(!confirm('Delete "'+name+'"?'))return;
  var btn=event.target;btn.disabled=1;btn.textContent='...';
  fetch(A+'/api/models/'+encodeURIComponent(name),{method:'DELETE'})
  .then(function(r){return r.json()}).then(function(d){alert(d.status||'deleted');init()})
  .catch(function(e){alert('Error')}).finally(function(){btn.disabled=0;btn.textContent='-Del'});
}

// Tab completion for paths
var tabPaths=[], tabIdx=0;
function loadTabPaths(){
  fetch(A+'/api/files?path=').then(function(r){return r.json()}).then(function(d){
    tabPaths=[];
    function walk(nodes,prefix){nodes.forEach(function(n){var p=prefix+n.name;tabPaths.push(p);if(n.children)walk(n.children,p+'/')})}
    walk(d.tree||[],'');
  }).catch(function(){})
}
function completeTab(){
  var ta=$('ta'),val=ta.value,cursor=ta.selectionStart;
  var before=val.slice(0,cursor),after=val.slice(cursor);
  var wordMatch=before.match(/([\w\/\\\.\-]+)$/);
  if(wordMatch){
    var partial=wordMatch[1].toLowerCase();
    var matches=tabPaths.filter(function(p){return p.toLowerCase().includes(partial)});
    if(matches.length){
      var match=matches[tabIdx%matches.length];
      ta.value=before.slice(0,-partial.length)+match+after;
      ta.selectionStart=ta.selectionEnd=before.length-partial.length+match.length;
      tabIdx=(tabIdx+1)%matches.length;
      ah();return;
    }
  }
  var hint=$('hint-box');
  if(hint&&hint._items&&hint._items.length){
    var items=hint._items;
    var it=items[hint._idx%items.length];
    ta.value=before.slice(0,-it._partial.length)+it.value+after;
    ta.selectionStart=ta.selectionEnd=before.length-it._partial.length+it.value.length;
    hint.style.display='none';ah();
  }
}
// Autocomplete hints: @files, /commands, #skills
function showHints(){
  var ta=$('ta'),val=ta.value,cursor=ta.selectionStart;
  var before=val.slice(0,cursor);
  var hint=$('hint-box');if(!hint)return;
  var m=before.match(/([@/#][\w\/\\\.\-]*)$/);
  if(!m){hint.style.display='none';return}
  var prefix=m[1],q=prefix.slice(1).toLowerCase(),items=[];
  if(prefix[0]=='/'){
    Object.keys(SLASH_COMMANDS).forEach(function(k){if(k.startsWith(q))items.push({value:'/'+k+' ',label:'/'+k+' — '+SLASH_COMMANDS[k].desc,_partial:prefix})});
  }else if(prefix[0]=='#'){
    fetch(A+'/api/skills').then(function(r){return r.json()}).then(function(sk){
      var it=sk.filter(function(s){return s.name.startsWith(q)}).map(function(s){return {value:'@skill '+s.name+' ',label:'#'+s.name,_partial:prefix}});
      if(it.length)showHintBox(it,cursor);else hideHint();
    });return;
  }else if(prefix[0]=='@'){
    ['explore','scout','general'].forEach(function(a){if(a.startsWith(q))items.push({value:'@'+a+' ',label:'@'+a,_partial:prefix})});
  }
  if(items.length)showHintBox(items,cursor);else hideHint();
}
function showHintBox(items,cursor){
  var ta=$('ta'),hint=$('hint-box');if(!hint)return;
  hint.innerHTML=items.map(function(it,i){return '<div class="hint-item'+(i===0?' sel':'')+'" data-i="'+i+'">'+esc(it.label)+'</div>'}).join('');
  hint._items=items;hint._idx=0;hint._cursor=cursor;
  var r=ta.getBoundingClientRect();hint.style.left=r.left+'px';hint.style.top=(r.top-hint.offsetHeight-4)+'px';
  hint.style.display='block';
  hint.querySelectorAll('.hint-item').forEach(function(el){
    el.onmousedown=function(ev){ev.preventDefault();applyHint(+el.getAttribute('data-i'))};
    el.onmouseenter=function(){hint._idx=+el.getAttribute('data-i');hint.querySelectorAll('.hint-item').forEach(function(e,i){e.classList.toggle('sel',i===hint._idx)})};
  });
}
function hideHint(){var h=$('hint-box');if(h)h.style.display='none'}
function applyHint(i){
  var ta=$('ta'),hint=$('hint-box'),it=hint._items[i];
  var before=ta.value.slice(0,hint._cursor),after=ta.value.slice(hint._cursor);
  ta.value=before.slice(0,-it._partial.length)+it.value+after;
  ta.selectionStart=ta.selectionEnd=hint._cursor-it._partial.length+it.value.length;
  hint.style.display='none';ah();
}
var hist=[],histIdx=0;
$('ta').addEventListener('keydown',function(e){
  if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();send()}
  else if(e.key=='Tab'){e.preventDefault();completeTab()}
  else if(e.key=='ArrowUp'&&!$('ta').value.trim()&&histIdx<hist.length-1){histIdx++;$('ta').value=hist[histIdx];ah()}
  else if(e.key=='ArrowDown'&&histIdx>0){histIdx--;$('ta').value=hist[histIdx];ah()}
  else if(e.key!='Tab')setTimeout(showHints,80);
});
$('ta').addEventListener('input',ah);init();

// ─── Terminal ─────────────────────────────────────────────
var termBusy=false,termHist=[],termHIdx=0,termAbc=null;
function toggleTerm(){var p=$('term-panel');p.classList.toggle('open');if(p.classList.contains('open')){var ti=$('term-input');ti.focus()}}
function termCwd(){return $('prj').getAttribute('data-path')||''}
function termPrint(line,cls){
  var out=$('term-out');if(!line&&cls!='t-done')return;
  var d=document.createElement('div');if(cls)d.className=cls;
  d.textContent=line;out.appendChild(d);out.scrollTop=out.scrollHeight;
}
function termRun(cmd){
  if(!cmd)return;termPrint('$ '+cmd,'t-cmd');
  termHist.unshift(cmd);if(termHist.length>50)termHist.pop();termHIdx=-1;
  termBusy=true;termPrint('',null);termPrint('running...','t-done');
  var body=JSON.stringify({cmd:cmd,cwd:termCwd()});
  var ctrl=new AbortController();termAbc=ctrl;
  fetch(A+'/api/terminal',{method:'POST',headers:{'Content-Type':'application/json'},body:body,signal:ctrl.signal})
    .then(function(r){
      if(!r.ok)throw new Error('HTTP '+r.status);
      var rd=r.body.getReader(),dec=new TextDecoder(),buf='';
      function pump(){
        return rd.read().then(function(res){
          if(res.done){finish(null);return}
          buf+=dec.decode(res.value,{stream:true});
          var i;
          while((i=buf.indexOf('\n\n'))>=0){
            var chunk=buf.slice(0,i);buf=buf.slice(i+2);
            if(chunk.startsWith('data: ')){
              try{
                var d=JSON.parse(chunk.slice(6));
                if(d.done){finish(d.code);continue}
                termPrint(d.line);
              }catch(e){}
            }
          }
          return pump();
        });
      }
      function finish(code){
        var last=$('term-out').lastElementChild;
        if(last&&last.textContent=='running...')last.remove();
        if(code!=null)termPrint('exit code: '+code,'t-done');
        termBusy=false;termAbc=null;
      }
      pump();
    })
    .catch(function(e){
      var last=$('term-out').lastElementChild;
      if(last&&last.textContent=='running...')last.remove();
      termPrint('Error: '+e.message,'t-done');termBusy=false;termAbc=null;
    });
}
function termKill(){
  if(termAbc){termAbc.abort();termAbc=null}
  fetch(A+'/api/terminal/kill',{method:'POST'});
  termPrint('(killed)','t-done');termBusy=false;
}
$('term-input').addEventListener('keydown',function(e){
  if(e.key=='Enter'){e.preventDefault();var v=this.value;this.value='';termRun(v)}
  else if(e.key=='ArrowUp'&&termHIdx<termHist.length-1){termHIdx++;this.value=termHist[termHIdx]}
  else if(e.key=='ArrowDown'&&termHIdx>0){termHIdx--;this.value=termHist[termHIdx]}
  else if(e.key=='c'&&e.ctrlKey){e.preventDefault();termKill()}
});
</script>
</body></html>"""
