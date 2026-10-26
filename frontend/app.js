/* FreelanceOS frontend. Uses the existing Flask REST API; no frontend build step. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const state = { token: localStorage.getItem('fmos_token'), user: JSON.parse(localStorage.getItem('fmos_user') || 'null'), page: 'home', charts: [], cache: {} };
  const authView = $('#authView'), appView = $('#appView'), pageContent = $('#pageContent');
  const apiBase = () => `${location.origin === 'null' ? 'http://127.0.0.1:5000' : location.origin}/api`;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = value => '$' + Number(value || 0).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:2});
  const date = value => value ? new Date(value).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'}) : 'No deadline';
  const timestamp = value => { if(!value)return 'Time unavailable'; const parsed=new Date(String(value).replace(' ','T')); return Number.isNaN(parsed.getTime())?esc(value):parsed.toLocaleString(undefined,{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit'}); };
  const initials = name => (name || 'U').trim().split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();
  const fmt = status => `<span class="status-pill ${esc(status)}">${esc((status || 'unknown').replaceAll('_',' '))}</span>`;

  async function request(path, options = {}) {
    const headers = {'Content-Type':'application/json', ...(options.headers || {})};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    let response;
    try { response = await fetch(`${apiBase()}${path}`, {...options, headers}); }
    catch { throw new Error('Cannot reach the Flask API. Make sure the Flask server is running.'); }
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) {
      const message = data?.error?.message || `Request failed (${response.status}).`;
      if (response.status === 401 && state.token && !path.endsWith('/login')) signOut(false);
      throw new Error(message);
    }
    return data;
  }
  const post = (path, body) => request(path, {method:'POST', body:JSON.stringify(body)});
  const patch = (path, body) => request(path, {method:'PATCH', body:JSON.stringify(body)});
  const put = (path, body) => request(path, {method:'PUT', body:JSON.stringify(body)});
  const del = path => request(path, {method:'DELETE'});
  function notify(message, kind='success') {
    const el = $('#globalAlert'); el.textContent = message; el.className = `global-alert ${kind === 'success' ? 'success' : ''}`;
    clearTimeout(notify.timer); notify.timer = setTimeout(()=>el.classList.add('d-none'), 4300);
  }
  function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.remove('d-none'); setTimeout(()=>el.classList.add('d-none'),2200); }
  function showAuthError(message) { const el=$('#authAlert'); el.textContent=message; el.className='alert alert-danger'; }
  function showAuthMessage(message, success=false) { const el=$('#authAlert'); el.textContent=message; el.className=`alert alert-${success?'success':'danger'}`; }
  function showApp() {
    if (!state.token || !state.user) { authView.classList.remove('d-none'); appView.classList.add('d-none'); return; }
    authView.classList.add('d-none'); appView.classList.remove('d-none');
    const user=state.user; $('#sideName').textContent=user.full_name; $('#sideEmail').textContent=user.email; $('#topName').textContent=user.full_name;
    $('#sideAvatar').textContent=initials(user.full_name); $('#topAvatar').textContent=initials(user.full_name);
    $('#workspaceRole').textContent=`${user.role[0].toUpperCase()}${user.role.slice(1)} workspace`;
    $('#projectsNavLabel').textContent=user.role==='client'?'My projects':'Find projects';
    $$('.admin-only').forEach(x=>x.classList.toggle('d-none',user.role!=='admin'));
    navigate(state.page || 'home'); refreshNotificationDot();
  }
  function signOut(callApi=true) {
    const logoutRequest = callApi && state.token ? post('/auth/logout',{}) : null;
    state.token=null; state.user=null; state.cache={}; localStorage.removeItem('fmos_token'); localStorage.removeItem('fmos_user');
    authView.classList.remove('d-none'); appView.classList.add('d-none');
    $('#notificationPanel').classList.add('d-none');
    $('#notificationList').textContent=''; $('#notificationDot').classList.add('d-none'); $('#notificationBtn').setAttribute('aria-expanded','false');
    $('#loginForm').reset(); $('#registerForm').reset(); $('#forgotPasswordForm').reset();
    authTab('login');
    $('#authAlert').classList.add('d-none');
    if (location.hash || location.search) history.replaceState({}, document.title, location.pathname);
    if (logoutRequest) logoutRequest.catch(error => showAuthMessage(`Signed out on this device, but server revocation failed: ${error.message}`, false));
  }
  // Capture clicks early so logout remains responsive if a later dashboard
  // component fails while registering its own handlers.
  document.addEventListener('click',e=>{
    const button=e.target.closest('#logoutBtn, #dashboardLogoutBtn');
    if(!button)return;
    e.preventDefault();
    signOut(true);
  },true);
  async function authenticate(form, mode) {
    const button=$('button[type="submit"]',form); button.disabled=true;
    try {
      const values=Object.fromEntries(new FormData(form).entries());
      const result=await post(`/auth/${mode}`,values);
      if(mode==='register') { notify('Account created. Sign in to open your workspace.'); authTab('login'); $('#loginForm [name="email"]').value=values.email; return; }
      state.token=result.access_token; state.user=result.user; state.page='home';
      localStorage.setItem('fmos_token',state.token); localStorage.setItem('fmos_user',JSON.stringify(state.user)); $('#authAlert').classList.add('d-none'); showApp();
    } catch(e) { showAuthError(e.message); } finally { button.disabled=false; }
  }
  function authTab(mode) {
    const reg=mode==='register'; $$('.auth-tab').forEach(t=>t.classList.toggle('active',t.dataset.authTab===mode));
    $('.auth-tabs').classList.remove('d-none');
    $('#loginForm').classList.toggle('d-none',reg); $('#registerForm').classList.toggle('d-none',!reg);
    $('#forgotPasswordForm').classList.add('d-none'); $('#forgotPasswordForm').reset();
    $('#authTitle').textContent=reg?'Create your account':'Welcome back'; $('#authSubtitle').textContent=reg?'A few details and your workspace is ready.':'Enter your details to access your workspace.'; $('#authAlert').classList.add('d-none');
  }
  function showForgotPassword() {
    $('.auth-tabs').classList.add('d-none'); $('#loginForm').classList.add('d-none'); $('#registerForm').classList.add('d-none');
    $('#forgotPasswordForm').classList.remove('d-none'); $('#authTitle').textContent='Reset your password';
    $('#authSubtitle').textContent='Enter your account email and choose a new password.'; $('#authAlert').classList.add('d-none');
  }
  async function requestPasswordReset(form) {
    const values=Object.fromEntries(new FormData(form).entries());
    if(values.password!==values.confirm_password) { showAuthError('The passwords do not match.'); return; }
    const button=$('button[type="submit"]',form),label=button.innerHTML; button.disabled=true;button.innerHTML='Resetting…';
    try { await post('/auth/forgot-password',{email:values.email,new_password:values.password}); authTab('login'); showAuthMessage('Password reset successfully. Please log in.',true); }
    catch(e) { showAuthError(e.message); } finally { button.disabled=false;button.innerHTML=label; }
  }
  function navigate(page) {
    state.page=page; $$('.nav-link').forEach(x=>x.classList.toggle('active',x.dataset.page===page));
    const labels={home:'Overview',projects:state.user?.role==='client'?'My projects':'Find projects',applications:'Applications',contracts:'Contracts & work',payments:'Payments',messages:'Messages',profile:'My profile',admin:'Administration',reports:'Reports',disputes:'Disputes'};
    $('#pageCrumb').textContent=labels[page]||'Overview'; $('#sidebar').classList.remove('open');
    ({home:renderHome,projects:renderProjects,applications:renderApplications,contracts:renderContracts,payments:renderPayments,messages:renderMessages,profile:renderProfile,admin:renderAdmin,reports:renderReports,disputes:renderDisputes}[page]||renderHome)();
  }
  function heading(title, subtitle, actions='') { return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${actions}</div></div>`; }
  function empty(title, body, action='') { return `<div class="empty-state"><div class="empty-icon">✳</div><h3>${title}</h3><p>${body}</p>${action}</div>`; }
  function loadingState(message='Loading…') { return `<div class="loading-state" role="status"><span class="spinner-border spinner-border-sm" aria-hidden="true"></span><span>${esc(message)}</span></div>`; }
  function button(label, action, cls='btn-primary-soft', attrs='') { return `<button class="btn ${cls}" data-action="${action}" ${attrs}>${label}</button>`; }
  function stat(label,value,icon,color,foot='') { return `<div class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon ${color}">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-foot">${foot}</div></div>`; }
  function panel(title,sub,content,chart=false) { return `<div class="panel-card"><div class="panel-title"><div><h3>${title}</h3><p>${sub}</p></div></div>${chart?`<div class="chart-wrap"><canvas id="${chart}"></canvas></div>`:content}</div>`; }
  function destroyCharts(){state.charts.forEach(c=>c.destroy());state.charts=[];}
  function makeChart(id, labels, values, type='bar', color='#7565e8') { const canvas=$(`#${id}`); if(!canvas||!window.Chart)return; const chart=new Chart(canvas,{type,data:{labels,datasets:[{data:values,backgroundColor:type==='line'?color:labels.map((_,i)=>[color,'#a99ef3','#cec8fa','#e2defd'][i%4]),borderColor:color,borderWidth:type==='line'?2:0,borderRadius:6,tension:.35,fill:type==='line'?{target:'origin',above:'rgba(117,101,232,.08)'}:false,pointRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{font:{size:11},color:'#9aa1ae'}},y:{beginAtZero:true,grid:{color:'#f0f1f4'},ticks:{font:{size:11},color:'#9aa1ae',precision:0}}}}});state.charts.push(chart); }
  async function safe(path, key) { try { const d=await request(path); state.cache[key]=d; return d; } catch(e) { notify(e.message,'error'); return {}; } }

  async function renderHome() {
    destroyCharts(); pageContent.innerHTML=`${heading(`Good ${new Date().getHours()<12?'morning':new Date().getHours()<18?'afternoon':'evening'}, ${esc((state.user?.full_name||'').split(' ')[0])} 👋`,'Here’s what’s happening in your workspace today.')}
      <div id="homeStats" class="stat-grid">${[1,2,3,4].map(()=>'<div class="stat-card"><div class="stat-foot">Loading your workspace…</div></div>').join('')}</div>
      <div class="dashboard-grid">${panel('Payment status mix','A snapshot of your payment ledger','', 'activityChart')}${panel('Next up','Items that may need your attention','<div id="upNext" class="activity-list"></div>')}</div>
      <div class="section-row"><h2>Recent projects</h2><button data-page="projects">View workspace →</button></div><div id="homeProjects" class="project-grid"></div>`;
    const role=state.user.role;
    const [projects,apps,contracts,payments,notifications,adminData]=await Promise.all([
      safe(role==='client'?'/projects/mine':role==='admin'?'/projects?limit=5':'/projects?limit=100','projects'),
      role==='freelancer'?safe('/applications/mine','applications'):Promise.resolve({}),
      safe('/contracts/mine','contracts'),safe('/payments/mine','payments'),safe('/notifications?limit=8','notifications'),
      role==='admin'?safe('/admin/reports/summary','adminSummary'):Promise.resolve({})]);
    const projectsAvailable=Array.isArray(projects.projects),applicationsAvailable=Array.isArray(apps.applications),contractsAvailable=Array.isArray(contracts.contracts),paymentsAvailable=Array.isArray(payments.payments),notificationsAvailable=Array.isArray(notifications.notifications);
    const ps=projects.projects||[], cs=contracts.contracts||[], pays=payments.payments||[];
    const aps=role==='freelancer'?(apps.applications||[]):[];
    const totalSpend=paymentsAvailable?pays.filter(p=>p.status==='completed').reduce((s,p)=>s+Number(p.amount),0):null;
    let activeTaskCount='—',ratingSummary=null;
    if(role==='freelancer'){
      const [taskResults,reviewData]=await Promise.all([Promise.allSettled(cs.map(c=>request(`/contracts/${c.contract_id}/tasks`))),request(`/reviews/users/${state.user.user_id}`).catch(()=>null)]);
      if(contractsAvailable&&taskResults.every(x=>x.status==='fulfilled'))activeTaskCount=taskResults.flatMap(x=>x.value.tasks||[]).filter(t=>t.status==='in_progress').length;
      ratingSummary=reviewData?.summary;
    }
    const ratingText=ratingSummary&&Number(ratingSummary.review_count)?`${Number(ratingSummary.average_rating).toFixed(1)} ★`:'—';
    const report=adminData.report||{},reportAvailable=Boolean(adminData.report);
    const totalRows=rows=>(rows||[]).reduce((sum,row)=>sum+Number(row.count||0),0);
    const projectRows=report.projects_by_status||[];
    const stats=role==='client'?[['My projects',projectsAvailable?ps.length:'—','▧','purple'],['Applications received','—','↗','blue'],['Active contracts',contractsAvailable?cs.filter(c=>c.status==='active').length:'—','▤','green'],['Total spending',paymentsAvailable?money(totalSpend):'—','◈','amber']]:role==='freelancer'?[['Open projects',projectsAvailable?ps.filter(p=>p.status==='open').length:'—','▧','purple'],['My applications',applicationsAvailable?aps.length:'—','↗','blue'],['Tasks in progress',activeTaskCount,'▤','green'],['Earnings',paymentsAvailable?money(totalSpend):'—','◈','amber'],['Rating',ratingText,'★','amber']]:[['Total users',reportAvailable?report.user_count:'—','◎','purple'],['Active projects',reportAvailable?projectRows.filter(x=>['open','in_progress'].includes(x.label)).reduce((n,x)=>n+Number(x.count||0),0):'—','▧','blue'],['Contracts',reportAvailable?totalRows(report.contracts_by_status):'—','▤','green'],['Payments',reportAvailable?totalRows(report.payments_by_status):'—','◈','amber'],['Disputes',reportAvailable?totalRows(report.disputes_by_status):'—','⚑','purple']];
    // Clients can inspect all their project applications without a separate aggregate endpoint.
    if(role==='client'&&projectsAvailable){
      const counts=await Promise.allSettled(ps.map(p=>request(`/projects/${p.project_id}/applications`)));
      stats[1][1]=counts.every(x=>x.status==='fulfilled')?counts.reduce((n,x)=>n+(x.value.applications||[]).length,0):'—';
    }
    $('#homeStats').innerHTML=stats.map(x=>stat(x[0],x[1],x[2],x[3],x[0]==='Earnings'?'Completed payments':x[0]==='Rating'?(ratingSummary?.review_count?`${ratingSummary.review_count} reviews`:'No reviews yet'):'' )).join('');
    const notif=notifications.notifications||[]; const attention=notif.slice(0,4);
    $('#upNext').innerHTML=notificationsAvailable?(attention.length?attention.map(n=>`<div class="activity-row"><div class="activity-icon">✦</div><div class="activity-copy">${esc(n.message)}<small>${date(n.created_at)}</small></div></div>`).join(''):`<div class="activity-row"><div class="activity-icon">✓</div><div class="activity-copy"><b>You're all caught up</b><small>New activity will show up here.</small></div></div>`):`<div class="activity-row"><div class="activity-icon">!</div><div class="activity-copy"><b>Activity unavailable</b><small>Notifications could not be loaded.</small></div></div>`;
    const recent=role==='client'?ps:ps.slice(0,5);
    $('#homeProjects').innerHTML=projectsAvailable?(recent.slice(0,3).map(projectCard).join('')||empty('No projects yet',role==='client'?'Create your first project and find the right freelancer.':'Browse open projects to find your next collaboration.',role==='client'?button('Create a project','create-project'):'')):empty('Projects unavailable','Project data could not be loaded. Please try again later.');
    const paymentStates=['pending','processing','completed','failed'];
    if(paymentsAvailable)makeChart('activityChart',paymentStates.map(x=>x[0].toUpperCase()+x.slice(1)),paymentStates.map(s=>pays.filter(p=>p.status===s).length),'bar');else $('#activityChart').parentElement.innerHTML='<div class="empty-state">Payment data is unavailable.</div>';
  }
  function projectCard(p) {
    const skills=(p.required_skills||[]).slice(0,4).map(s=>`<span class="skill-chip">${esc(s.name)}</span>`).join('');
    const isClient=state.user.role==='client',isFreelancer=state.user.role==='freelancer';
    return `<article class="project-card"><div class="project-card-top"><span class="category-chip">${esc(p.category_name||`Category #${p.category_id}`)}</span>${fmt(p.status)}</div><h3>${esc(p.title)}</h3><p>${esc(p.description)}</p><div class="skill-list">${skills||'<span class="skill-chip">Skills flexible</span>'}</div><div class="project-meta"><span>Budget<b>${money(p.budget_min)} – ${money(p.budget_max)}</b></span><span>Deadline<b>${esc(date(p.deadline))}</b></span></div><div class="card-actions">${isClient?`${p.status==='open'?`<button class="btn btn-outline-soft" data-action="project-apps" data-id="${p.project_id}">Applications</button>`:''}${['draft','open'].includes(p.status)?`<button class="btn btn-outline-soft" data-action="edit-project" data-id="${p.project_id}">Edit</button><button class="btn btn-outline-soft" data-action="cancel-project" data-id="${p.project_id}">Cancel</button>`:''}`:`<button class="btn btn-outline-soft" data-action="view-project" data-id="${p.project_id}">Details</button>${isFreelancer&&p.status==='open'?`<button class="btn btn-primary-soft" data-action="apply" data-id="${p.project_id}" data-title="${esc(p.title)}">Apply now</button>`:''}`}</div></article>`;
  }

  async function renderProjects() {
    destroyCharts(); const client=state.user.role==='client';
    pageContent.innerHTML=`${heading(client?'Your projects':'Find your next project',client?'Manage project listings and review incoming applications.':'Explore open work that fits your skills.',client?button('+ New project','create-project'):'')}
      ${client?'':`<div id="projectFilters" class="filter-bar"><input id="projectQuery" class="form-control filter-search" placeholder="Search projects by keyword…" aria-label="Search projects"><select id="projectCategory" class="form-select" aria-label="Filter by category"><option value="">All categories</option></select><input id="projectBudgetMin" class="form-control" type="number" min="0" placeholder="Min budget" aria-label="Minimum budget"><input id="projectBudgetMax" class="form-control" type="number" min="0" placeholder="Max budget" aria-label="Maximum budget"><select id="projectSkills" class="form-select skill-filter" multiple size="3" aria-label="Filter by required skills"><option disabled>Loading skills…</option></select><select id="projectType" class="form-select" aria-label="Project type"><option value="">Any type</option><option value="fixed">Fixed price</option><option value="hourly">Hourly</option></select><select id="projectSort" class="form-select" aria-label="Sort projects"><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="deadline">Deadline</option><option value="budget_low">Lowest budget</option><option value="budget_high">Highest budget</option></select><button class="btn btn-primary-soft" data-action="search-projects">Search</button></div>`}
      <div id="projectResults" class="project-grid">${loadingState('Loading projects…')}</div>`;
    if(!client){
      const [skillsResult,categoriesResult]=await Promise.allSettled([request('/skills'),request('/categories')]);
      const skillSelect=$('#projectSkills'),categorySelect=$('#projectCategory');
      if(skillsResult.status==='fulfilled')skillSelect.innerHTML=(skillsResult.value.skills||[]).map(s=>`<option value="${s.skill_id}">${esc(s.name)}</option>`).join('')||'<option disabled>No skills available</option>';
      else{skillSelect.innerHTML='<option disabled>Skills unavailable</option>';notify(`Skill filters unavailable: ${skillsResult.reason.message}`,'error');}
      if(categoriesResult.status==='fulfilled')categorySelect.innerHTML='<option value="">All categories</option>'+(categoriesResult.value.categories||[]).map(c=>`<option value="${c.category_id}">${esc(c.name)}</option>`).join('');
      else notify(`Category filters unavailable: ${categoriesResult.reason.message}`,'error');
      $('#projectFilters').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.id!=='projectSkills'){e.preventDefault();loadProjects();}});
    }
    await loadProjects();
  }
  async function loadProjects() {
    const client=state.user.role==='client'; let path='/projects/mine';
    const results=$('#projectResults');if(!results)return;results.innerHTML=loadingState(client?'Loading your projects…':'Searching projects…');results.setAttribute('aria-busy','true');
    const searchButton=$('[data-action="search-projects"]');if(searchButton){searchButton.disabled=true;searchButton.textContent='Searching…';}
    if(!client){const params=new URLSearchParams({limit:'100',sort:$('#projectSort')?.value||'newest'}); const q=$('#projectQuery')?.value.trim(),cat=$('#projectCategory')?.value,min=$('#projectBudgetMin')?.value,max=$('#projectBudgetMax')?.value,type=$('#projectType')?.value;if(q)params.set('q',q);if(cat)params.set('category_id',cat);if(min)params.set('budget_min',min);if(max)params.set('budget_max',max);if(type)params.set('project_type',type);for(const option of ($('#projectSkills')?.selectedOptions||[]))params.append('skill_id',option.value);path=`/projects?${params}`;}
    try{const data=await request(path);state.cache.projects=data.projects||[];results.innerHTML=state.cache.projects.map(projectCard).join('')||empty(client?'No projects created':'No matching projects',client?'Create your first listing to get started.':'Try changing your keyword, category, budget, skills, or sort order.',client?button('Create project','create-project'):'');}
    catch(e){results.innerHTML=empty('Unable to load projects',`${esc(e.message)} Please try again.`,button('Try again','search-projects','btn-outline-soft'));}
    finally{results.removeAttribute('aria-busy');if(searchButton){searchButton.disabled=false;searchButton.textContent='Search';}}
  }
  async function showApply(projectId,title) {
    showForm(`Apply to ${title}`,`<form id="applyForm" class="modal-form"><label>Proposal<textarea name="proposal" class="form-control" rows="4" placeholder="Tell the client how you’ll approach the project" required></textarea></label><div class="row g-2"><div class="col"><label>Bid amount<input name="bid_amount" type="number" min="0.01" step="0.01" class="form-control" required></label></div><div class="col"><label>Estimated days<input name="estimated_days" type="number" min="1" step="1" class="form-control" required></label></div></div><button class="btn btn-primary-soft" type="submit">Send application</button></form>`);
    $('#applyForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post(`/projects/${projectId}/applications`,{proposal:f.get('proposal'),bid_amount:f.get('bid_amount'),estimated_days:Number(f.get('estimated_days'))});bootstrap.Modal.getInstance($('#formModal')).hide();notify('Application submitted.');}catch(err){notify(err.message,'error');}};
  }
  async function showProjectForm(project={}) {
    const [skills,categories]=await Promise.all([request('/skills').catch(()=>({skills:[]})),request('/categories').catch(()=>({categories:[]}))]); const existing=project.required_skills||[]; const selected=new Set(existing.map(s=>Number(s.skill_id)));
    const categoryOptions=(categories.categories||[]).map(c=>`<option value="${c.category_id}" ${Number(project.category_id)===Number(c.category_id)?'selected':''}>${esc(c.name)}</option>`).join('');
    const fallbackCategory=project.category_id&&!categoryOptions?`<option value="${esc(project.category_id)}" selected>${esc(project.category_name||'Current category')}</option>`:'';
    showForm(project.project_id?'Edit project':'Create a project',`<form id="projectForm" class="modal-form"><label>Project title<input class="form-control" name="title" maxlength="180" value="${esc(project.title||'')}" required></label><label>Description<textarea class="form-control" name="description" rows="3" required>${esc(project.description||'')}</textarea></label><div class="row g-2"><div class="col"><label>Category<select class="form-select" name="category_id" required><option value="">Choose a category</option>${categoryOptions||fallbackCategory}</select></label></div><div class="col"><label>Project type<select class="form-select" name="project_type"><option value="fixed" ${project.project_type==='hourly'?'':'selected'}>Fixed price</option><option value="hourly" ${project.project_type==='hourly'?'selected':''}>Hourly</option></select></label></div></div><div class="row g-2"><div class="col"><label>Minimum budget<input class="form-control" name="budget_min" type="number" min="0" step="0.01" value="${esc(project.budget_min||'')}" required></label></div><div class="col"><label>Maximum budget<input class="form-control" name="budget_max" type="number" min="0" step="0.01" value="${esc(project.budget_max||'')}" required></label></div></div><label>Deadline<input class="form-control" name="deadline" type="date" value="${esc(project.deadline||'')}"></label><label>Required skills<select class="form-select" name="skill_ids" multiple size="4">${(skills.skills||[]).map(s=>`<option value="${s.skill_id}" ${selected.has(Number(s.skill_id))?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label><button class="btn btn-primary-soft" type="submit">${project.project_id?'Save changes':'Publish project'}</button></form>`);
    $('#projectForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.currentTarget);const data={title:fd.get('title'),description:fd.get('description'),category_id:Number(fd.get('category_id')),budget_min:fd.get('budget_min'),budget_max:fd.get('budget_max'),deadline:fd.get('deadline')||null,project_type:fd.get('project_type'),status:project.status||'open',skill_ids:$$('[name="skill_ids"] option:checked',$('#projectForm')).map(o=>Number(o.value))};try{if(project.project_id){delete data.status;await patch(`/projects/${project.project_id}`,data);}else await post('/projects',data);bootstrap.Modal.getInstance($('#formModal')).hide();notify('Project saved.');if(state.page==='projects')loadProjects();else renderHome();}catch(err){notify(err.message,'error');}};
  }
  async function showProject(projectId) { try{const {project:p}=await request(`/projects/${projectId}`);showDetails(p.title,`<div class="detail-stats"><div class="detail-stat"><small>Budget</small><b>${money(p.budget_min)} – ${money(p.budget_max)}</b></div><div class="detail-stat"><small>Client</small><b>${esc(p.client_name)}</b></div><div class="detail-stat"><small>Deadline</small><b>${esc(date(p.deadline))}</b></div></div><p class="detail-copy">${esc(p.description)}</p><div class="detail-section"><h4>Skills</h4><div class="skill-list">${(p.required_skills||[]).map(s=>`<span class="skill-chip">${esc(s.name)}</span>`).join('')||'No specific skills listed'}</div></div>`);}catch(e){notify(e.message,'error');} }
  async function showProjectApplications(projectId){try{const [pd,ad]=await Promise.all([request(`/projects/${projectId}`),request(`/projects/${projectId}/applications`)]);const rows=ad.applications||[];showDetails(`${pd.project.title} · Applications`,rows.length?`<div class="table-responsive"><table class="table"><thead><tr><th>Freelancer</th><th>Bid</th><th>Days</th><th>Status</th><th>Actions</th></tr></thead><tbody>${rows.map(a=>`<tr><td><b>${esc(a.freelancer_name)}</b><div class="small text-secondary">${esc(a.headline||'')}</div><div class="small text-secondary pt-1">${esc(a.proposal)}</div></td><td>${money(a.bid_amount)}</td><td>${a.estimated_days}</td><td>${fmt(a.status)}</td><td>${['pending','shortlisted'].includes(a.status)?`<div class="d-flex gap-1"><button class="btn btn-outline-soft" data-action="app-status" data-id="${a.application_id}" data-status="shortlisted">Shortlist</button><button class="btn btn-primary-soft" data-action="app-status" data-id="${a.application_id}" data-status="accepted" data-amount="${a.bid_amount}">Hire</button><button class="btn btn-outline-soft" data-action="app-status" data-id="${a.application_id}" data-status="rejected">Decline</button></div>`:'—'}</td></tr>`).join('')}</tbody></table></div>`:empty('No proposals yet','Applications from freelancers will appear here.'));}catch(e){notify(e.message,'error');}}

  async function renderApplications() {
    destroyCharts(); pageContent.innerHTML=`${heading('Applications','Track proposals, compare bids, and move work forward.')}<div id="applicationsArea"></div>`;
    const area=$('#applicationsArea');area.innerHTML=loadingState('Loading applications…');
    try{
      if(state.user.role==='freelancer') {
        const data=await request('/applications/mine');const rows=data.applications||[];
        area.innerHTML=rows.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>Project</th><th>Your bid</th><th>Delivery</th><th>Status</th><th>Submitted</th></tr></thead><tbody>${rows.map(a=>`<tr><td><b>${esc(a.project_title)}</b><div class="text-secondary small">${esc(a.category_name)}</div></td><td>${money(a.bid_amount)}</td><td>${a.estimated_days} days</td><td>${fmt(a.status)}</td><td>${date(a.applied_at)}</td></tr>`).join('')}</tbody></table></div>`:empty('No applications yet','Find an open project and send your first proposal.',button('Explore projects','page-projects'));
      } else if(state.user.role==='client') {
        const {projects=[]}=await request('/projects/mine');const results=await Promise.all(projects.map(async p=>{const d=await request(`/projects/${p.project_id}/applications`);return (d.applications||[]).map(a=>({...a,project_title:p.title}));}));const apps=results.flat();
        area.innerHTML=apps.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>Freelancer</th><th>Project</th><th>Bid</th><th>Delivery</th><th>Status</th><th>Action</th></tr></thead><tbody>${apps.map(a=>`<tr><td><b>${esc(a.freelancer_name)}</b><div class="small text-secondary">${esc(a.headline||'Freelancer')}</div></td><td>${esc(a.project_title)}</td><td>${money(a.bid_amount)}</td><td>${a.estimated_days} days</td><td>${fmt(a.status)}</td><td>${a.status==='pending'||a.status==='shortlisted'?`<div class="d-flex gap-1"><button class="btn btn-outline-soft" data-action="app-status" data-id="${a.application_id}" data-status="shortlisted">Shortlist</button><button class="btn btn-primary-soft" data-action="app-status" data-id="${a.application_id}" data-status="accepted" data-amount="${a.bid_amount}">Hire</button><button class="btn btn-outline-soft" data-action="app-status" data-id="${a.application_id}" data-status="rejected">Decline</button></div>`:'—'}</td></tr><tr><td colspan="6" class="text-secondary small">Proposal: ${esc(a.proposal)}</td></tr>`).join('')}</tbody></table></div>`:empty('No proposals yet','Applications will appear here when freelancers respond to your projects.',button('View projects','page-projects'));
      } else area.innerHTML=empty('Applications are participant-owned','Sign in as a client or freelancer to manage project applications.');
    }catch(e){area.innerHTML=empty('Applications could not load',esc(e.message));}
  }
  async function changeApplication(id,status,amount) { const body={status};if(status==='accepted'){const v=prompt('Agreed contract amount',amount);if(v===null)return;if(Number(v)<=0)return notify('Enter a valid amount.','error');body.agreed_amount=v;}try{const result=await patch(`/applications/${id}/status`,body);bootstrap.Modal.getInstance($('#genericModal'))?.hide();notify(status==='accepted'?`Contract #${result.contract_id} created.`:`Application ${status}.`);if(state.page==='applications')renderApplications();else if(state.page==='projects')loadProjects();else renderHome();}catch(e){notify(e.message,'error');} }

  async function renderContracts() {
    destroyCharts();pageContent.innerHTML=`${heading('Contracts & work','Keep delivery, milestones, and communication moving.')}<div id="contractsArea">${loadingState('Loading contracts and work progress…')}</div>`;
    const area=$('#contractsArea');
    try{
      const [data,paymentResult]=await Promise.all([request('/contracts/mine'),request('/payments/mine').then(value=>({value})).catch(error=>({error}))]);
      const payments=paymentResult.value?.payments||null;
      const contracts=(data.contracts||[]).slice().sort((a,b)=>(a.status==='active'?-1:0)-(b.status==='active'?-1:0));
      const summaries=await Promise.all(contracts.map(async c=>{
        try{
          const [taskData,mileData]=await Promise.all([request(`/contracts/${c.contract_id}/tasks`),request(`/contracts/${c.contract_id}/milestones`)]);
          const tasks=taskData.tasks||[],milestones=mileData.milestones||[];
          const contractPayments=payments?.filter(p=>Number(p.contract_id)===Number(c.contract_id))||[];
          const tasksDone=tasks.filter(t=>t.status==='completed').length;
          const milestonesDone=milestones.filter(m=>['approved','paid'].includes(m.status)||contractPayments.some(p=>Number(p.milestone_id)===Number(m.milestone_id)&&p.status==='completed')).length;
          const workCount=tasks.length+milestones.length,doneCount=tasksDone+milestonesDone;
          const settled=contractPayments.filter(p=>p.status==='completed').length;
          const pending=contractPayments.filter(p=>['pending','processing'].includes(p.status)).length;
          return {contract:c,tasks,milestones,tasksDone,milestonesDone,progress:workCount?Math.round(doneCount/workCount*100):null,settled,pending,available:true};
        }catch{return {contract:c,available:false};}
      }));
      area.innerHTML=summaries.length?`<div class="contract-grid">${summaries.map(s=>{const c=s.contract;return `<article class="contract-card"><div class="contract-card-head"><div><h3>${esc(c.project_title)}</h3><p>Contract #${c.contract_id} · Started ${date(c.start_date)}</p></div>${fmt(c.status)}</div><div class="contract-stats"><span><small>Contract value</small><b>${money(c.agreed_amount)}</b></span><span><small>Project</small><b>#${c.project_id}</b></span><span><small>Role</small><b>${state.user.role==='client'?'Client':state.user.role==='admin'?'Admin':'Freelancer'}</b></span></div>${s.available?`<div class="contract-progress"><div class="progress-heading"><span>Project progress</span><b>${s.progress===null?'No work items':`${s.progress}%`}</b></div>${s.progress===null?'<p class="small text-secondary mb-2">Tasks and milestones have not been added yet.</p>':`<div class="progress" role="progressbar" aria-label="Contract work progress" aria-valuenow="${s.progress}" aria-valuemin="0" aria-valuemax="100"><div class="progress-bar" style="width:${s.progress}%"></div></div>`}<div class="progress-foot"><span>Tasks ${s.tasksDone}/${s.tasks.length} complete</span><span>Milestones ${s.milestonesDone}/${s.milestones.length} approved</span></div><div class="progress-foot payment-progress"><span>Payments ${payments===null?'unavailable':`${s.settled} settled${s.pending?` · ${s.pending} pending`:''}`}</span></div></div>`:'<p class="small text-secondary mt-3 mb-0">Work progress could not load.</p>'}<div class="card-actions"><button class="btn btn-primary-soft" data-action="contract-detail" data-id="${c.contract_id}">Open workspace</button></div></article>`;}).join('')}</div>`:empty('No contracts yet','Once a client accepts a proposal, the contract workspace appears here.',state.user.role==='freelancer'?button('Browse projects','page-projects'):'');
    }catch(e){area.innerHTML=empty('Contracts could not load',esc(e.message));}
  }
  async function openContract(id) {
    try{
      const [ct,tasks,miles,msgs,disputeData,paymentData]=await Promise.all([request(`/contracts/${id}`),request(`/contracts/${id}/tasks`),request(`/contracts/${id}/milestones`),state.user.role==='admin'?Promise.resolve({messages:[]}):request(`/contracts/${id}/messages`),state.user.role==='admin'?Promise.resolve({disputes:[]}):request('/disputes/mine'),request('/payments/mine')]);
      const c=ct.contract, client=state.user.role==='client';
      const caseRows=(disputeData.disputes||[]).filter(d=>Number(d.contract_id)===Number(id));
      const contractPayments=(paymentData.payments||[]).filter(p=>Number(p.contract_id)===Number(id));
      let reviewSection='';
      if(state.user.role!=='admin'&&c.status==='completed'){
        const revieweeId=client?c.freelancer_id:c.client_id;
        try{
          const reviewData=await request(`/reviews/users/${revieweeId}`);
          const prior=(reviewData.reviews||[]).find(r=>Number(r.contract_id)===Number(id)&&Number(r.reviewer_id)===Number(state.user.user_id));
          reviewSection=prior
            ?`<div class="detail-section review-recorded"><h4>Your review</h4><p><strong>${Number(prior.rating)} / 5 ★</strong>${prior.comment?` · ${esc(prior.comment)}`:''}</p></div>`
            :`<div class="detail-section"><h4>Leave a review</h4><form id="reviewForm" class="message-compose"><select name="rating" class="form-select" style="max-width:120px" aria-label="Rating"><option value="5">5 stars</option><option value="4">4 stars</option><option value="3">3 stars</option><option value="2">2 stars</option><option value="1">1 star</option></select><input name="comment" class="form-control" placeholder="Share a quick note"><button class="btn btn-outline-soft">Review</button></form></div>`;
        }catch{
          reviewSection='<div class="detail-section"><p class="text-secondary small">Review status could not be checked.</p></div>';
        }
      }
      const taskHtml=(tasks.tasks||[]).map(t=>`<div class="work-row"><div><b>${esc(t.title)}</b><small>Due ${esc(date(t.due_date))} · ${fmt(t.status)}</small></div><div>${client&&t.status==='submitted'?`<button class="btn btn-primary-soft" data-action="task-status" data-id="${t.task_id}" data-status="completed" data-contract="${id}">Complete</button>`:state.user.role==='freelancer'&&['todo','in_progress'].includes(t.status)?`<button class="btn btn-outline-soft" data-action="task-status" data-id="${t.task_id}" data-status="${t.status==='todo'?'in_progress':'submitted'}" data-contract="${id}">${t.status==='todo'?'Start':'Submit'}</button>`:''}</div></div>`).join('')||'<p class="text-secondary small">No tasks yet.</p>';
      const mileHtml=(miles.milestones||[]).map(m=>{const related=contractPayments.filter(p=>Number(p.milestone_id)===Number(m.milestone_id));const paymentState=related.some(p=>p.status==='completed')?'completed':related[0]?.status||'not recorded';return `<div class="work-row"><div><b>${esc(m.title)} · ${money(m.amount)}</b><small>Due ${esc(date(m.due_date))} · Work ${fmt(m.status)} · Payment ${fmt(paymentState)}</small></div><div>${state.user.role==='freelancer'&&['pending','rejected'].includes(m.status)?`<button class="btn btn-outline-soft" data-action="milestone-submit" data-id="${m.milestone_id}" data-contract="${id}">Submit</button>`:''}${client&&m.status==='submitted'?`<button class="btn btn-outline-soft" data-action="milestone-review" data-id="${m.milestone_id}" data-status="rejected" data-contract="${id}">Request changes</button><button class="btn btn-primary-soft" data-action="milestone-review" data-id="${m.milestone_id}" data-status="approved" data-contract="${id}">Approve</button>`:''}${client&&m.status==='approved'?`<button class="btn btn-primary-soft" data-action="pay-milestone" data-id="${m.milestone_id}" data-amount="${m.amount}" data-contract="${id}">Pay</button>`:''}</div></div>`;}).join('')||'<p class="text-secondary small">No milestones yet.</p>';
      const messages=(msgs.messages||[]).map(m=>`<div class="message-bubble ${Number(m.sender_id)===Number(state.user.user_id)?'mine':''}">${esc(m.body)}<small>${esc(m.sender_name)} · ${date(m.sent_at)} ${m.read_at?'· Read':''}</small></div>`).join('');
      showDetails(c.project_title,`<div class="detail-stats"><div class="detail-stat"><small>Contract value</small><b>${money(c.agreed_amount)}</b></div><div class="detail-stat"><small>Started</small><b>${date(c.start_date)}</b></div><div class="detail-stat"><small>Status</small><b>${esc(c.status)}</b></div></div>
        <div class="detail-section"><div class="d-flex justify-content-between align-items-center"><h4>Tasks</h4>${client?button('+ Add task','add-task','btn-outline-soft',`data-contract="${id}"`):''}</div>${taskHtml}</div>
        <div class="detail-section"><div class="d-flex justify-content-between align-items-center"><h4>Milestones</h4>${client?button('+ Add milestone','add-milestone','btn-outline-soft',`data-contract="${id}"`):''}</div>${mileHtml}</div>
        <div class="detail-section"><h4>Messages</h4><div class="message-thread">${messages||'<p class="text-secondary small">Start the conversation with your project partner.</p>'}</div><form id="messageForm" class="message-compose"><input name="body" class="form-control" placeholder="Write a message…" required><button class="btn btn-primary-soft">Send</button></form></div>
        ${client&&c.status==='active'?`<div class="detail-section d-flex gap-2">${button('Record project payment','pay-contract','btn-outline-soft',`data-contract="${id}" data-amount="${c.agreed_amount}"`)}${button('Complete contract','complete-contract','btn-primary-soft',`data-contract="${id}"`)}</div>`:''}
        ${state.user.role!=='admin'&&c.status!=='cancelled'?`<div class="detail-section"><button class="btn btn-outline-soft" data-action="open-dispute" data-contract="${id}">Open a dispute</button>${caseRows.map(d=>`<div class="work-row"><div><b>Dispute #${d.dispute_id} · ${esc(d.reason)}</b><small>${fmt(d.status)} ${d.resolution?`· ${esc(d.resolution)}`:''}</small></div></div>`).join('')}</div>`:''}
        ${reviewSection}`);
      if($('#messageForm'))$('#messageForm').onsubmit=async e=>{e.preventDefault();try{await post(`/contracts/${id}/messages`,{body:new FormData(e.currentTarget).get('body')});openContract(id);}catch(err){notify(err.message,'error');}};
      if($('#reviewForm'))$('#reviewForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post(`/contracts/${id}/reviews`,{rating:Number(f.get('rating')),comment:f.get('comment')||null});notify('Review submitted.');openContract(id);}catch(err){notify(err.message,'error');}};
    }catch(e){notify(e.message,'error');}
  }

  async function renderPayments() {
    destroyCharts();pageContent.innerHTML=`${heading('Payments','A clear record of money moving through your work.')}<div id="paymentsArea"></div>`;
    const data=await safe('/payments/mine','payments'),payments=data.payments||[];const total=payments.filter(p=>p.status==='completed').reduce((n,p)=>n+Number(p.amount),0);
    const table=payments.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>Payment</th><th>Contract</th><th>${state.user.role==='client'?'Paid to':'Paid by'}</th><th>Amount</th><th>Status</th><th>Date</th><th>Transaction</th></tr></thead><tbody>${payments.map(p=>`<tr><td><b>Payment #${p.payment_id}</b>${p.milestone_id?`<div class="small text-secondary">Milestone #${p.milestone_id}</div>`:''}</td><td>#${p.contract_id}</td><td>${esc(state.user.role==='client'?p.payee_name:p.payer_name)}</td><td>${money(p.amount)}</td><td>${fmt(p.status)}</td><td>${date(p.paid_at||p.created_at)}</td><td>${esc(p.transaction_reference||'—')}</td></tr>`).join('')}</tbody></table></div>`:empty('No payment activity','Payments will appear after they are initiated on a contract.');
    pageContent.insertAdjacentHTML('afterbegin',`<div class="stat-grid">${stat(state.user.role==='freelancer'?'Received':'Paid',money(total),'◈','green','Completed transactions')}${stat('Transactions',payments.length,'↗','purple','All recorded activity')}${stat('Pending',payments.filter(p=>['pending','processing'].includes(p.status)).length,'◷','amber','Awaiting settlement')}${state.user.role==='admin'?stat('Unique payees',new Set(payments.map(p=>p.payee_id)).size,'◎','blue','Platform overview'):''}</div>`);
    $('#paymentsArea').innerHTML=table;
  }
  async function renderMessages() {
    destroyCharts();pageContent.innerHTML=`${heading('Messages','Your contract conversations, all together.')}<div id="messagesArea"></div>`;
    if(state.user.role==='admin'){$('#messagesArea').innerHTML=empty('Messages are private to participants','Admins do not access contract conversation content.');return;}
    const {contracts=[]}=await safe('/contracts/mine','contracts');if(!contracts.length){$('#messagesArea').innerHTML=empty('No conversations yet','Messages are available inside an active contract workspace.');return;}
    const ordered=contracts.slice().sort((a,b)=>(a.status==='active'?-1:0)-(b.status==='active'?-1:0));
    $('#messagesArea').innerHTML=`<section class="messages-layout"><aside class="conversation-panel"><div class="conversation-panel-head"><h2>Conversations</h2><input id="conversationSearch" class="form-control" type="search" placeholder="Search conversations…" aria-label="Search conversations"></div><div id="conversationList" class="conversation-list">${ordered.map((c,i)=>`<button class="conversation-item ${i===0?'active':''}" type="button" data-message-contract="${c.contract_id}" data-title="${esc(c.project_title)}"><span class="conversation-avatar">${esc(initials(c.project_title))}</span><span class="conversation-copy"><b>${esc(c.project_title)}</b><small>Contract #${c.contract_id}</small></span><span class="conversation-status">${fmt(c.status)}</span></button>`).join('')}</div></aside><section class="conversation-view" id="conversationView" aria-live="polite">${loadingState('Loading conversation…')}</section></section>`;
    const list=$('#conversationList');
    $('#conversationSearch').addEventListener('input',e=>{const q=e.currentTarget.value.trim().toLowerCase();$$('.conversation-item',list).forEach(item=>{item.hidden=!item.textContent.toLowerCase().includes(q);});});
    list.addEventListener('click',e=>{const item=e.target.closest('[data-message-contract]');if(!item)return;$$('.conversation-item',list).forEach(row=>row.classList.toggle('active',row===item));loadMessageConversation(item.dataset.messageContract,item.dataset.title);});
    loadMessageConversation(ordered[0].contract_id,ordered[0].project_title);
  }
  async function loadMessageConversation(id,title) {
    const view=$('#conversationView');if(!view)return;view.innerHTML=loadingState('Loading messages…');
    try{
      const [contractData,messageData]=await Promise.all([request(`/contracts/${id}`),request(`/contracts/${id}/messages`)]);
      const contract=contractData.contract,messages=messageData.messages||[];
      view.innerHTML=`<header class="conversation-header"><div class="conversation-avatar">${esc(initials(title))}</div><div><h2>${esc(title)}</h2><p>Contract #${esc(id)} · ${fmt(contract.status)}</p></div><button class="btn btn-outline-soft" data-action="contract-detail" data-id="${esc(id)}">Open workspace</button></header><div class="conversation-thread">${messages.length?messages.map(m=>`<div class="message-bubble ${Number(m.sender_id)===Number(state.user.user_id)?'mine':''}">${esc(m.body)}<small>${esc(m.sender_name)} · ${date(m.sent_at)}${m.read_at?' · Read':''}</small></div>`).join(''):'<div class="conversation-empty">No messages yet. Start the conversation with your project partner.</div>'}</div><form id="conversationCompose" class="conversation-compose"><input name="body" class="form-control" placeholder="Write a message…" aria-label="Write a message" required><button class="btn btn-primary-soft">Send</button></form>`;
      $('#conversationCompose').onsubmit=async e=>{e.preventDefault();const body=new FormData(e.currentTarget).get('body')?.toString().trim();if(!body)return;const submit=e.currentTarget.querySelector('button[type="submit"]')||e.currentTarget.querySelector('button');submit.disabled=true;try{await post(`/contracts/${id}/messages`,{body});await loadMessageConversation(id,title);}catch(err){notify(err.message,'error');submit.disabled=false;}};
    }catch(e){view.innerHTML=empty('Messages could not load',esc(e.message),`<button class="btn btn-outline-soft" data-action="message-retry" data-id="${esc(id)}" data-title="${esc(title)}">Try again</button>`);}
  }
  async function renderProfile() {
    destroyCharts();pageContent.innerHTML=`${heading('My profile','Keep your account details current and your profile complete.')}<div id="profileArea">${loadingState('Loading your profile…')}</div>`;
    try {
      const [userData,profileData]=await Promise.all([request('/users/me'),state.user.role==='client'?request('/clients/me'):state.user.role==='freelancer'?request('/freelancers/me'):Promise.resolve({profile:{}})]);
      const user=userData.user,profile=profileData.profile||{},freelancer=state.user.role==='freelancer',client=state.user.role==='client';
      const [skillResult,mySkillResult,portfolioResult,ratingResult]=freelancer?await Promise.all([
        request('/skills').then(data=>({data})).catch(error=>({error})),
        request('/skills/me').then(data=>({data})).catch(error=>({error})),
        request('/freelancers/me/portfolio').then(data=>({data})).catch(error=>({error})),
        request(`/reviews/users/${state.user.user_id}`).then(data=>({data})).catch(error=>({error}))
      ]):[{}, {}, {}, {}];
      const skills=skillResult.data?.skills||[],myskills=mySkillResult.data?.skills||[],portfolio=portfolioResult.data?.portfolio||[],rating=ratingResult.data?.summary;
      const chosen=new Map(myskills.map(s=>[Number(s.skill_id),s.proficiency_level]));
      const skillSummary=skillResult.error?'Skills are unavailable.':mySkillResult.error?'Skill profile is unavailable.':myskills.length?myskills.map(s=>`<span class="skill-chip">${esc(s.name)} · level ${s.proficiency_level}</span>`).join(''):'No skills added yet.';
      const ratingSummary=ratingResult.error?'Rating unavailable':Number(rating?.review_count)?`${Number(rating.average_rating).toFixed(1)} ★ · ${rating.review_count} reviews`:'Not rated yet';
      const portfolioHtml=portfolioResult.error?empty('Portfolio unavailable',esc(portfolioResult.error.message)):portfolio.length?portfolio.map(x=>`<article class="project-card"><h3>${esc(x.title)}</h3><p>${esc(x.description||'')}</p>${x.project_url?`<a class="small" target="_blank" rel="noopener" href="${esc(x.project_url)}">View project ↗</a>`:''}<div class="card-actions"><button class="btn btn-outline-soft" data-action="delete-portfolio" data-id="${x.portfolio_id}">Remove</button></div></article>`).join(''):empty('Showcase your work','Add a portfolio item so clients can see what you make.');
      $('#profileArea').innerHTML=`<div class="profile-layout"><aside class="panel-card profile-intro"><div class="profile-avatar">${initials(user.full_name)}</div><h3>${esc(user.full_name)}</h3><p>${esc(freelancer?profile.headline||'Freelancer':client?profile.company_name||'Client':'Administrator')}<br>${esc(user.email)}</p>${freelancer?`<p class="profile-bio">${esc(profile.bio||'Add a short bio to introduce your work.')}</p><div class="profile-preview-skills">${skillSummary}</div><div class="profile-highlights"><div><small>Hourly rate</small><b>${money(profile.hourly_rate)}/hr</b></div><div><small>Experience</small><b>${Number(profile.experience_years||0)} years</b></div><div><small>Availability</small><b>${esc(profile.availability_status||'Not set')}</b></div><div><small>Rating</small><b>${esc(ratingSummary)}</b></div></div><div class="profile-stats"><div><b>${mySkillResult.error?'—':myskills.length}</b><small>Skills</small></div><div><b>${portfolioResult.error?'—':portfolio.length}</b><small>Portfolio</small></div></div>`:''}</aside><div class="panel-card"><div class="panel-title"><div><h3>Account details</h3><p>Your account${freelancer?' and freelancer profile':client?' and client profile':''}.</p></div></div><form id="profileForm" class="profile-form"><label>Full name<input class="form-control" name="full_name" value="${esc(user.full_name)}" required></label><label>Email address<input class="form-control" type="email" name="email" value="${esc(user.email)}" required></label>${freelancer?`<label class="span-2">Professional headline<input class="form-control" name="headline" value="${esc(profile.headline||'')}"></label><label class="span-2">Bio<textarea class="form-control" name="bio" rows="3">${esc(profile.bio||'')}</textarea></label><label>Hourly rate<input class="form-control" name="hourly_rate" type="number" min="0" step="0.01" value="${esc(profile.hourly_rate||0)}"></label><label>Experience in years<input class="form-control" name="experience_years" type="number" min="0" value="${esc(profile.experience_years||0)}"></label><label>Location<input class="form-control" name="location" value="${esc(profile.location||'')}"></label><label>Availability<select class="form-select" name="availability_status"><option value="available" ${profile.availability_status==='available'?'selected':''}>Available</option><option value="busy" ${profile.availability_status==='busy'?'selected':''}>Busy</option><option value="unavailable" ${profile.availability_status==='unavailable'?'selected':''}>Unavailable</option></select></label><label class="span-2">Skills and proficiency<select class="form-select" name="skill_ids" multiple size="5">${skillResult.error?'<option disabled>Skill catalog unavailable</option>':skills.map(s=>`<option value="${s.skill_id}" ${chosen.has(Number(s.skill_id))?'selected':''}>${esc(s.name)}${chosen.has(Number(s.skill_id))?` · level ${chosen.get(Number(s.skill_id))}`:''}</option>`).join('')}</select><small class="text-secondary">Select your skills; selected levels default to your current value or 3.</small></label>`:client?`<label>Company name<input class="form-control" name="company_name" value="${esc(profile.company_name||'')}"></label><label>Location<input class="form-control" name="location" value="${esc(profile.location||'')}"></label><label>Website<input class="form-control" name="website" type="url" value="${esc(profile.website||'')}"></label><label class="span-2">About<textarea class="form-control" name="bio" rows="3">${esc(profile.bio||'')}</textarea></label>`:''}<div class="span-2"><button class="btn btn-primary-soft">Save profile</button></div></form></div></div>${freelancer?`<div class="section-row"><h2>Portfolio</h2>${button('+ Add item','add-portfolio','btn-primary-soft')}</div><div id="portfolioList" class="project-grid">${portfolioHtml}</div>`:''}`;
      $('#profileForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await patch('/users/me',{full_name:f.get('full_name'),email:f.get('email')});if(freelancer){await patch('/freelancers/me',{headline:f.get('headline')||null,bio:f.get('bio')||null,hourly_rate:f.get('hourly_rate'),experience_years:Number(f.get('experience_years')),location:f.get('location')||null,availability_status:f.get('availability_status')});if(!skillResult.error&&!mySkillResult.error){const arr=$$('[name="skill_ids"] option:checked',e.currentTarget).map(o=>({skill_id:Number(o.value),proficiency_level:chosen.get(Number(o.value))||3}));await put('/skills/me',{skills:arr});}}else if(client){await patch('/clients/me',{company_name:f.get('company_name')||null,location:f.get('location')||null,website:f.get('website')||null,bio:f.get('bio')||null});}state.user.full_name=f.get('full_name');state.user.email=f.get('email');localStorage.setItem('fmos_user',JSON.stringify(state.user));notify('Profile saved.');showApp();}catch(err){notify(err.message,'error');}};
    }catch(e){$('#profileArea').innerHTML=empty('Profile could not load',esc(e.message));}
  }
  async function renderAdmin() {
    if(state.user.role!=='admin')return navigate('home');destroyCharts();pageContent.innerHTML=`${heading('Administration','Manage platform accounts and monitor transactions.')}<div class="stat-grid" id="adminStats">${loadingState('Loading platform statistics…')}</div><div class="section-row"><h2>Users</h2><div class="d-flex gap-2"><input id="adminUserQuery" class="form-control" placeholder="Search name or email"><button class="btn btn-outline-soft" data-action="admin-search">Search</button></div></div><div id="adminUsers">${loadingState('Loading users…')}</div><div class="section-row"><h2>Recent transactions</h2></div><div id="adminPayments">${loadingState('Loading payments…')}</div>`;
    const [usersResult,paymentsResult,reportResult]=await Promise.allSettled([request('/users?limit=100'),request('/payments/mine'),request('/admin/reports/summary')]);
    const report=reportResult.status==='fulfilled'?reportResult.value.report||{}:{};
    const sumRows=rows=>(rows||[]).reduce((sum,row)=>sum+Number(row.count||0),0);
    const activeProjects=(report.projects_by_status||[]).filter(x=>['open','in_progress'].includes(x.label)).reduce((sum,row)=>sum+Number(row.count||0),0);
    const reportOk=reportResult.status==='fulfilled'&&Boolean(reportResult.value.report);
    $('#adminStats').innerHTML=[stat('Total users',reportOk?report.user_count:'—','◎','purple','Registered accounts'),stat('Active projects',reportOk?activeProjects:'—','▧','blue','Open or in progress'),stat('Contracts',reportOk?sumRows(report.contracts_by_status):'—','▤','green','All contract statuses'),stat('Payments',reportOk?sumRows(report.payments_by_status):'—','◈','amber','Recorded transactions'),stat('Disputes',reportOk?sumRows(report.disputes_by_status):'—','⚑','purple','All dispute statuses')].join('');
    if(usersResult.status==='fulfilled')renderAdminUsers(usersResult.value.users||[]);else $('#adminUsers').innerHTML=empty('Users could not load',esc(usersResult.reason.message));
    if(paymentsResult.status==='fulfilled')renderAdminPayments(paymentsResult.value.payments||[]);else $('#adminPayments').innerHTML=empty('Payments could not load',esc(paymentsResult.reason.message));
    if(!reportOk)notify(reportResult.reason.message,'error');
  }
  function renderAdminUsers(users){$('#adminUsers').innerHTML=users.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>User</th><th>Role</th><th>Joined</th><th>Status</th><th>Update status</th></tr></thead><tbody>${users.map(u=>`<tr><td><b>${esc(u.full_name)}</b><div class="small text-secondary">${esc(u.email)}</div></td><td>${esc(u.role)}</td><td>${date(u.created_at)}</td><td>${fmt(u.account_status)}</td><td><select class="form-select form-select-sm" data-user-status="${u.user_id}" style="max-width:140px"><option value="active" ${u.account_status==='active'?'selected':''}>Active</option><option value="suspended" ${u.account_status==='suspended'?'selected':''}>Suspended</option><option value="closed" ${u.account_status==='closed'?'selected':''}>Closed</option></select></td></tr>`).join('')}</tbody></table></div>`:empty('No users found','Try a different search.');}
  function renderAdminPayments(payments){$('#adminPayments').innerHTML=payments.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>Payment</th><th>Parties</th><th>Amount</th><th>Status</th><th>Transaction reference</th><th>Action</th></tr></thead><tbody>${payments.map(p=>`<tr><td><b>#${p.payment_id}</b><div class="small text-secondary">Contract #${p.contract_id}</div></td><td>${esc(p.payer_name)} → ${esc(p.payee_name)}</td><td>${money(p.amount)}</td><td>${fmt(p.status)}</td><td>${esc(p.transaction_reference||'—')}</td><td>${['pending','processing','completed'].includes(p.status)?`<button class="btn btn-outline-soft" data-action="advance-payment" data-id="${p.payment_id}" data-status="${p.status}">${p.status==='pending'?'Process':p.status==='processing'?'Settle':'Refund'}</button>`:'—'}</td></tr>`).join('')}</tbody></table></div>`:empty('No payments yet','Transactions will show here as contracts progress.');}

  async function renderReports(){
    destroyCharts();pageContent.innerHTML=`${heading('Platform reports','Live totals and breakdowns from the MySQL reporting views.')}<div class="stat-grid" id="reportStats"></div><div class="dashboard-grid"><div id="reportCharts"></div><div id="reportBreakdowns"></div></div><div class="dashboard-grid"><div id="earningsReport"></div><div id="spendingReport"></div></div>`;
    const [summaryData,earningsData,spendingData]=await Promise.all([safe('/admin/reports/summary','report'),safe('/admin/reports/earnings','earnings'),safe('/admin/reports/spending','spending')]);
    const r=summaryData.report||{}, openDisputes=(r.disputes_by_status||[]).filter(x=>['open','investigating'].includes(x.label)).reduce((n,x)=>n+Number(x.count),0);
    $('#reportStats').innerHTML=[stat('Platform users',r.user_count||0,'◎','purple','All registered roles'),stat('Projects',r.project_count||0,'▧','blue','All project statuses'),stat('Settled volume',money(r.completed_payment_volume),'◈','green','Completed payment records'),stat('Open disputes',openDisputes,'⚑','amber','Open or investigating')].join('');
    $('#reportCharts').innerHTML=`<div class="panel-card"><div class="panel-title"><div><h3>Projects by status</h3><p>Current platform distribution</p></div></div><div class="small-chart"><canvas id="projectStatusChart"></canvas></div></div><div class="panel-card mt-3"><div class="panel-title"><div><h3>Users by role</h3><p>Registered account mix</p></div></div><div class="small-chart"><canvas id="userRoleChart"></canvas></div></div>`;
    $('#reportBreakdowns').innerHTML=`<div class="panel-card"><div class="panel-title"><div><h3>Applications</h3><p>Submissions grouped by status</p></div></div>${reportTable(r.applications_by_status||[])}</div><div class="panel-card mt-3"><div class="panel-title"><div><h3>Payments</h3><p>Recorded transaction totals</p></div></div>${reportTable(r.payments_by_status||[],true)}</div><div class="panel-card mt-3"><div class="panel-title"><div><h3>Disputes</h3><p>Case status distribution</p></div></div>${reportTable(r.disputes_by_status||[])}</div><div class="panel-card mt-3"><div class="panel-title"><div><h3>Reviews by role</h3><p>Average rating received</p></div></div>${ratingReportTable(r.reviews_by_role||[])}</div>`;
    $('#earningsReport').innerHTML=`<div class="panel-card"><div class="panel-title"><div><h3>Freelancer earnings</h3><p>Completed payment volume by payee</p></div></div>${peopleReportTable(earningsData.earnings||[],'freelancer_id','total_earnings')}</div>`;
    $('#spendingReport').innerHTML=`<div class="panel-card"><div class="panel-title"><div><h3>Client spending</h3><p>Completed payment volume by payer</p></div></div>${peopleReportTable(spendingData.spending||[],'client_id','total_spending')}</div>`;
    makeChart('projectStatusChart',(r.projects_by_status||[]).map(x=>x.label),(r.projects_by_status||[]).map(x=>Number(x.count)),'bar','#6957e8');
    makeChart('userRoleChart',(r.users_by_role||[]).map(x=>x.label),(r.users_by_role||[]).map(x=>Number(x.count)),'bar','#39a883');
  }
  function reportTable(rows,withAmount=false){return rows.length?`<div class="table-responsive"><table class="table"><thead><tr><th>Status</th><th>Count</th>${withAmount?'<th>Volume</th>':''}</tr></thead><tbody>${rows.map(x=>`<tr><td>${fmt(x.label)}</td><td>${Number(x.count)}</td>${withAmount?`<td>${money(x.amount)}</td>`:''}</tr>`).join('')}</tbody></table></div>`:'<p class="small text-secondary mb-0">No records yet.</p>';}
  function ratingReportTable(rows){return rows.length?`<div class="table-responsive"><table class="table"><thead><tr><th>Account role</th><th>Reviews</th><th>Average rating</th></tr></thead><tbody>${rows.map(x=>`<tr><td>${esc(x.label)}</td><td>${Number(x.count)}</td><td>${x.average_rating===null?'—':`${Number(x.average_rating).toFixed(2)} ★`}</td></tr>`).join('')}</tbody></table></div>`:'<p class="small text-secondary mb-0">No ratings yet.</p>';}
  function peopleReportTable(rows,idKey,amountKey){return rows.length?`<div class="table-responsive"><table class="table"><thead><tr><th>Name</th><th>Completed</th><th>Payments</th></tr></thead><tbody>${rows.map(x=>`<tr><td><b>${esc(x.full_name)}</b><div class="small text-secondary">#${x[idKey]}</div></td><td>${money(x[amountKey])}</td><td>${x.completed_payment_count}</td></tr>`).join('')}</tbody></table></div>`:'<p class="small text-secondary mb-0">No records yet.</p>';}
  async function renderDisputes(){
    if(state.user.role!=='admin')return navigate('home');destroyCharts();pageContent.innerHTML=`${heading('Dispute management','Review reported contract issues and record a resolution.')}<div class="filter-bar"><select id="disputeStatusFilter" class="form-select"><option value="">All statuses</option><option>open</option><option>investigating</option><option>resolved</option><option>closed</option></select><button class="btn btn-primary-soft" data-action="load-disputes">Filter</button></div><div id="disputesArea"></div>`;await loadDisputes();
  }
  async function loadDisputes(){const status=$('#disputeStatusFilter')?.value||'';try{const d=await request(`/admin/disputes?limit=100${status?`&status=${encodeURIComponent(status)}`:''}`);const rows=d.disputes||[];$('#disputesArea').innerHTML=rows.length?`<div class="table-panel table-responsive"><table class="table"><thead><tr><th>Case</th><th>Project / contract</th><th>Opened by</th><th>Parties</th><th>Status</th><th>Resolution</th><th>Action</th></tr></thead><tbody>${rows.map(x=>`<tr><td><b>#${x.dispute_id} · ${esc(x.reason)}</b><div class="small text-secondary">${date(x.created_at)}</div><div class="small text-secondary">${esc(x.description||'')}</div></td><td>${esc(x.project_title)}<div class="small text-secondary">Contract #${x.contract_id}</div></td><td>${esc(x.opener_name)}</td><td>${esc(x.client_name)} ↔ ${esc(x.freelancer_name)}</td><td>${fmt(x.status)}</td><td>${esc(x.resolution||'—')}</td><td>${x.status==='open'?`<button class="btn btn-outline-soft" data-action="dispute-update" data-id="${x.dispute_id}" data-status="investigating">Investigate</button>`:''}${['open','investigating'].includes(x.status)?`<button class="btn btn-primary-soft" data-action="dispute-update" data-id="${x.dispute_id}" data-status="resolved">Resolve</button>`:''}${x.status==='resolved'?`<button class="btn btn-outline-soft" data-action="dispute-update" data-id="${x.dispute_id}" data-status="closed">Close</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:empty('No disputes found','There are no disputes for this status.');}catch(e){$('#disputesArea').innerHTML=empty('Disputes could not load',esc(e.message));}}
  async function showDisputeForm(contractId){
    showForm('Open a contract dispute',`<form id="disputeForm" class="modal-form"><p class="small text-secondary">Describe the issue clearly. An administrator can review and record a resolution.</p><label>Reason<input class="form-control" name="reason" maxlength="180" required></label><label>Details<textarea class="form-control" name="description" maxlength="20000" rows="4"></textarea></label><button class="btn btn-primary-soft">Submit dispute</button></form>`);
    $('#disputeForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post(`/contracts/${contractId}/disputes`,{reason:f.get('reason'),description:f.get('description')||null});bootstrap.Modal.getInstance($('#formModal')).hide();notify('Dispute submitted for review.');openContract(contractId);}catch(err){notify(err.message,'error');}};
  }

  async function renderNotifications(){const listEl=$('#notificationList');listEl.innerHTML=loadingState('Loading notifications…');try{const d=await request('/notifications?limit=30'),list=d.notifications||[];$('#notificationDot').classList.toggle('d-none',!list.some(n=>!n.is_read));listEl.innerHTML=list.length?list.map(n=>`<div class="notification-item ${n.is_read?'':'unread'}" data-action="notification-read" data-id="${n.notification_id}" role="button" tabindex="0"><div class="activity-icon">✦</div><p>${esc(n.message)}<small>${timestamp(n.created_at)} · ${esc((n.notification_type||'update').replaceAll('_',' '))} · <b>${n.is_read?'Read':'Unread'}</b></small></p></div>`).join(''):`<div class="p-4 text-center small text-secondary">Nothing to see just yet.</div>`;}catch(e){listEl.innerHTML=`${empty('Notifications could not load',esc(e.message))}<div class="text-center pb-3"><button class="btn btn-outline-soft" data-action="reload-notifications">Try again</button></div>`;}}
  async function refreshNotificationDot(){try{const d=await request('/notifications?unread_only=true&limit=1');$('#notificationDot').classList.toggle('d-none',!(d.notifications||[]).length);}catch{}}
  function showForm(title,html){$('#formModalTitle').textContent=title;$('#formModalBody').innerHTML=html;bootstrap.Modal.getOrCreateInstance($('#formModal')).show();}
  function showDetails(title,html){$('#modalTitle').textContent=title;$('#modalBody').innerHTML=html;bootstrap.Modal.getOrCreateInstance($('#genericModal')).show();}
  function addTask(contract){showForm('Add a task',`<form id="taskForm" class="modal-form"><label>Task title<input name="title" class="form-control" maxlength="180" required></label><label>Description<textarea name="description" class="form-control" rows="3"></textarea></label><label>Due date<input name="due_date" class="form-control" type="date"></label><button class="btn btn-primary-soft">Assign task</button></form>`);$('#taskForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post(`/contracts/${contract}/tasks`,{title:f.get('title'),description:f.get('description')||null,due_date:f.get('due_date')||null});bootstrap.Modal.getInstance($('#formModal')).hide();openContract(contract);}catch(err){notify(err.message,'error');}};}
  function addMilestone(contract){showForm('Add a milestone',`<form id="milestoneForm" class="modal-form"><label>Milestone title<input name="title" class="form-control" maxlength="180" required></label><label>Description<textarea name="description" class="form-control" rows="3"></textarea></label><div class="row g-2"><div class="col"><label>Amount<input name="amount" class="form-control" type="number" min="0.01" step="0.01" required></label></div><div class="col"><label>Due date<input name="due_date" class="form-control" type="date"></label></div></div><button class="btn btn-primary-soft">Add milestone</button></form>`);$('#milestoneForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post(`/contracts/${contract}/milestones`,{title:f.get('title'),description:f.get('description')||null,amount:f.get('amount'),due_date:f.get('due_date')||null});bootstrap.Modal.getInstance($('#formModal')).hide();openContract(contract);}catch(err){notify(err.message,'error');}};}
  function addPortfolio(){showForm('Add portfolio item',`<form id="portfolioForm" class="modal-form"><label>Title<input class="form-control" name="title" maxlength="180" required></label><label>Description<textarea class="form-control" name="description" rows="3"></textarea></label><label>Project URL<input class="form-control" name="project_url" type="url"></label><button class="btn btn-primary-soft">Add item</button></form>`);$('#portfolioForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);try{await post('/freelancers/me/portfolio',{title:f.get('title'),description:f.get('description')||null,project_url:f.get('project_url')||null});bootstrap.Modal.getInstance($('#formModal')).hide();notify('Portfolio item added.');renderProfile();}catch(err){notify(err.message,'error');}};}
  function pay(contract,milestone,amount){showForm('Record a payment',`<form id="paymentForm" class="modal-form"><p class="text-secondary small">This creates a pending payment record for admin settlement. No real charge is processed.</p><label>Amount<input class="form-control" name="amount" type="number" min="0.01" step="0.01" value="${esc(amount||'')}" required></label><label>Payment method<input class="form-control" name="payment_method" value="demo" maxlength="40"></label><button class="btn btn-primary-soft">Create payment</button></form>`);$('#paymentForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.currentTarget);const body={amount:f.get('amount'),payment_method:f.get('payment_method')||null};if(milestone)body.milestone_id=Number(milestone);try{await post(`/contracts/${contract}/payments`,body);bootstrap.Modal.getInstance($('#formModal')).hide();notify('Payment record created.');openContract(contract);}catch(err){notify(err.message,'error');}};}

  $('#loginForm').addEventListener('submit',e=>{e.preventDefault();authenticate(e.currentTarget,'login');});$('#registerForm').addEventListener('submit',e=>{e.preventDefault();authenticate(e.currentTarget,'register');});
  $$('.auth-tab').forEach(t=>t.addEventListener('click',()=>authTab(t.dataset.authTab)));
  $('#forgotPasswordLink').addEventListener('click',e=>{e.preventDefault();showForgotPassword();});
  $('#forgotPasswordForm').addEventListener('submit',e=>{e.preventDefault();requestPasswordReset(e.currentTarget);});
  $$('[data-auth-mode="login"]').forEach(button=>button.addEventListener('click',()=>authTab('login')));
  showApp();
  $('#sideNav').addEventListener('click',e=>{const b=e.target.closest('[data-page]');if(b)navigate(b.dataset.page);});
  document.addEventListener('click',async e=>{
    const nav=e.target.closest('[data-page]');if(nav){navigate(nav.dataset.page==='projects'?'projects':nav.dataset.page);return;}
    const b=e.target.closest('[data-action]');if(!b)return;const id=b.dataset.id,action=b.dataset.action;
    try {
      if(action==='create-project')return showProjectForm();if(action==='edit-project'){const p=await request(`/projects/${id}`);return showProjectForm(p.project);}
      if(action==='page-projects')return navigate('projects');if(action==='reload-notifications')return renderNotifications();if(action==='message-retry')return loadMessageConversation(id,b.dataset.title);
      if(action==='search-projects')return loadProjects();if(action==='apply')return showApply(id,b.dataset.title);if(action==='view-project')return showProject(id);
      if(action==='project-apps')return showProjectApplications(id);
      if(action==='cancel-project'){if(!confirm('Cancel this project? This action cannot be undone from the dashboard.'))return;await del(`/projects/${id}`);notify('Project cancelled.');return state.page==='projects'?loadProjects():renderHome();}
      if(action==='app-status')return changeApplication(id,b.dataset.status,b.dataset.amount);
      if(action==='contract-detail')return openContract(id);if(action==='add-task')return addTask(b.dataset.contract);if(action==='add-milestone')return addMilestone(b.dataset.contract);
      if(action==='task-status'){await patch(`/tasks/${id}`,{status:b.dataset.status});toast(`Task ${b.dataset.status.replace('_',' ')}.`);return openContract(b.dataset.contract);}
      if(action==='milestone-submit'){await patch(`/milestones/${id}/submit`,{});toast('Milestone submitted.');return openContract(b.dataset.contract);}
      if(action==='milestone-review'){await patch(`/milestones/${id}/review`,{status:b.dataset.status});toast(`Milestone ${b.dataset.status}.`);return openContract(b.dataset.contract);}
      if(action==='pay-milestone')return pay(b.dataset.contract,id,b.dataset.amount);if(action==='pay-contract')return pay(b.dataset.contract,null,b.dataset.amount);
      if(action==='complete-contract'){if(!confirm('Complete this contract? All work and payment must be settled.'))return;await post(`/contracts/${b.dataset.contract}/complete`,{});notify('Contract completed.');return openContract(b.dataset.contract);}
      if(action==='add-portfolio')return addPortfolio();if(action==='delete-portfolio'){if(!confirm('Remove this portfolio item?'))return;await del(`/freelancers/me/portfolio/${id}`);notify('Portfolio item removed.');return renderProfile();}
      if(action==='admin-search'){const q=$('#adminUserQuery').value;const d=await request(`/users?limit=100&q=${encodeURIComponent(q)}`);return renderAdminUsers(d.users||[]);}
      if(action==='load-disputes')return loadDisputes();
      if(action==='open-dispute')return showDisputeForm(b.dataset.contract);
      if(action==='dispute-update'){const status=b.dataset.status;const resolution=['resolved','closed'].includes(status)?prompt('Enter the resolution to record:'):null;if(['resolved','closed'].includes(status)&&!resolution?.trim())return;await patch(`/admin/disputes/${id}`,{status,...(resolution?{resolution}:{})});notify(`Dispute ${status}.`);return loadDisputes();}
      if(action==='advance-payment'){const status=b.dataset.status;let next=status==='pending'?'processing':status==='processing'?'completed':'refunded';const reference=next==='completed'?prompt('Transaction reference'):undefined;if(next==='completed'&&!reference)return;await patch(`/payments/${id}/status`,{status:next,...(reference?{transaction_reference:reference}:{})});notify(`Payment ${next}.`);return renderAdmin();}
    }catch(err){notify(err.message,'error');}
  });
  pageContent.addEventListener('change',async e=>{const el=e.target.closest('[data-user-status]');if(!el)return;try{await patch(`/users/${el.dataset.userStatus}/status`,{account_status:el.value});notify('Account status updated.');}catch(err){notify(err.message,'error');}});
  $('#notificationBtn').addEventListener('click',async()=>{$('#notificationPanel').classList.toggle('d-none');const open=!$('#notificationPanel').classList.contains('d-none');$('#notificationBtn').setAttribute('aria-expanded',String(open));if(open)renderNotifications();});
  $('#notificationList').addEventListener('click',async e=>{const item=e.target.closest('[data-id]');if(!item)return;try{await patch(`/notifications/${item.dataset.id}/read`,{});renderNotifications();}catch(err){notify(err.message,'error');}});
  $('#notificationList').addEventListener('keydown',e=>{const item=e.target.closest('[role="button"][data-id]');if(item&&(e.key==='Enter'||e.key===' ')){e.preventDefault();item.click();}});
  $('#readAllBtn').addEventListener('click',async()=>{try{await patch('/notifications/read-all',{});renderNotifications();}catch(err){notify(err.message,'error');}});
  $('#mobileMenu').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
  document.addEventListener('click',e=>{if(!e.target.closest('#notificationPanel')&&!e.target.closest('#notificationBtn'))$('#notificationPanel').classList.add('d-none');});
})();
