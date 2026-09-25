/* No API keys here. FastAPI serves this frontend and receives the CSV + rules. */
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let savedConfig = null;
let result = null;
let busy = false;
const storageKey = 'review-radar-company-v2';
const statusNames = {matched:'Matched',needs_review:'Needs review',irrelevant:'Irrelevant',duplicate:'Exact duplicate',no_action:'No action requested',empty:'Empty feedback'};
function notify(message) { $('notice').textContent = message; }
function newId() { return 'r_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2,9); }
function addRule(rule = {}) {
  const row = document.createElement('div');
  row.className = 'rule'; row.dataset.id = rule.id || newId();
  row.innerHTML = `<input data-key="label" aria-label="Problem name" placeholder="e.g. Payment problems" required minlength="2" maxlength="100" value="${escapeHTML(rule.label || '')}"><input data-key="phrases" aria-label="Keywords or phrases, separated by commas" placeholder="payment failed, charged twice, refund delay" required value="${escapeHTML((rule.phrases || []).join(', '))}"><select data-key="priority" aria-label="Company priority"><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select><button type="button" class="remove" aria-label="Remove this problem">×</button>`;
  row.querySelector('select').value = rule.priority || 'medium';
  row.querySelector('button').onclick = () => { if ($('rules').children.length === 1) { notify('Keep at least one problem topic.'); return; } row.remove(); invalidate(); };
  $('rules').append(row);
}
function invalidate() {
  savedConfig = null; result = null;
  document.querySelector('[data-page="results"]').disabled = true;
}
function getConfig() {
  if (!$('settings-form').reportValidity()) return null;
  const rules = [...$('rules').children].map(row => ({id:row.dataset.id,label:row.querySelector('[data-key="label"]').value.trim(),phrases:[...new Set(row.querySelector('[data-key="phrases"]').value.split(',').map(x=>x.trim()).filter(Boolean))],priority:row.querySelector('select').value}));
  const company=$('company').value.trim(), context=$('context').value.trim();
  if (company.length<2 || context.length<10) { notify('Enter a company name and at least 10 characters describing the product.'); return null; }
  if (rules.some(r => r.label.length<2 || !r.phrases.length || r.phrases.length>20 || r.phrases.some(p=>p.length>200))) { notify('Each problem needs a name and 1–20 phrases, up to 200 characters each.'); return null; }
  if (new Set(rules.map(r=>r.label.toLowerCase())).size !== rules.length) { notify('Use a distinct problem name for each topic.'); return null; }
  return {company,context,rules};
}
function saveSettings() {
  const config=getConfig(); if (!config) return false;
  if (JSON.stringify(savedConfig)!==JSON.stringify(config)) { result=null; document.querySelector('[data-page="results"]').disabled=true; }
  savedConfig=config;
  try { localStorage.setItem(storageKey,JSON.stringify(config)); } catch { notify('Browser storage is unavailable. Settings will last for this page session only.'); }
  return true;
}
function showPage(page) {
  if (busy) return;
  if (page==='upload' && !savedConfig) { if (!saveSettings()) { page='settings'; } }
  if (page==='results' && !result) { notify('Upload and analyze a CSV first.'); return; }
  document.querySelectorAll('.page').forEach(p=>p.hidden=p.id!==page);
  document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===page));
  if (page==='upload') $('company-summary').textContent=`${savedConfig.company} · ${savedConfig.rules.length} configured problem topics`;
  window.scrollTo({top:0,behavior:'auto'});
}
function loadSettings(config) {
  $('company').value=config.company || ''; $('context').value=config.context || ''; $('rules').replaceChildren();
  (Array.isArray(config.rules)&&config.rules.length?config.rules.slice(0,30):[{}]).forEach(addRule);
}
$('settings-form').addEventListener('input',invalidate);
$('settings-form').addEventListener('change',invalidate);
$('settings-form').addEventListener('submit',e=>{e.preventDefault();notify('');if(saveSettings())showPage('upload');});
$('add-rule').onclick=()=>{if($('rules').children.length>=30){notify('Maximum 30 problem topics.');return;}addRule();invalidate();};
$('example').onclick=()=>{loadSettings({company:'Acme Shop',context:'An online shopping app with product browsing, payments, checkout, order history and account settings.',rules:[{id:'payments',label:'Payment problems',phrases:['payment failed','money deducted','charged twice','checkout error','refund delay'],priority:'high'},{id:'ui',label:'UI improvements',phrases:['confusing navigation','hard to find settings','unclear menu icons','text labels'],priority:'low'}]});invalidate();notify('Example settings loaded. Replace these with your company’s topics or use them with the sample CSV.');};
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>showPage(b.dataset.page));
document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>showPage(b.dataset.go));
$('csv').addEventListener('change',()=>{const f=$('csv').files[0];$('file-info').textContent=f?`${f.name} · ${(f.size/1024).toFixed(1)} KB`:'No file selected';$('analyze').disabled=!f;notify('');});
function setBusy(value) {
  busy=value; $('working').hidden=!value;
  document.querySelectorAll('button,input,select,textarea').forEach(el=>{if(value){el.dataset.wasDisabled=String(el.disabled);el.disabled=true;}else{el.disabled=el.dataset.wasDisabled==='true';delete el.dataset.wasDisabled;}});
}
$('analyze').onclick=async()=>{
  const file=$('csv').files[0];if(!file||!savedConfig)return;
  if(!/\.csv$/i.test(file.name)||file.size>5*1024*1024){notify('Choose a .csv file smaller than 5 MB.');return;}
  notify('');result=null;document.querySelector('[data-page="results"]').disabled=true;
  const body=new FormData();body.append('file',file);body.append('config',JSON.stringify(savedConfig));
  setBusy(true);
  try {
    const response=await fetch('/analyze',{method:'POST',body});
    let data;try{data=await response.json();}catch{throw new Error('The server returned an unreadable response. Check the backend terminal.');}
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Analysis failed. Check the CSV and company settings.');
    if(!Array.isArray(data.issues)||!Array.isArray(data.audit)||!data.summary)throw new Error('Unexpected API response. Use the backend files supplied with this frontend.');
    result=data;renderResults();
  } catch(error) {notify(error instanceof TypeError?'Could not reach the backend. Open this app through http://127.0.0.1:8000 and keep the server running.':error.message);}
  finally {setBusy(false);if(result){document.querySelector('[data-page="results"]').disabled=false;showPage('results');}}
};
function renderResults() {
  const s=result.summary;$('result-company').textContent=`${result.company} · Ranked using your company priorities and the uploaded feedback.`;
  const metrics=[['CSV records',s.uploaded_rows],['Unique matched users',s.matched_unique_users],['Ranked problems',s.issues],['Needs review',s.needs_review]];
  $('metrics').innerHTML=metrics.map(([label,value])=>`<div class="metric"><small>${label}</small><strong>${value}</strong></div>`).join('');
  $('ranked').innerHTML=result.issues.map(i=>`<tr><td>#${i.rank}</td><td><button class="issue-link" data-issue="${escapeHTML(i.id)}">${escapeHTML(i.issue)}</button><small>${i.messages} retained comments</small></td><td><span class="priority ${escapeHTML(i.priority)}">${escapeHTML(i.priority)}</span></td><td>${i.unique_users}</td><td>${i.frequency_percent}%</td><td><span class="score">${i.score.toFixed(2)}</span></td><td><button class="issue-link" data-issue="${escapeHTML(i.id)}">View comments ↗</button></td></tr>`).join('');
  $('no-issues').hidden=result.issues.length>0;
  $('formula-explanation').textContent=`${result.formula}. High=3, Medium=2, Low=1. Frequency denominator: ${s.matched_unique_users} distinct users with matched feedback. ${s.duplicate} exact duplicates, ${s.irrelevant} irrelevant, ${s.no_action} with no action requested, ${s.empty} empty, ${s.needs_review} needing review. A user can count toward multiple different problems, so frequency percentages need not sum to 100%.`;
  $('audit-filter').value='all';renderAudit();
}
function renderAudit(){if(!result)return;const filter=$('audit-filter').value;const rows=result.audit.filter(r=>filter==='all'||r.status===filter);$('audit').innerHTML=rows.map(r=>`<tr><td>#${r.id}</td><td>${escapeHTML(r.name||'—')}<small>${escapeHTML(r.user_id||'—')}</small></td><td>${escapeHTML(r.feedback||'(empty)')}</td><td><strong>${escapeHTML(statusNames[r.status]||r.status)}</strong><small>${escapeHTML(r.reason)}</small>${r.topics?.length?`<small>Topics: ${escapeHTML(r.topics.join(', '))}</small>`:''}</td></tr>`).join('');$('audit-empty').hidden=rows.length>0;}
$('audit-filter').onchange=renderAudit;
$('ranked').addEventListener('click',e=>{const button=e.target.closest('[data-issue]');if(!button)return;const issue=result.issues.find(i=>i.id===button.dataset.issue);if(!issue)return;$('evidence-title').textContent=issue.issue;$('evidence-summary').textContent=`${issue.priority.toUpperCase()} priority · ${issue.unique_users} unique users · ${issue.messages} comments · Score ${issue.score.toFixed(2)}/100 · ${issue.repeat_mentions_not_counted} repeat mentions do not add frequency.`;const seen=new Set();$('evidence-list').innerHTML=issue.evidence.map(r=>{const repeat=seen.has(r.user_id);seen.add(r.user_id);return `<article class="quote"><div class="quote-header"><strong>${escapeHTML(r.name)}</strong><small>Record #${r.id}${r.date?' · '+escapeHTML(r.date):''}</small></div><small>User ID: ${escapeHTML(r.user_id)} · ${repeat?'Additional comment; no extra frequency vote':'Counts as one unique user'}</small><p>${escapeHTML(r.feedback)}</p></article>`}).join('');$('evidence').showModal();});
$('close-dialog').onclick=()=>$('evidence').close();
$('export').onclick=()=>{if(!result)return;const blob=new Blob([JSON.stringify(result,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='review-radar-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
try{const stored=JSON.parse(localStorage.getItem(storageKey)||'null');loadSettings(stored||{});}catch{loadSettings({});}
if(location.protocol==='file:')notify('Start the backend and visit http://127.0.0.1:8000. This frontend requires the Python API.');
