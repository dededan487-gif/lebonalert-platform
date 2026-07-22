/**
 * LeBonAlert Platform v5 - Frontend SaaS + Premium + Admin
 */
const API = '';
let currentUser = null;
let currentPlan = null;
let plans = {};
let alerts = [];
let categories = [];
let resultsCache = [];
let isAdmin = false;

const el = id => document.getElementById(id);
const escapeHtml = s => String(s||'').replace(/[&<>"']/g, m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const toast = (msg, ok=true) => {
  const e = document.createElement('div');
  e.textContent = msg;
  e.style.cssText = `position:fixed;bottom:20px;right:20px;background:${ok?'#22c55e':'#ef4444'};color:white;padding:12px 18px;border-radius:10px;font-size:13px;z-index:999;box-shadow:0 10px 30px #00000050`;
  document.body.appendChild(e);
  setTimeout(()=>e.remove(), 3500);
};

// --- Auth ---
async function checkAuth() {
  try {
    const r = await fetch(`${API}/api/auth/me`, {credentials:'include'});
    if (!r.ok) throw new Error('not auth');
    const j = await r.json();
    if (j.authenticated) {
      currentUser = j.user;
      currentPlan = j.user.plan;
      plans = j.plans || {};
      isAdmin = !!j.user.is_admin;
      showApp();
      return true;
    }
  } catch {}
  showAuth();
  return false;
}
function showAuth() {
  el('authWrapper').style.display='grid';
  el('app').classList.remove('show');
}
function showApp() {
  el('authWrapper').style.display='none';
  el('app').classList.add('show');
  el('userName').textContent = currentUser.username;
  el('userEmail').textContent = currentUser.email;
  el('telegramChatId').value = currentUser.telegram_chat_id || '';
  el('telegramEnabled').checked = !!currentUser.telegram_enabled;
  el('emailEnabled').checked = currentUser.email_enabled !== false;
  
  const plan = currentPlan || {name:'Gratuit', badge:'🆓 Gratuit'};
  el('userPlanBadge').textContent = plan.badge || plan.name;
  el('userPlanBadge').className = 'badge ' + (currentUser.is_premium ? 'green' : 'gray');
  if (currentUser.is_premium) el('userPlanBadge').classList.add('green');
  if (isAdmin) {
    el('adminBadge').style.display='inline-block';
    el('adminPanel').classList.add('show');
    loadAdminStats();
  }
  renderPlanCard();
  loadCategories();
  loadAlerts();
  updateUpgradeBtn();
}

document.querySelectorAll('.auth-tab').forEach(tab=>{
  tab.onclick=()=>{
    document.querySelectorAll('.auth-tab').forEach(t=>t.classList.remove('active'));
    tab.classList.add('active');
    el('loginForm').style.display = tab.dataset.tab==='login' ? 'block' : 'none';
    el('registerForm').style.display = tab.dataset.tab==='register' ? 'block' : 'none';
    el('authError').classList.remove('show');
  };
});
function showError(msg){ const e=el('authError'); e.textContent=msg; e.classList.add('show'); }

el('loginForm').addEventListener('submit', async e=>{
  e.preventDefault();
  try {
    const r = await fetch(`${API}/api/auth/login`, {
      method:'POST', credentials:'include', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username: el('loginId').value.trim(), password: el('loginPass').value})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error);
    toast(`Bienvenue ${j.user.username} !`);
    await checkAuth();
  } catch(err){ showError(err.message); }
});
el('registerForm').addEventListener('submit', async e=>{
  e.preventDefault();
  try {
    const r = await fetch(`${API}/api/auth/register`, {
      method:'POST', credentials:'include', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({username: el('regUser').value.trim(), email: el('regEmail').value.trim(), password: el('regPass').value})
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error);
    toast(`Compte créé !`);
    await checkAuth();
  } catch(err){ showError(err.message); }
});
el('logoutBtn').onclick = async ()=>{
  await fetch(`${API}/api/auth/logout`, {method:'POST', credentials:'include'});
  currentUser=null; alerts=[]; resultsCache=[]; showAuth();
};

// --- Plans ---
function renderPlanCard() {
  const card = el('planCard');
  const plan = currentPlan || plans.free || {name:'Gratuit', max_alerts:3, min_frequency:300, can_telegram:false};
  const isPrem = currentUser?.is_premium;
  if (isPrem) {
    card.className='plan-card premium';
    card.innerHTML = `
      <h4>⭐ Premium actif <span style="font-size:11px;background:white;color:#ff6a00;padding:3px 7px;border-radius:999px">4.99€/mo</span></h4>
      <ul>
        <li>∞ alertes illimitées</li>
        <li>30s ultra rapide</li>
        <li>📧 Email + 📲 Telegram</li>
        <li>Toutes catégories</li>
      </ul>
      <div style="font-size:11px;margin-top:8px;opacity:.9">${currentUser.premium_until?`Jusqu'au ${new Date(currentUser.premium_until).toLocaleDateString('fr-FR')}`:''}</div>
      <button class="btn-ghost" id="manageSubBtn" style="margin-top:8px;background:white;color:#111827;border:none;width:100%">Gérer abonnement</button>
    `;
    setTimeout(()=>{
      const b = document.getElementById('manageSubBtn');
      if (b) b.onclick = async ()=>{
        try {
          const r = await fetch(`${API}/api/stripe/portal`, {method:'POST', credentials:'include'});
          const j = await r.json();
          if (j.url) window.open(j.url, '_blank');
          else toast(j.error||'Pas de portail (mode démo)', false);
        } catch(e){ toast('Erreur portail', false); }
      };
    },100);
  } else {
    card.className='plan-card free';
    card.innerHTML = `
      <h4>🆓 Gratuit <span style="font-size:11px;opacity:.7">${alerts.length}/${plan.max_alerts||3} alertes</span></h4>
      <ul>
        <li>${plan.max_alerts||3} alertes max</li>
        <li>Fréq min ${plan.min_frequency||300}s (5 min)</li>
        <li>📧 Email seulement</li>
        <li>Toutes catégories</li>
      </ul>
      <button class="btn-upgrade" id="upgradeFromCard">⭐ Passer Premium 4.99€</button>
    `;
    setTimeout(()=>{
      const b=document.getElementById('upgradeFromCard');
      if(b) b.onclick=()=>showPremiumModal();
    },100);
  }
}

function updateUpgradeBtn() {
  const btn = el('upgradeBtn');
  if (currentUser?.is_premium) {
    btn.textContent='✅ Premium actif';
    btn.style.background='#22c55e';
    btn.onclick = ()=> toast('Tu es déjà Premium ⭐');
  } else {
    btn.textContent='⭐ Passer Premium 4.99€';
    btn.style.background='linear-gradient(135deg,#a855f7,#ec4899)';
    btn.onclick = ()=> showPremiumModal();
  }
}

function showPremiumModal() {
  el('premiumModal').classList.add('show');
}
el('closePremium').onclick = ()=> el('premiumModal').classList.remove('show');
el('premiumModal').onclick = (e)=>{ if(e.target.id==='premiumModal') el('premiumModal').classList.remove('show'); };

el('checkoutBtn').onclick = async ()=>{
  const btn = el('checkoutBtn');
  btn.textContent='⏳ Création session Stripe...';
  try {
    const r = await fetch(`${API}/api/stripe/create-checkout-session`, {method:'POST', credentials:'include'});
    const j = await r.json();
    if (!r.ok) {
      if (j.error && j.error.includes('Stripe non configuré')) {
        // Mode démo: propose activation admin
        if (confirm('Stripe non configuré (mode démo). Veux-tu que je t\'active en Premium manuellement ? (Admin)')) {
          // Essaie via admin endpoint si user est admin
          if (isAdmin && currentUser) {
            const r2 = await fetch(`${API}/api/admin/users/${currentUser.id}/make-premium`, {
              method:'POST', credentials:'include',
              headers:{'Content-Type':'application/json'},
              body: JSON.stringify({months:1})
            });
            const j2 = await r2.json();
            if (j2.ok) {
              toast('✅ Premium activé 1 mois (mode démo admin) ! Recharge la page.');
              el('premiumModal').classList.remove('show');
              await checkAuth();
              return;
            }
          }
          el('premiumMsg').style.display='block';
          el('premiumMsg').innerHTML=`<span style="color:#fca5a5">Stripe non configuré. Pour activer Premium en mode démo:<br>1. Connecte-toi en admin (admin/admin123)<br>2. Va dans Admin Panel → Users → clique ⭐ pour passer premium<br>Ou configure STRIPE_SECRET_KEY sur Railway.</span>`;
        } else {
          throw new Error(j.error);
        }
      } else if (j.upgrade_required) {
        throw new Error(j.error);
      } else if (j.url) {
        window.location.href = j.url;
        return;
      } else {
        throw new Error(j.error||'Erreur checkout');
      }
    }
    if (j.url) {
      window.location.href = j.url;
    } else {
      toast('Session créée, redirection...', true);
    }
  } catch(e) {
    el('premiumMsg').style.display='block';
    el('premiumMsg').textContent='❌ '+e.message;
    toast('❌ '+e.message, false);
  } finally {
    btn.textContent='💳 Payer 4.99€/mois avec Stripe';
  }
};

// --- Categories ---
async function loadCategories() {
  try {
    const r = await fetch(`${API}/api/categories`);
    const j = await r.json();
    categories = j.categories || [];
  } catch {
    categories = [{id:"",label:"🌐 Toutes"},{id:"2",label:"🚗 Voitures"}];
  }
  const catSelect = el('category');
  const filterCat = el('filterByCategory');
  const groups={};
  categories.forEach(c=>{ if(!groups[c.group]) groups[c.group]=[]; groups[c.group].push(c); });
  catSelect.innerHTML=''; filterCat.innerHTML='<option value="">📂 Toutes catégories</option>';
  Object.keys(groups).forEach(gName=>{
    const og=document.createElement('optgroup'); og.label=gName;
    groups[gName].forEach(c=>{
      const opt=document.createElement('option'); opt.value=c.id; opt.textContent=c.label; og.appendChild(opt);
      filterCat.appendChild(opt.cloneNode(true));
    });
    catSelect.appendChild(og);
  });
}

// --- Settings ---
el('saveSettings').onclick = async ()=>{
  const payload={
    telegram_chat_id: el('telegramChatId').value.trim(),
    telegram_enabled: el('telegramEnabled').checked,
    email_enabled: el('emailEnabled').checked
  };
  try {
    const r=await fetch(`${API}/api/user/settings`, {method:'PUT', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const j=await r.json();
    if(!r.ok) throw new Error(j.error);
    toast('✅ Réglages sauvegardés');
    el('settingsMsg').style.display='block'; el('settingsMsg').textContent='✅ Sauvegardé';
    setTimeout(()=>el('settingsMsg').style.display='none',2500);
    await checkAuth();
  } catch(e){ toast('❌ '+e.message,false); }
};
el('testTelegramBtn').onclick = async ()=>{
  el('testTelegramBtn').textContent='⏳...';
  try{
    const r=await fetch(`${API}/api/user/test-telegram`, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({keywords: alerts[0]?.keywords||'clio 1983 test'})});
    const j=await r.json(); if(!r.ok) throw new Error(j.error); toast(j.message);
  }catch(e){ toast('❌ '+e.message,false); }
  el('testTelegramBtn').textContent='📲 Test';
};
el('testEmailBtn').onclick = async ()=>{
  el('testEmailBtn').textContent='⏳...';
  try{
    const r=await fetch(`${API}/api/user/test-email`, {method:'POST', credentials:'include'});
    const j=await r.json(); toast(j.message||'Email envoyé');
  }catch(e){ toast('❌ '+e.message,false); }
  el('testEmailBtn').textContent='📧 Test';
};

// --- Alerts ---
async function loadAlerts() {
  try{
    const r=await fetch(`${API}/api/alerts`, {credentials:'include'});
    const j=await r.json();
    alerts=j.alerts||[];
    if (j.plan) currentPlan=j.plan;
  }catch{ alerts=[]; }
  renderAlerts();
  await loadResultsForAlerts();
  updateStats();
  const sel=el('filterByAlert'); const cur=sel.value;
  sel.innerHTML='<option value="">📋 Toutes mes alertes</option>'+alerts.map(a=>`<option value="${a.id}">${escapeHtml(a.keywords)} ${a.active?'':'⏸️'}</option>`).join(''); sel.value=cur;
  el('userAlertsCount').textContent=`${alerts.filter(a=>a.active).length}/${alerts.length} alertes`;
  renderPlanCard();
  // Update freq hint
  const plan = currentPlan || {min_frequency:300};
  el('freqHint').textContent = currentUser?.is_premium ? 'Premium: min 30s' : `Gratuit: min ${plan.min_frequency||300}s - Premium 30s`;
}
function getCatLabel(id){ const c=categories.find(x=>x.id===String(id)); return c?c.label:(id||'Toutes'); }

function renderAlerts() {
  const bar=el('alertsBar'); bar.innerHTML='';
  if(alerts.length===0){ bar.innerHTML=`<span style="color:var(--muted);font-size:13px">Aucune alerte. Crée ta première (ex: clio 1983 en Voitures, maison 3ch en Immo) →</span>`; return; }
  alerts.forEach(a=>{
    const chip=document.createElement('div'); chip.className=`alert-chip ${a.active?'active':'inactive'}`;
    const priceTxt=a.price_max?`≤${a.price_max}€`:''; const catLabel=getCatLabel(a.category_id);
    const newBadge=a.new_count?`<span style="background:var(--primary);color:white;padding:2px 6px;border-radius:999px;font-size:10px;font-weight:800">+${a.new_count}</span>`:'';
    chip.innerHTML=`
      <div class="chip-dot" style="background:${a.active?'var(--green)':'#555'}"></div>
      <div style="display:flex;flex-direction:column;gap:2px">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <strong>${escapeHtml(a.keywords)}</strong> ${newBadge}
          <span style="font-size:10px;background:#ffffff12;padding:2px 6px;border-radius:999px">${escapeHtml(catLabel)}</span>
          <span style="color:var(--muted);font-size:11px">${priceTxt} ${a.frequency}s ${a.notify_email?'📧':''}${a.notify_telegram?'📲':''}</span>
        </div>
        ${a.description?`<div style="font-size:11px;color:var(--muted)">${escapeHtml(a.description)}</div>`:''}
      </div>
      <div class="chip-actions">
        <button class="chip-btn" data-act="edit" data-id="${a.id}">✏️</button>
        <button class="chip-btn" data-act="toggle" data-id="${a.id}">${a.active?'⏸️':'▶️'}</button>
        <button class="chip-btn" data-act="reset" data-id="${a.id}">🔄</button>
        <button class="chip-btn" data-act="delete" data-id="${a.id}" style="color:#f87171">🗑️</button>
      </div>`;
    chip.querySelectorAll('.chip-btn').forEach(btn=>{
      btn.onclick=async e=>{
        e.stopPropagation(); const id=btn.dataset.id; const act=btn.dataset.act;
        if(act==='delete'){ if(!confirm(`Supprimer "${a.keywords}" ?`)) return; await fetch(`${API}/api/alerts/${id}`, {method:'DELETE', credentials:'include'}); toast('Supprimée'); await loadAlerts(); }
        else if(act==='toggle'){ await fetch(`${API}/api/alerts/${id}/toggle`, {method:'POST', credentials:'include'}); await loadAlerts(); }
        else if(act==='edit'){ startEdit(id); }
        else if(act==='reset'){ await fetch(`${API}/api/alerts/${id}/reset`, {method:'POST', credentials:'include'}); toast('Reset'); await loadAlerts(); }
      };
    });
    chip.onclick=e=>{ if(e.target.closest('.chip-btn')) return; el('filterByAlert').value=a.id; renderResults(); };
    bar.appendChild(chip);
  });
}
let editingId=null;
function startEdit(id){
  const a=alerts.find(x=>x.id===id); if(!a) return;
  editingId=id; el('editId').value=id; el('keywords').value=a.keywords; el('category').value=a.category_id||''; el('alertDesc').value=a.description||'';
  el('priceMin').value=a.price_min||''; el('priceMax').value=a.price_max||''; el('frequency').value=a.frequency||300;
  el('notifyEmail').checked=!!a.notify_email; el('notifyTelegram').checked=!!a.notify_telegram; el('active').checked=!!a.active;
  el('formTitle').textContent=`✏️ Modifier: ${a.keywords}`; el('submitBtn').textContent='💾 Sauvegarder'; el('cancelEdit').style.display='block';
}
function cancelEdit(){ editingId=null; el('editId').value=''; el('alertForm').reset(); el('formTitle').textContent='➕ Nouvelle alerte (toutes catégories)'; el('submitBtn').textContent='🚀 Créer alerte'; el('cancelEdit').style.display='none'; el('frequency').value='300'; }
el('cancelEdit').onclick=cancelEdit;

el('alertForm').addEventListener('submit', async e=>{
  e.preventDefault();
  const payload={
    keywords: el('keywords').value.trim(),
    category_id: el('category').value,
    description: el('alertDesc').value.trim(),
    price_min: el('priceMin').value ? parseInt(el('priceMin').value) : null,
    price_max: el('priceMax').value ? parseInt(el('priceMax').value) : null,
    location_mode: el('locationMode').value,
    frequency: parseInt(el('frequency').value),
    notify_email: el('notifyEmail').checked,
    notify_telegram: el('notifyTelegram').checked,
    active: el('active').checked
  };
  if(!payload.keywords) return toast('Mots-clés requis',false);
  const btn=el('submitBtn'); const prev=btn.textContent; btn.textContent='⏳...'; btn.disabled=true; el('limitMsg').style.display='none';
  try{
    let url=`${API}/api/alerts`; let method='POST';
    if(editingId){ url=`${API}/api/alerts/${editingId}`; method='PUT'; }
    const r=await fetch(url, {method, credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const j=await r.json();
    if(!r.ok){
      if(j.upgrade_required){ showPremiumModal(); el('limitMsg').style.display='block'; el('limitMsg').textContent='⚠️ '+j.error; throw new Error(j.error); }
      throw new Error(j.error);
    }
    toast(editingId?'✅ Modifiée !':'✅ Créée !'); cancelEdit(); await loadAlerts();
  }catch(err){ toast('❌ '+err.message,false); el('limitMsg').style.display='block'; el('limitMsg').textContent=err.message; }
  finally{ btn.textContent=prev; btn.disabled=false; }
});

// Results
async function loadResultsForAlerts(){
  resultsCache=[];
  for(const a of alerts.slice(0,10)){
    try{
      const r=await fetch(`${API}/api/alerts/${a.id}/ads`, {credentials:'include'});
      if(!r.ok) continue;
      const j=await r.json();
      (j.ads||[]).forEach(ad=>{ ad._alertId=a.id; ad._alertKeywords=a.keywords; ad._alertCategory=a.category_id; ad._categoryLabel=getCatLabel(a.category_id); resultsCache.push(ad); });
    }catch{}
  }
  resultsCache.sort((a,b)=> new Date(b._found_at||b.creation_date||0)-new Date(a._found_at||a.creation_date||0));
  resultsCache=resultsCache.slice(0,200);
  renderResults();
}
function renderResults(){
  const filter=document.querySelector('.filter-btn.active')?.dataset.filter||'all';
  const textFilter=el('searchInResults').value.toLowerCase();
  const alertFilter=el('filterByAlert').value;
  const catFilter=el('filterByCategory').value;
  let list=[...resultsCache];
  if(filter==='new'){ list=list.filter(ad=>{ const d=ad._found_at||ad.creation_date; if(!d) return true; return (Date.now()-new Date(d).getTime())/1000/60 < 120; }); }
  if(textFilter){ list=list.filter(ad=> (ad.subject+' '+(ad.body||'')+' '+(ad.location||'')+' '+(ad._alertKeywords||'')).toLowerCase().includes(textFilter)); }
  if(alertFilter){ list=list.filter(ad=> String(ad._alertId)===String(alertFilter)); }
  if(catFilter){ list=list.filter(ad=> String(ad.category_id)===String(catFilter) || String(ad._alertCategory)===String(catFilter)); }
  el('statTotal').textContent=resultsCache.length;
  if(list.length===0){
    el('results').innerHTML=`<div class="empty-state"><div style="font-size:28px">📭</div><h3>Aucune annonce</h3><p style="font-size:12px">Tes alertes surveillent H24. Tu recevras email/telegram dès qu'une annonce sort.</p></div>`;
    return;
  }
  el('results').innerHTML=list.map(ad=>{
    const isNew=(()=>{ const d=ad._found_at||ad.creation_date; if(!d) return false; return (Date.now()-new Date(d).getTime())<1000*60*30; })();
    const price=ad.price?`${Number(ad.price).toLocaleString('fr-FR')} €`:'N.C';
    const catLabel=ad.category_name||ad._categoryLabel||getCatLabel(ad.category_id);
    return `<div class="card ${isNew?'new':''}" data-id="${ad.id}">
      <div class="card-img">${ad.first_image?`<img src="${ad.first_image}" loading="lazy" onerror="this.style.display='none'">`:`<div style="display:grid;place-items:center;height:100%;color:var(--muted)">📦</div>`}</div>
      <div class="card-body">
        <div style="display:flex;justify-content:space-between"><div class="card-price">${price}</div><span style="font-size:10px;background:#ffffff12;padding:2px 6px;border-radius:999px">${escapeHtml(catLabel)}</span></div>
        <div class="card-title">${escapeHtml(ad.subject)}</div>
        <div class="card-meta">${ad.location?`<span class="meta">📍 ${escapeHtml(ad.location)}</span>`:''}${ad._alertKeywords?`<span class="meta" style="background:#ff6a0015;color:#ff9a4d">🔎 ${escapeHtml(ad._alertKeywords)}</span>`:''}</div>
        <div class="card-footer"><span>${ad._found_at?new Date(ad._found_at).toLocaleTimeString('fr-FR'):''}</span><a href="${ad.url}" target="_blank" onclick="event.stopPropagation()">Voir →</a></div>
      </div>
    </div>`;
  }).join('');
  el('results').querySelectorAll('.card').forEach(card=>{
    card.onclick=()=>{
      const ad=resultsCache.find(a=>String(a.id)===String(card.dataset.id));
      if(ad) openModal(ad);
    };
  });
}
function openModal(ad){
  el('modalBody').innerHTML=`
    <div style="display:flex;gap:14px;flex-wrap:wrap">
      <div style="width:300px;height:200px;background:#0e1118;border-radius:12px;overflow:hidden">${ad.first_image?`<img src="${ad.first_image}" style="width:100%;height:100%;object-fit:cover">`:''}</div>
      <div style="flex:1;min-width:240px">
        <h2 style="font-size:17px">${escapeHtml(ad.subject)}</h2>
        <div style="font-size:20px;font-weight:800;color:var(--primary);margin:8px 0">${ad.price?Number(ad.price).toLocaleString('fr-FR')+' €':'N.C.'}</div>
        <div style="font-size:12px;color:var(--muted)">📍 ${escapeHtml(ad.location||'')} • 📂 ${escapeHtml(ad.category_name||ad._categoryLabel||'')}</div>
        <a href="${ad.url}" target="_blank" style="margin-top:12px;display:inline-block;background:var(--text);color:var(--bg);padding:10px 16px;border-radius:10px;text-decoration:none;font-weight:700;font-size:13px">🔗 Voir Leboncoin</a>
      </div>
    </div>
    <div style="margin-top:14px;white-space:pre-wrap;line-height:1.6;font-size:13px;color:#d0d6e0">${escapeHtml(ad.body||'')}</div>`;
  el('modal').classList.remove('hidden');
}
el('closeModal').onclick=()=>el('modal').classList.add('hidden');
el('modal').onclick=e=>{ if(e.target.id==='modal') el('modal').classList.add('hidden'); };
document.querySelectorAll('.filter-btn').forEach(b=>{ b.onclick=()=>{ document.querySelectorAll('.filter-btn').forEach(x=>x.classList.remove('active')); b.classList.add('active'); renderResults(); }; });
el('searchInResults').oninput=renderResults;
el('filterByAlert').onchange=renderResults;
el('filterByCategory').onchange=renderResults;
el('refreshBtn').onclick=async()=>{ el('refreshBtn').textContent='⏳...'; await loadAlerts(); await loadResultsForAlerts(); el('refreshBtn').textContent='🔄'; };

async function updateStats(){
  try{
    const r=await fetch(`${API}/api/status`, {credentials:'include'});
    const j=await r.json();
    el('statAlerts').textContent=`${j.active_count||0}/${j.alerts_count||0}`;
    el('statTotal').textContent=j.total_seen||0;
    el('statNext').textContent=j.checker?.last_loop?new Date(j.checker.last_loop).toLocaleTimeString('fr-FR'):'-';
  }catch{}
}
setInterval(async()=>{ if(!currentUser) return; await updateStats(); },15000);

// --- Admin ---
async function loadAdminStats(){
  try{
    const r=await fetch(`${API}/api/admin/stats`, {credentials:'include'});
    if(!r.ok) return;
    const j=await r.json();
    el('adminTotalUsers').textContent=j.total_users;
    el('adminPremiumUsers').textContent=j.premium_users;
    el('adminRevenue').textContent=j.revenue+'€';
    el('adminTotalAlerts').textContent=j.total_alerts;
    el('adminActiveAlerts').textContent=j.active_alerts;
    el('adminTotalSeen').textContent=j.total_seen;
    
    const r2=await fetch(`${API}/api/admin/users`, {credentials:'include'});
    const j2=await r2.json();
    const tbody=el('adminUsersBody');
    tbody.innerHTML='';
    (j2.users||[]).forEach(u=>{
      const tr=document.createElement('tr');
      tr.innerHTML=`
        <td><b>${escapeHtml(u.username)}</b><br><small style="color:var(--muted)">${escapeHtml(u.email)}</small>${u.is_admin?'<br><span class="badge purple">Admin</span>':''} ${u.is_premium?'<span class="badge green">Premium</span>':''}</td>
        <td>${u.is_premium?'⭐ Premium<br><small>'+(u.premium_until?new Date(u.premium_until).toLocaleDateString():'')+'</small>':'🆓 Gratuit'}</td>
        <td>${u.alerts_count} / ${u.active_alerts} actives<br><small>${u.seen_count} vues</small></td>
        <td>
          <button class="btn-ghost" data-act="premium" data-id="${u.id}">${u.is_premium?'❌ Retirer Premium':'⭐ Premium'}</button>
          <button class="btn-ghost" data-act="admin" data-id="${u.id}">${u.is_admin?'👤 Retirer Admin':'👑 Admin'}</button>
          <button class="btn-ghost" data-act="delete" data-id="${u.id}" style="color:#f87171">🗑️</button>
        </td>`;
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('button').forEach(btn=>{
      btn.onclick=async()=>{
        const id=btn.dataset.id; const act=btn.dataset.act;
        if(act==='delete'){ if(!confirm('Supprimer user '+id+' ?')) return; await fetch(`${API}/api/admin/users/${id}`, {method:'DELETE', credentials:'include'}); toast('User supprimé'); loadAdminStats(); }
        else if(act==='premium'){
          await fetch(`${API}/api/admin/users/${id}/make-premium`, {method:'POST', credentials:'include', headers:{'Content-Type':'application/json'}, body:JSON.stringify({months:1})});
          toast('Premium toggled'); loadAdminStats();
        }
        else if(act==='admin'){
          await fetch(`${API}/api/admin/users/${id}/make-admin`, {method:'POST', credentials:'include'}); toast('Admin toggled'); loadAdminStats(); await checkAuth();
        }
      };
    });
  }catch(e){ console.warn('admin load fail',e); }
}
el('refreshAdmin') && (el('refreshAdmin').onclick=loadAdminStats);
el('exportUsers') && (el('exportUsers').onclick=async()=>{
  const r=await fetch(`${API}/api/admin/users`, {credentials:'include'});
  const j=await r.json();
  const blob=new Blob([JSON.stringify(j.users,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=url; a.download='users-export.json'; a.click();
});

// Init
(async()=>{
  // Check premium success in URL
  const params=new URLSearchParams(location.search);
  if(params.get('premium')==='success'){
    toast('🎉 Paiement réussi ! Bienvenue en Premium ⭐');
    // Attend webhook 2s puis refresh
    setTimeout(()=>checkAuth(),2000);
    history.replaceState({},'',location.pathname);
  }
  const ok=await checkAuth();
  if(ok){
    // interval refresh results
    await new Promise(r=>setTimeout(r,500));
    await loadAlerts();
    setInterval(loadAlerts,60000);
  }
})();
