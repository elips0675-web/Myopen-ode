
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
      h+='<div class="'+cls+'" onclick="openSession(\''+s.id+'\')"><div class="sess-title">'+esc(s.title)+'</div><div class="sess-meta"><span class="sess-time">'+timeAgo(s.updated)+'</span><span class="sess-count">'+nmsg+' msgs</span>'+(s.interrupted?'<span class="sess-int" style="color:var(--cnl-btn);font-size:10px;margin-left:6px">&#9888; interrupted</span>':'')+'</div><button class="sess-del" onclick="event.stopPropagation();delSession(\''+s.id+'\')">&times;</button></div>';
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
  ragPoll();
}
function ragPoll(){
  fetch(A+'/api/rag/status').then(function(r){return r.json()}).then(function(s){
    if(s.phase=='indexing'&&s.files_total>$('ragst').textContent){
      $('ragst').textContent='RAG: '+s.files_done+'/'+s.files_total;
    } else if(s.phase=='indexing'){
      $('ragst').textContent='RAG: '+s.files_done+'/'+s.files_total;
    } else if(s.chunks>$('ragst')._c||s.phase=='idle'){
      $('ragst').textContent=s.chunks?('RAG: '+s.chunks+' chunks'):'';
    }
    $('ragst')._c=s.chunks;
    setTimeout(ragPoll,5000);
  }).catch(function(){setTimeout(ragPoll,10000)});
}
function showAudit(){
  var w=window.open('','audit','width=700,height=500');
  if(!w){alert('Popup blocked — allow popups to view the audit log');return}
  fetch(A+'/api/audit?limit=100').then(function(r){return r.json()}).then(function(d){
    w.document.write('<html><head><title>Audit log</title><style>body{background:#111;color:#ddd;font:12px monospace;padding:10px;white-space:pre-wrap;word-break:break-all}</style></head><body>'+
      (d.lines?esc(d.lines.join('\n')):(d.error||'empty'))+'</body></html>');w.document.close();
  }).catch(function(e){w.document.write('Error: '+e.message);w.document.close()});
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
    var tl=null,tlCount=0;
    function toolLine(name,args,result){
      if(!tl){tl=document.createElement('div');tl.className='tline';be.parentNode.appendChild(tl)}
      var short=(args&&(args.path||args.cmd||args.pattern||args.query))?' '+(args.path||args.cmd||args.pattern||args.query).toString().slice(0,60):'';
      tl.innerHTML='<span class="tldone">&#10003;</span> <b>'+esc(name)+'</b>'+esc(short);
      if(result&&result.toString().toLowerCase().includes('error'))tl.className='tline terr';
      tlCount++;
    }
    fetch(A+'/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({model:m,messages:ms,session_id:curSid}),signal:ac.signal})
  .then(function(r){if(!r.ok)throw Error(r.status);
    var rd=r.body.getReader(),dc=new TextDecoder(),bf='';
    (function rd2(){rd.read().then(function(v){
      if(v.done){ms.push({role:'assistant',content:fl});be.innerHTML=fm(fl)||'(empty)';sd=0;$('snd').disabled=0;$('cnl').style.display='none';$('st2').textContent='';loadFiles();return}
      bf+=dc.decode(v.value,{stream:1});var ls=bf.split('\n');bf=ls.pop()||'';
      ls.forEach(function(l){if(l.startsWith('data: ')){try{var d=JSON.parse(l.slice(6));
        if(d.text){fl+=d.text}
        else if(d.tool){
          if(d.tool.type=='status')$('st2').textContent=d.tool.msg;
          else if(d.tool.type=='tool')toolLine(d.tool.name,d.tool.args,d.tool.result);
        }
      }catch(e){}}});
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

// ─── Terminal (xterm.js + WebSocket) ───────────────────────
var term=null,termWs=null,termBuf='',termHist=[],termHIdx=0;
function toggleTerm(){
  var p=$('term-panel');p.classList.toggle('open');
  if(p.classList.contains('open'))termStart();else termClose();
}
function termCwd(){return $('prj').getAttribute('data-path')||''}
function termStart(){
  if(term)return;
  if(typeof Terminal==='undefined'){termBuf='xterm.js failed to load\n';return}
  term=new Terminal({
    convertEol:true,cursorBlink:true,fontSize:12,
    theme:{background:'#0d1117',foreground:'#e2e8f0',cursor:'#58a6ff',selection:'#264f78'}
  });
  term.open(document.getElementById('xterm-host'));
  term.onData(function(d){if(termWs&&termWs.readyState==1)termWs.send(JSON.stringify({input:d}))});
  term.onResize(function(s){if(termWs&&termWs.readyState==1)termWs.send(JSON.stringify({resize:{cols:s.cols,rows:s.rows}}))});
  term.reset();
  if(termBuf){term.write(termBuf);termBuf=''}
  termShell(null);
}
function termShell(cmd){
  termShellKill();
  var proto=location.protocol=='https:'?'wss://':'ws://';
  termWs=new WebSocket(proto+location.host+'/ws/term');
  termWs.onopen=function(){
    termWs.send(JSON.stringify({cmd:cmd||null,cwd:termCwd(),cols:term.cols,rows:term.rows}));
  };
  termWs.onmessage=function(ev){
    var m;try{m=JSON.parse(ev.data)}catch(e){return}
    if(m.out){term.write(m.out)}
    else if(m.exit!=null){
      term.writeln('\r\n[process exited with code '+m.exit+']');
      termWs=null;
    }
  };
  termWs.onclose=function(){if(termWs===this)termWs=null};
}
function termShellKill(){
  if(termWs&&termWs.readyState==1){try{termWs.send(JSON.stringify({kill:true}))}catch(e){}}
  try{if(termWs)termWs.close()}catch(e){}
  termWs=null;
}
function termClear(){if(term)term.clear()}
function termClose(){termShellKill();if(term){term.dispose();term=null}}
var termCmdInput=null;
window.addEventListener('load',function(){
  termCmdInput=document.getElementById('term-cmd');
  if(!termCmdInput)return;
  termCmdInput.addEventListener('keydown',function(e){
    if(e.key=='Enter'){e.preventDefault();var v=this.value;this.value='';
      if(v){termHist.unshift(v);if(termHist.length>50)termHist.pop();termHIdx=-1}
      termShell(v||null);this.blur();}
    else if(e.key=='ArrowUp'&&termHIdx<termHist.length){termHIdx++;this.value=termHist[termHIdx]}
    else if(e.key=='ArrowDown'&&termHIdx>0){termHIdx--;this.value=termHist[termHIdx]}
    else if(e.key=='c'&&e.ctrlKey){e.preventDefault();termShellKill()}
  });
});
