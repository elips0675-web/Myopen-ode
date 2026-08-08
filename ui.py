"""HTML UI template."""

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>AI Coder v2 — OpenCode Desktop</title>
<link rel="stylesheet" href="/static/vendor/xterm.css">
<link rel="stylesheet" href="/static/vendor/cm/codemirror.min.css">
<link rel="stylesheet" href="/static/vendor/cm/theme/dracula.min.css">
<link rel="stylesheet" href="/static/vendor/cm/addon/fold/foldgutter.min.css">
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

#term-panel{position:fixed;left:230px;right:0;bottom:0;height:240px;background:#0d1117;border-top:1px solid var(--sidebar-border);display:none;flex-direction:column;z-index:50}
#term-panel.open{display:flex}
#term-bar{padding:4px 10px;background:var(--sidebar);border-bottom:1px solid var(--sidebar-border);display:flex;align-items:center;gap:8px}
#term-bar .t-title{font-size:11px;font-weight:600;color:var(--st-c)}
#term-bar input{flex:1;background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;color:var(--fg);font-family:inherit;font-size:11px;padding:3px 8px;outline:none;max-width:320px}
#term-bar button{background:none;border:1px solid var(--sidebar-border);border-radius:4px;color:var(--st-c);cursor:pointer;font-size:11px;padding:2px 8px}
#term-bar button:hover{border-color:var(--accent);color:var(--accent)}
#xterm-host{flex:1;overflow:hidden;padding:4px 0 0 4px}
.tline{font-family:Consolas,monospace;font-size:11px;color:var(--st-c);background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;padding:3px 8px;margin:3px 0;word-break:break-all}
.tline .tldone{color:#4ade80}
.tline.terr{color:#f87171;border-color:rgba(248,113,113,.4)}
.plantree{font-size:11px;color:var(--st-c);background:var(--code-bg);border:1px solid var(--sidebar-border);border-radius:4px;padding:6px 8px;margin:3px 0}
.plantree b{font-size:11px;display:block;margin-bottom:3px}
.plstep{padding:1px 0;word-break:break-all}
.plicon{font-family:Consolas,monospace;margin-right:4px}
.pldone{color:#4ade80}
.plerr{color:#f87171}
.plpend{color:var(--st-c)}
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
    <span class="badge" id="vram-badge" title="GPU VRAM (nvidia-smi)" style="display:none"></span>
    <span id="prj"></span>
    <span id="st2"></span><a href="/docs" target="_blank" style="font-size:11px;color:var(--st-c);text-decoration:none;margin-left:8px">API</a><span id="ragst" style="font-size:11px;color:var(--st-c);margin-left:8px"></span><span id="updst" style="font-size:11px;color:var(--st-c);margin-left:8px"></span><button onclick="showAudit()" title="Action audit log" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:12px;margin-left:8px">&#128203;</button><button onclick="toggleTerm()" title="Terminal" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:14px;margin-left:8px">&#9654;_</button><button id="theme-btn" onclick="toggleTheme()" style="background:none;border:none;color:var(--st-c);cursor:pointer;font-size:16px;margin-left:8px">&#127769;</button>
  </div>
  <div id="chat">
    <div id="msgs"><div class="msg s">Agent ready. Try: &quot;create a fibonacci function&quot;</div></div>
    <div id="inp">
      <textarea id="ta" rows="1" placeholder="Ask something... /test /review /fix /doc /deploy"></textarea>
      <div id="hint-box"></div>
      <div style="display:flex;flex-direction:column;gap:4px;align-self:flex-end">
        <button id="mic" title="Voice input (STT)" style="background:none;border:1px solid var(--inp-border);border-radius:var(--radius);padding:4px 10px;cursor:pointer;font-size:14px">🎤</button>
        <button id="snd" onclick="send()" style="height:auto;padding:4px 14px">Send</button>
        <button id="cnl" onclick="cancel()" style="display:none;height:auto;padding:4px 14px">Cancel</button>
      </div>
    </div>
  </div>
  <div id="stat"><span id="old"></span><span id="ols">Ollama...</span></div>
</div>
<div id="fileview"><div class="fv-bar"><div id="fv-tabs" style="display:flex;gap:2px;overflow-x:auto;flex:1"></div><button id="fv-save" onclick="saveFile()" style="display:none;background:var(--btn);color:#fff;border:none;border-radius:4px;padding:4px 12px;cursor:pointer;font-size:11px">Save (Ctrl+S)</button><button class="fv-close" onclick="closeFile()">&times;</button></div><div id="fv-content" style="flex:1;padding:0;overflow:hidden;background:var(--pre-bg);margin:0;font-family:monospace;white-space:pre"></div></div>
<div id="term-panel">
  <div id="term-bar"><span class="t-title">Terminal</span>
    <input id="term-cmd" placeholder="Run command (Enter)...">
    <button onclick="termShell(null)" title="New shell">&#8635;</button>
    <button onclick="termShellKill()" title="Kill process">&#10005;</button>
    <button onclick="termClear()" title="Clear">&#9003;</button>
    <span id="term-cwd" style="font-size:10px;color:var(--st-c)"></span>
  </div>
  <div id="xterm-host"></div>
</div>
<div id="dropzone"><div class="dz-box"><svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg><div class="dz-title">Drop files here</div><div class="dz-sub">Upload to workspace</div></div></div>















<script src="/static/vendor/cm6.bundle.js"></script>
    <script src="/static/vendor/xterm.min.js"></script>
<script>
var CM_READY = typeof cm6 !== 'undefined';
</script>
<script src="/static/app.js"></script>
</body></html>"""
