const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dateText = value => new Date(value).toLocaleDateString(undefined, {day:'numeric', month:'short', year:'numeric'});
const state = {user:null, pregnancies:[], pid:null, dashboard:null, view:'overview', registering:false};
const fields = [
  ['Age','Age','years',10,60], ['BodyTempF','Body temperature','°F',90,110],
  ['HeartRate','Heart rate','bpm',30,220], ['SystolicBP','Systolic pressure','mmHg',60,260],
  ['DiastolicBP','Diastolic pressure','mmHg',30,160], ['BMI','Body mass index','kg/m²',10,70],
  ['HbA1c','HbA1c','%',2,20], ['FastingGlucose','Fasting glucose','mg/dL',20,600]
];
const units = {Age:'years', BodyTempF:'degF', HeartRate:'bpm', SystolicBP:'mmHg', DiastolicBP:'mmHg', BMI:'kg/m2', HbA1c:'%', FastingGlucose:'mg/dL'};

async function api(path, options={}) {
  let response;
  try { response = await fetch('/api'+path, {...options, headers:{'Content-Type':'application/json','X-Bloom-Request':'1', ...options.headers}}); }
  catch { throw new Error('You are offline. Connect to save or retrieve health records.'); }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    if (response.status === 401 && state.user) showAuth();
    const detail = payload.detail;
    throw new Error(Array.isArray(detail) ? detail.map(e => `${e.loc.slice(1).join(' → ')}: ${e.msg}`).join('\n') : detail || 'Request failed. Please try again.');
  }
  return response.json();
}

function notify(message, error=false) {
  $('status').innerHTML = `<div class="status-message ${error?'error':''}">${escapeHTML(message)}</div>`;
}

function showAuth() {
  state.user = null; state.dashboard = null; state.pregnancies=[]; state.pid=null;
  $('application').hidden=true; $('auth').hidden=false;
  document.querySelectorAll('dialog[open]').forEach(d => d.close());
  $('history').innerHTML=''; $('notification-list').innerHTML=''; $('admin-audit').innerHTML='';
}

$('auth-toggle').addEventListener('click', () => {
  state.registering=!state.registering;
  $('auth-title').textContent=state.registering?'Begin your journey':'Welcome back';
  $('name-label').hidden=!state.registering;
  $('auth-form').elements.name.required=state.registering;
  $('auth-submit').textContent=state.registering?'Create account →':'Sign in →';
  $('auth-toggle').textContent=state.registering?'Already have an account? Sign in':'New here? Create an account';
  $('auth-form').elements.password.autocomplete=state.registering?'new-password':'current-password';
  $('auth-error').textContent='';
});

$('auth-form').addEventListener('submit', async e => {
  e.preventDefault(); $('auth-submit').disabled=true; $('auth-error').textContent='';
  const values=Object.fromEntries(new FormData(e.target));
  if(!state.registering) delete values.name;
  try {
    state.user=await api('/auth/'+(state.registering?'register':'login'), {method:'POST',body:JSON.stringify(values)});
    e.target.reset(); await start();
  } catch(error) { $('auth-error').textContent=error.message; }
  finally { $('auth-submit').disabled=false; }
});

function pregnancyForm() {
  return `<form class="pregnancy-form form-grid"><label>Episode name<input name="label" value="My pregnancy" required maxlength="100"></label><label>First day of last menstrual period<input name="lmp" type="date" required max="${new Date().toLocaleDateString('en-CA')}" min="${new Date(Date.now()-308*86400000).toLocaleDateString('en-CA')}"><small>Used for estimated dating; your clinician can confirm your dates.</small></label><button class="primary">Save pregnancy →</button></form>`;
}

async function start() {
  $('auth').hidden=true; $('application').hidden=false;
  $('user-avatar').textContent=state.user.name.split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase();
  $('admin-nav').hidden=state.user.role!=='admin';
  state.pregnancies=await api('/pregnancies');
  $('setup').hidden=state.pregnancies.length>0; $('workspace').hidden=!state.pregnancies.length;
  $('setup-form-host').innerHTML=pregnancyForm(); $('profile-form-host').innerHTML=pregnancyForm();
  document.querySelectorAll('.pregnancy-form').forEach(f => f.addEventListener('submit', async e => {
    e.preventDefault(); const button=f.querySelector('button'); button.disabled=true;
    try { const p=await api('/pregnancies',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(f)))}); state.pid=p.id; await start(); notify('Pregnancy profile saved.'); }
    catch(error) { notify(error.message,true); } finally {button.disabled=false;}
  }));
  if(state.pregnancies.length) {
    if(!state.pregnancies.some(p=>p.id===state.pid)) state.pid=state.pregnancies[0].id;
    $('episode').innerHTML=state.pregnancies.map(p=>`<option value="${p.id}">${escapeHTML(p.label)} · ${dateText(p.lmp)}</option>`).join('');
    $('episode').value=state.pid; await loadDashboard();
  }
  navigate(!state.pregnancies.length && state.user.role==='admin'?'admin':'overview');
}

$('episode').addEventListener('change',async()=>{state.pid=Number($('episode').value); try{await loadDashboard();}catch(e){notify(e.message,true);}});

const viewNames={overview:['A little check-in.','Every small step helps you understand your journey.'],measurements:['Your health record.','A clear view of the measurements you have logged.'],guidance:['Support for your stage.','Guidance reviewed and published by your care team.'],notifications:['Stay in the loop.','Updates linked to your pregnancy assessments.'],profile:['Your pregnancy story.','Keep each chapter of your journey in one place.'],admin:['Care, thoughtfully managed.','Review guidance and inspect model traceability.']};
function navigate(view) {
  if(view==='admin' && state.user?.role!=='admin') return;
  const needsSetup=!state.pregnancies.length && view!=='admin';
  $('setup').hidden=!needsSetup;
  $('workspace').hidden=needsSetup;
  document.querySelector('.episode-selector').hidden=!state.pregnancies.length;
  state.view=view;
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!=='view-'+view);
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));
  $('page-title').textContent=viewNames[view][0]; $('page-subtitle').textContent=viewNames[view][1];
  $('breadcrumb').textContent='Your '+(view==='admin'?'administration':view);
  $('heading-eyebrow').textContent=view==='overview'?'YOUR HEALTH, AT A GLANCE':'YOUR PREGNANCY COMPANION';
  $('add-measurement').hidden=['profile','admin'].includes(view);
  if(view==='admin') loadAdmin().catch(e=>notify(e.message,true));
  if(view==='guidance' && state.dashboard) trackGuidance();
}

function trackGuidance() {
  for(const g of state.dashboard.guidance) api(`/pregnancies/${state.pid}/guidance/${g.id}/delivered`,{method:'POST'}).catch(()=>{});
}
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.view)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.go)));

async function loadDashboard() {
  const pid=state.pid;
  const data=await api(`/pregnancies/${pid}/dashboard`);
  if(pid!==state.pid) return;
  state.dashboard=data; render();
  if(state.view==='guidance') trackGuidance();
}

function render() {
  const {pregnancy:p, observations:obs, guidance, notifications}=state.dashboard;
  const latest=obs.at(-1), result=latest?.prediction;
  $('week-number').textContent=p.weeks; $('week-days').textContent=`and ${p.days} days`;
  $('trimester').textContent=['','First trimester','Second trimester','Third trimester'][p.stage];
  $('due-date').textContent='Estimated due date · '+dateText(p.due_date);
  $('pregnancy-progress').style.width=Math.min(100,p.weeks/40*100)+'%';
  $('risk-content').innerHTML=result?`<span class="risk-badge ${result.category}">${result.category==='mid'?'Mid':result.category==='high'?'High':'Low'} risk estimate</span><p class="risk-description">${result.category==='low'?'Keep your care team informed as your pregnancy progresses.':'Contact your maternity care team to review these measurements.'}</p><div class="probabilities">${Object.entries(result.probabilities).map(([k,v])=>`<span>${k[0].toUpperCase()+k.slice(1)} ${(v*100).toFixed(1)}%</span>`).join('')}</div>${result.outside_training_range.length?'<p class="error">Some measurements are outside the model’s training range.</p>':''}`:`<h2>Assessment unavailable</h2><p class="risk-description">The trained model’s measurement units need verification. ${latest?'Your visit is safely recorded.':'You can still log your measurements.'}</p>`;
  const metrics=[['Blood pressure',latest?`${latest.values.SystolicBP}/${latest.values.DiastolicBP}`:'—','mmHg'],['Heart rate',latest?.values.HeartRate??'—','bpm'],['Body temperature',latest?.values.BodyTempF??'—','°F'],['Fasting glucose',latest?.values.FastingGlucose??'—','mg/dL']];
  $('metric-cards').innerHTML=metrics.map(([name,value,unit])=>`<article class="metric"><div class="metric-label">${name}</div><div class="metric-value">${value}<small>${unit}</small></div><div class="metric-date">${latest?dateText(latest.observed_at):'No measurements yet'}</div></article>`).join('');
  renderTrend(obs);
  $('history').innerHTML=obs.length?`<table><thead><tr><th>Visit</th>${fields.map(f=>`<th>${f[1]}<br>${f[2]}</th>`).join('')}<th>Assessment</th></tr></thead><tbody>${[...obs].reverse().map(o=>`<tr><td>${dateText(o.observed_at)}<br><small>${new Date(o.observed_at).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</small></td>${fields.map(f=>`<td>${o.values[f[0]]}</td>`).join('')}<td>${o.prediction?`<span class="risk-badge ${o.prediction.category}">${o.prediction.category} risk</span>`:`<button class="text-button retry" data-id="${o.id}">Retry assessment</button>`}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">Your history starts with your first measurement visit.</div>';
  document.querySelectorAll('.retry').forEach(b=>b.addEventListener('click',async()=>{b.disabled=true;try{await api(`/observations/${b.dataset.id}/predict`,{method:'POST'});await loadDashboard();notify('Assessment complete.');}catch(e){notify(e.message,true);b.disabled=false;}}));
  $('guidance-list').innerHTML=guidance.length?guidance.map(g=>`<article class="card"><span class="eyebrow">REVIEWED · TRIMESTER ${p.stage}</span><h2>${escapeHTML(g.title)}</h2><p class="content-body">${escapeHTML(g.body)}</p><a href="${escapeHTML(g.source_url)}" target="_blank" rel="noopener noreferrer">Read source ↗</a></article>`).join(''):'<article class="card empty"><h2>Guidance is being prepared.</h2><p>No reviewed content has been published for your stage yet. Speak with your care team for personalised advice.</p></article>';
  $('guidance-teaser').textContent=guidance.length?guidance[0].title:'Reviewed guidance will appear here when your care team publishes it.';
  $('notification-count').textContent=notifications.filter(n=>!n.read).length||'';
  $('notification-list').innerHTML=notifications.length?notifications.map(n=>`<article class="card notification ${n.read?'read':''}"><div><span class="eyebrow">ASSESSMENT UPDATE</span><p>${escapeHTML(n.message)}</p><small>${dateText(n.created_at)}</small></div>${n.read?'<small>Read</small>':`<button class="text-button mark-read" data-id="${n.id}">Mark as read</button>`}</article>`).join(''):'<article class="card empty">You’re all caught up. Assessment updates will appear here.</article>';
  document.querySelectorAll('.mark-read').forEach(b=>b.addEventListener('click',async()=>{try{await api(`/notifications/${b.dataset.id}/read`,{method:'PATCH'});await loadDashboard();}catch(e){notify(e.message,true);}}));
  $('profile-details').innerHTML=`<div class="profile-details"><p class="muted">Episode<strong>${escapeHTML(p.label)}</strong></p><p class="muted">Last menstrual period<strong>${dateText(p.lmp)}</strong></p><p class="muted">Estimated due date<strong>${dateText(p.due_date)}</strong></p><p class="muted">Gestational age<strong>${p.weeks} weeks, ${p.days} days</strong></p></div><p class="muted">Dating is an estimate based on the last menstrual period. Confirm your dates with your clinician.</p>`;
}

function renderTrend(obs) {
  const points=obs.slice(-10);
  if(!points.length) {$('trend').innerHTML='<div class="empty">Your blood pressure history will grow with each visit.</div>';return;}
  const values=points.flatMap(o=>[o.values.SystolicBP,o.values.DiastolicBP]);
  const min=Math.floor((Math.min(...values)-10)/10)*10, max=Math.ceil((Math.max(...values)+10)/10)*10;
  const x=i=>45+(points.length===1?210:i/(points.length-1)*420), y=v=>140-(v-min)/(max-min)*115;
  let svg='<svg viewBox="0 0 500 175" role="img" aria-label="Blood pressure over recent visits">';
  for(let i=0;i<4;i++){const val=min+(max-min)*i/3;svg+=`<line x1="40" y1="${y(val)}" x2="480" y2="${y(val)}" stroke="#edf0e8"/><text x="5" y="${y(val)+4}">${Math.round(val)}</text>`;}
  for(const [key,color] of [['SystolicBP','#24594e'],['DiastolicBP','#b2b96d']]){
    svg+=`<polyline points="${points.map((o,i)=>`${x(i)},${y(o.values[key])}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>`;
    svg+=points.map((o,i)=>`<circle cx="${x(i)}" cy="${y(o.values[key])}" r="4" fill="${color}"><title>${dateText(o.observed_at)}: ${o.values[key]} mmHg</title></circle>`).join('');
  }
  svg+=points.filter((_,i)=>i===0||i===points.length-1).map(o=>`<text x="${x(points.indexOf(o))}" y="169" text-anchor="middle">${escapeHTML(new Date(o.observed_at).toLocaleDateString(undefined,{day:'numeric',month:'short'}))}</text>`).join('');
  $('trend').innerHTML=svg+'</svg>';
}

$('measurement-fields').innerHTML=fields.map(([key,label,unit,min,max])=>`<label>${label} <span class="muted">(${unit})</span><input name="${key}" type="number" step="any" min="${min}" max="${max}" required></label>`).join('');
$('add-measurement').addEventListener('click',()=>{
  $('measurement-form').reset(); $('measurement-error').textContent='';
  const current=new Date(); current.setMinutes(current.getMinutes()-current.getTimezoneOffset());
  $('measurement-form').elements.observed_at.value=current.toISOString().slice(0,16);
  $('measurement-dialog').showModal();
});
document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>$(b.dataset.close).close()));
$('measurement-form').addEventListener('submit',async e=>{
  e.preventDefault(); $('measurement-submit').disabled=true; $('measurement-error').textContent='';
  const data=Object.fromEntries(new FormData(e.target));
  const values=Object.fromEntries(fields.map(f=>[f[0],Number(data[f[0]])]));
  try{
    const observation=await api(`/pregnancies/${state.pid}/observations`,{method:'POST',body:JSON.stringify({observed_at:new Date(data.observed_at).toISOString(),values,units})});
    $('measurement-dialog').close(); notify('Measurements saved. Running your assessment…');
    try {await api(`/observations/${observation.id}/predict`,{method:'POST'});notify('Measurements saved and assessment complete.');}
    catch(error){notify(error.message,true);}
    await loadDashboard();
  }catch(error){$('measurement-error').textContent=error.message;}
  finally{$('measurement-submit').disabled=false;}
});

$('model-info').addEventListener('click',async()=>{
  try{const m=await api('/model');$('model-details').innerHTML=`<span class="risk-badge">Unit verification required</span><p class="error">${escapeHTML(m.unit_issue)}</p><p>${escapeHTML(m.sequence_note)}</p><p>Held-out test accuracy: <strong>${(m.test_accuracy*100).toFixed(1)}%</strong>. This is a dataset evaluation, not evidence of clinical effectiveness.</p><p>Single-layer LSTM · 50 hidden units · dropout 0.20. Eight complete features, with the saved training scaler. Class selection uses the highest probability.</p><p>Feature order: ${m.features.map(escapeHTML).join(', ')}.</p><p class="model-code">Version: ${escapeHTML(m.version)}<br>Model SHA-256: ${m.sha256}<br>Scaler SHA-256: ${m.scaler_sha256}</p>`;$('info-dialog').showModal();}catch(e){notify(e.message,true);}
});

async function loadAdmin(){
  const data=await api('/admin');
  $('admin-content').innerHTML=data.guidance.map(g=>`<div class="admin-draft"><h3>${escapeHTML(g.title)} · trimester ${g.stage} · ${g.category}</h3><p class="content-body">${escapeHTML(g.body)}</p><a href="${escapeHTML(g.source_url)}" target="_blank" rel="noopener noreferrer">Source ↗</a><p>${g.reviewed?'Published':`<button class="text-button publish" data-id="${g.id}">Reviewed: publish this draft →</button>`}</p></div>`).join('')||'<p class="empty">No guidance drafts yet.</p>';
  document.querySelectorAll('.publish').forEach(b=>b.addEventListener('click',async()=>{try{await api(`/admin/guidance/${b.dataset.id}/review`,{method:'POST'});await loadAdmin();if(state.pid)await loadDashboard();notify('Reviewed guidance published.');}catch(e){notify(e.message,true);}}));
  $('admin-audit').innerHTML=data.models.map(m=>`<p class="model-code">${escapeHTML(m.version)} · ${escapeHTML(m.status)}<br>${escapeHTML(m.decision_rule)}</p>`).join('')+`<div class="table-wrap"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Resource</th></tr></thead><tbody>${data.audit.map(a=>`<tr><td>${dateText(a.created_at)}</td><td>${a.user_id}</td><td>${escapeHTML(a.action)}</td><td>${escapeHTML(a.resource)}</td></tr>`).join('')}</tbody></table></div>`;
}
$('guidance-form').addEventListener('submit',async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const data=Object.fromEntries(new FormData(e.target));data.stage=Number(data.stage);await api('/admin/guidance',{method:'POST',body:JSON.stringify(data)});e.target.reset();await loadAdmin();notify('Draft saved. It will appear for mothers after review.');}catch(error){notify(error.message,true);}finally{button.disabled=false;}});
for(const id of ['logout','mobile-logout']) $(id).addEventListener('click',async()=>{try{await api('/auth/logout',{method:'POST'});showAuth();}catch(e){notify(e.message,true);}});
window.addEventListener('offline',()=>notify('You are offline. Connect to save or retrieve health records.',true));
window.addEventListener('online',()=>{if(state.user){loadDashboard().then(()=>notify('Connection restored.')).catch(e=>notify(e.message,true));}});
if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(()=>{});
(async()=>{try{state.user=await api('/me');await start();}catch(error){if(state.user)notify(error.message,true);else showAuth();}})();
