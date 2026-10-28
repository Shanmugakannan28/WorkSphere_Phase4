/* WorkSphere Phase 4 pages */
const saveBlob = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); };
const bar = (done, total) => `<div class="bar"><i style="width:${total ? 100 * done / total : 0}%"></i></div>`;
const STAGES = [['submitted', 'Submitted'], ['notice_period', 'Notice period'], ['handover', 'Handover'], ['clearance', 'Clearance'], ['settlement', 'Settlement'], ['completed', 'Completed']];

/* ---------- Dashboard extras ---------- */
const baseDashboard = pages.dashboard;
pages.dashboard = async v => {
  await baseDashboard(v);
  try {
    const [ann, tasks, ob] = await Promise.all([api('/announcements?limit=3'), api('/tasks?mine=true&status=pending'), api('/onboarding?employee_id=' + S.user.employee_id)]);
    const done = ob.filter(i => i.status === 'completed').length;
    const x = document.createElement('div'); x.className = 'split';
    x.innerHTML = `<div class="card"><div class="head"><h3>Announcements</h3><a href="#/announcements">View all</a></div>${ann.length ? ann.map(a => `<p><a href="#/announcements/${a.id}"><b>${a.pinned ? '📌 ' : ''}${esc(a.title)}</b></a><br><span class="muted sm">${fmtDate(a.created_at)}</span></p>`).join('') : '<div class="empty">No announcements.</div>'}</div>
    <div class="card"><div class="head"><h3>My to-do</h3><a href="#/tasks">All tasks</a></div>${tasks.slice(0, 4).map(t => `<p>${esc(t.title)} ${t.overdue ? pill('expired') : ''}<br><span class="muted sm">Due ${fmtDate(t.due_date)}</span></p>`).join('') || '<div class="empty">No pending tasks.</div>'}
    ${ob.length && done < ob.length ? `<h3 style="margin-top:12px">Onboarding ${done}/${ob.length}</h3>${bar(done, ob.length)}<a href="#/onboarding">Open checklist</a>` : ''}</div>`;
    v.append(x);
  } catch { }
};

/* ---------- Announcements ---------- */
pages.announcements = async (v, id) => {
  if (id) {
    const a = await api('/announcements/' + encodeURIComponent(id));
    v.innerHTML = `<div class="card"><p><a href="#/announcements">&larr; All announcements</a></p><h2>${a.pinned ? '📌 ' : ''}${esc(a.title)}</h2>
    <p class="muted sm">${esc(a.author)} · ${new Date(a.created_at).toLocaleString()}</p><div style="white-space:pre-wrap">${esc(a.message)}</div>
    ${isHR() ? '<div class="actions"><button class="btn danger sm" id="del">Delete</button></div>' : ''}</div>`;
    if (isHR()) $('#del').onclick = guard(async () => { if (!confirm('Delete this announcement?')) return; await api('/announcements/' + a.id, { method: 'DELETE' }); location.hash = '#/announcements'; });
    return;
  }
  const list = await api('/announcements');
  v.innerHTML = `<div class="head"><h3>Announcement board</h3>${isHR() ? '<button class="btn primary" id="np">Post announcement</button>' : ''}</div>` +
    (list.length ? list.map(a => `<a class="card ann" href="#/announcements/${a.id}"><h3>${a.pinned ? '📌 ' : ''}${esc(a.title)}</h3><div class="muted sm">${esc(a.author)} · ${fmtDate(a.created_at)}</div><p>${esc(a.message)}${a.message.length >= 160 ? '…' : ''}</p></a>`).join('') : '<div class="card empty">No announcements yet.</div>');
  if (isHR()) $('#np').onclick = () => openModal('Post announcement', `<label>Title<input name="title" required minlength="3" maxlength="120"></label><label>Message<textarea name="message" rows="6" required maxlength="5000"></textarea></label>
    <label style="display:flex;gap:8px;align-items:center;color:var(--ink)"><input type="checkbox" name="pinned" style="width:auto"> Pin to the top</label>`,
    async d => { await api('/announcements', { method: 'POST', body: { title: d.title, message: d.message, pinned: d.pinned === 'on' } }); toast('Announcement posted. Everyone has been notified.', 'ok'); pages.announcements(v); }, 'Post');
};

/* ---------- Tasks ---------- */
pages.tasks = async v => {
  const [tasks, emps] = await Promise.all([api('/tasks'), isStaff() ? api('/employees') : []]);
  let filter = 'all';
  const draw = () => {
    const pend = tasks.filter(t => t.status === 'pending'), over = pend.filter(t => t.overdue);
    const rows = tasks.filter(t => filter === 'all' || (filter === 'overdue' ? t.overdue : t.status === filter));
    v.innerHTML = `<div class="grid"><div class="kpi warn"><b>${pend.length}</b><span>Pending</span></div><div class="kpi bad"><b>${over.length}</b><span>Overdue</span></div><div class="kpi ok"><b>${tasks.length - pend.length}</b><span>Completed</span></div></div>
    <div class="card"><div class="head"><h3>${isStaff() ? 'Tasks I manage and my own' : 'My tasks'}</h3><div class="row fit"><select id="tf" style="width:auto">${opts([['all', 'All'], ['pending', 'Pending'], ['overdue', 'Overdue'], ['completed', 'Completed']], filter)}</select>
    ${isStaff() ? '<button class="btn primary" id="nt">Assign task</button>' : ''}</div></div>
    ${table([{ h: 'Task', f: t => `<b>${esc(t.title)}</b><div class="muted sm">${esc(t.description)}</div>` }, ...(isStaff() ? [{ h: 'Assigned to', f: t => esc(t.assignee_name) }] : []),
    { h: 'Due', f: t => fmtDate(t.due_date) + (t.overdue ? ' ' + pill('expired') : '') }, { h: 'Assigned by', f: t => esc(t.assigned_by) }, { h: 'Status', f: t => pill(t.status) },
    { h: '', f: t => `<button class="btn sm" data-s="${t.id}" data-to="${t.status === 'pending' ? 'completed' : 'pending'}">${t.status === 'pending' ? 'Mark done' : 'Reopen'}</button>${t.can_manage ? ` <button class="btn sm danger" data-x="${t.id}">Delete</button>` : ''}` }], rows, 'No tasks here.')}</div>`;
    $('#tf').onchange = e => { filter = e.target.value; draw(); };
    if (isStaff()) $('#nt').onclick = () => openModal('Assign task', `<label>Employee<select name="assigned_to" required>${opts(emps.filter(e => e.status === 'active').map(e => [e.id, `${e.name} (${e.department})`]), '', 'Choose…')}</select></label>
      <label>Title<input name="title" required minlength="2" maxlength="120"></label><label>Description<textarea name="description" rows="3" maxlength="2000"></textarea></label><label>Due date<input type="date" name="due_date" min="${iso(new Date())}"></label>`,
      async d => { const b = clean(d); b.assigned_to = +b.assigned_to; await api('/tasks', { method: 'POST', body: b }); toast('Task assigned', 'ok'); pages.tasks(v); }, 'Assign');
    v.onclick = guard(async e => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.s) await api(`/tasks/${b.dataset.s}/status`, { method: 'PUT', body: { status: b.dataset.to } });
      else if (b.dataset.x) { if (!confirm('Delete this task?')) return; await api('/tasks/' + b.dataset.x, { method: 'DELETE' }); } else return;
      pages.tasks(v);
    });
  };
  draw();
};

/* ---------- Onboarding ---------- */
let OB_SEL = 0;
pages.onboarding = async v => {
  const staff = isStaff();
  let sel = staff ? OB_SEL : S.user.employee_id;
  const [summary, emps] = staff ? await Promise.all([api('/onboarding/summary'), api('/employees')]) : [[], []];
  if (staff && !sel && summary.length) sel = summary[0].employee_id;
  OB_SEL = sel;
  v.innerHTML = `${staff ? `<div class="card"><h3>Onboarding progress</h3>${table([{ h: 'Employee', f: s => `<a href="#" data-e="${s.employee_id}"><b>${esc(s.name)}</b></a><div class="muted sm">${esc(s.department)}</div>` },
  { h: 'Progress', f: s => `${s.done}/${s.total}${bar(s.done, s.total)}` }, { h: '', f: s => s.overdue ? pill('expired') + ` ${s.overdue} overdue` : (s.percent === 100 ? pill('completed') : '') }], summary, 'No onboarding checklists yet.')}</div>
  <div class="card"><div class="row"><label>Employee<select id="oe">${opts(emps.map(e => [e.id, e.name]), sel, 'Choose…')}</select></label>
  <div class="fit"><button class="btn" id="oa">Add task</button> ${isHR() ? '<button class="btn" id="od">Apply default checklist</button>' : ''}</div></div></div>` : ''}<div class="card" id="ck"></div>`;
  const load = guard(async () => {
    if (!sel) { $('#ck').innerHTML = '<div class="empty">Choose an employee to see their checklist.</div>'; return; }
    const items = await api('/onboarding?employee_id=' + sel);
    const done = items.filter(i => i.status === 'completed').length;
    $('#ck').innerHTML = `<div class="head"><h3>Checklist${items[0] ? ' for ' + esc(items[0].employee_name) : ''}</h3><b>${done} of ${items.length} done</b></div>${bar(done, items.length)}` +
      (items.length ? items.map(i => `<label class="chk ${i.status === 'completed' ? 'done' : ''}"><input type="checkbox" data-i="${i.id}" ${i.status === 'completed' ? 'checked' : ''}><span>${esc(i.task_name)}</span>
      ${i.overdue ? pill('expired') : ''}<small>${i.status === 'completed' ? 'Done ' + fmtDate(i.completed_at) : 'Due ' + fmtDate(i.due_date)}</small>${staff ? `<button type="button" class="btn sm danger" data-x="${i.id}">Remove</button>` : ''}</label>`).join('') : '<div class="empty">No onboarding tasks assigned.</div>');
  });
  v.onchange = guard(async e => { const c = e.target.closest('[data-i]'); if (!c) return; await api(`/onboarding/${c.dataset.i}/status`, { method: 'PUT', body: { status: c.checked ? 'completed' : 'pending' } }); load(); if (staff) refreshSummary(); });
  v.onclick = guard(async e => {
    const x = e.target.closest('[data-x]'); if (x) { e.preventDefault(); await api('/onboarding/' + x.dataset.x, { method: 'DELETE' }); load(); return; }
    const l = e.target.closest('[data-e]'); if (l) { e.preventDefault(); sel = OB_SEL = +l.dataset.e; $('#oe').value = sel; load(); }
  });
  const refreshSummary = () => { const y = scrollY; pages.onboarding(v).then(() => scrollTo(0, y)); };
  if (staff) {
    $('#oe').onchange = e => { sel = OB_SEL = +e.target.value; load(); };
    $('#oa').onclick = () => { if (!sel) return toast('Choose an employee first', 'err'); openModal('Add onboarding task', '<label>Task<input name="task_name" required minlength="2" maxlength="120"></label><label>Due date<input type="date" name="due_date"></label>',
      async d => { const b = clean(d); b.employee_id = sel; await api('/onboarding', { method: 'POST', body: b }); toast('Task added', 'ok'); refreshSummary(); }, 'Add'); };
    if (isHR()) $('#od').onclick = guard(async () => { if (!sel) return toast('Choose an employee first', 'err'); const r = await api('/onboarding/apply-default/' + sel, { method: 'POST' }); toast(r.added ? `${r.added} tasks added` : 'Checklist already complete', 'ok'); refreshSummary(); });
  }
  load();
};

/* ---------- Resignation & exit ---------- */
pages.exit = async v => {
  const list = await api('/resignations');
  const mine = list.filter(r => r.employee_id === S.user.employee_id);
  const active = mine.find(r => ['pending', 'approved'].includes(r.status) && r.exit_stage !== 'completed');
  const others = list.filter(r => r.employee_id !== S.user.employee_id);
  const tracker = r => {
    const idx = STAGES.findIndex(s => s[0] === r.exit_stage);
    return `<div class="row"><div><b>Status</b><br>${pill(r.status)}</div><div><b>Notice period</b><br>${r.notice_period} days</div><div><b>Last working day</b><br>${fmtDate(r.last_working_day)}</div></div>
    ${r.status === 'approved' ? `<ol class="steps">${STAGES.map((s, i) => `<li class="${i < idx ? 'done' : i === idx ? 'cur' : ''}">${s[1]}</li>`).join('')}</ol>` : '<p class="muted">Waiting for HR to review your resignation.</p>'}
    <p class="muted sm">Reason: ${esc(r.reason)}</p>${r.status === 'pending' ? '<button class="btn danger sm" id="wd">Withdraw resignation</button>' : ''}`;
  };
  v.innerHTML = `<div class="card"><h3>My resignation</h3>${active ? tracker(active) : `<form id="rf"><p class="muted">Submitting a resignation notifies HR and your manager. You can withdraw it while it is still pending.</p>
  <label>Reason<textarea name="reason" rows="3" required minlength="10" maxlength="1000"></textarea></label><label>Notice period (days)<input name="notice_period" type="number" min="0" max="180" value="30" required></label><button class="btn primary">Submit resignation</button></form>`}
  ${!active && mine.length ? `<h4 style="margin-top:14px">Earlier</h4>${table([{ h: 'Submitted', f: r => fmtDate(r.created_at) }, { h: 'Status', f: r => pill(r.status) }, { h: 'Stage', f: r => label(r.exit_stage) }], mine)}` : ''}</div>
  ${isStaff() ? `<div class="card"><h3>${isHR() ? 'Exit requests' : 'My team'}</h3>${table([{ h: 'Employee', f: r => `<b>${esc(r.employee_name)}</b><div class="muted sm">${esc(r.department)}</div>` }, { h: 'Reason', f: r => `<span title="${esc(r.reason)}">${esc(r.reason.slice(0, 50))}${r.reason.length > 50 ? '…' : ''}</span>` },
  { h: 'Last day', f: r => fmtDate(r.last_working_day) }, { h: 'Status', f: r => pill(r.status) },
  { h: isHR() ? 'Action' : 'Stage', f: r => !isHR() ? label(r.exit_stage) : r.status === 'pending' ? `<button class="btn sm" data-a="approved" data-id="${r.id}">Approve</button> <button class="btn sm danger" data-a="rejected" data-id="${r.id}">Reject</button>` :
    r.status === 'approved' && r.exit_stage !== 'completed' ? `<select data-st="${r.id}" style="width:auto">${opts(STAGES.slice(1).map(s => [s[0], s[1]]), r.exit_stage)}</select>` : label(r.exit_stage) }], others, 'No exit requests.')}</div>` : ''}`;
  if ($('#rf')) $('#rf').onsubmit = guard(async e => { e.preventDefault(); if (!confirm('Submit your resignation?')) return; const b = Object.fromEntries(new FormData(e.target)); b.notice_period = +b.notice_period; await api('/resignations', { method: 'POST', body: b }); toast('Resignation submitted', 'ok'); pages.exit(v); });
  if ($('#wd')) $('#wd').onclick = guard(async () => { await api('/resignations/' + active.id, { method: 'DELETE' }); toast('Resignation withdrawn', 'ok'); pages.exit(v); });
  v.onclick = guard(async e => { const b = e.target.closest('[data-a]'); if (!b) return; await api(`/resignations/${b.dataset.id}/review`, { method: 'PUT', body: { status: b.dataset.a } }); pages.exit(v); });
  v.onchange = guard(async e => {
    const s = e.target.closest('[data-st]'); if (!s) return;
    if (s.value === 'completed' && !confirm('Completing the exit deactivates this employee’s login. Continue?')) { pages.exit(v); return; }
    await api(`/resignations/${s.dataset.st}/stage`, { method: 'PUT', body: { stage: s.value } }); toast('Exit stage updated', 'ok'); pages.exit(v);
  });
};

/* ---------- Feedback ---------- */
pages.feedback = async v => {
  const d = await api('/feedback'), s = d.summary;
  v.innerHTML = `${s ? `<div class="grid"><div class="kpi"><b>${s.count}</b><span>Responses</span></div><div class="kpi ok"><b>${s.average ?? '—'}</b><span>Average rating</span></div></div>
  <div class="card"><h3>Rating distribution</h3>${hbars(Object.entries(s.distribution).map(([r, n]) => [r + ' star' + (r > 1 ? 's' : ''), n]), Math.max(1, ...Object.values(s.distribution)), 'var(--warn)')}</div>` : ''}
  <div class="card"><h3>Share your feedback</h3><form id="ff"><label>How is your experience at work?</label><div class="rate">${[1, 2, 3, 4, 5].map(n => `<label><input type="radio" name="rating" value="${n}" ${n === 4 ? 'checked' : ''}><span>${n}</span></label>`).join('')}</div><br>
  <label>Your message<textarea name="message" rows="3" required minlength="5" maxlength="2000"></textarea></label>
  <label style="display:flex;gap:8px;align-items:center;color:var(--ink)"><input type="checkbox" name="anonymous" style="width:auto"> Hide my name from HR</label><button class="btn primary">Submit feedback</button></form></div>
  <div class="card"><h3>${s ? 'All feedback' : 'My submissions'}</h3>${table([{ h: 'Date', f: f => fmtDate(f.created_at) }, ...(s ? [{ h: 'From', f: f => esc(f.employee_name) + (f.department ? `<div class="muted sm">${esc(f.department)}</div>` : '') }] : []),
  { h: 'Rating', f: f => stars(f.rating) }, { h: 'Message', f: f => esc(f.message) }], d.items, 'No feedback yet.')}</div>`;
  $('#ff').onsubmit = guard(async e => { e.preventDefault(); const b = Object.fromEntries(new FormData(e.target)); await api('/feedback', { method: 'POST', body: { message: b.message, rating: +b.rating, anonymous: b.anonymous === 'on' } }); toast('Thank you for your feedback', 'ok'); pages.feedback(v); });
};

/* ---------- Reports & integrations ---------- */
pages.integrations = async v => {
  const [st, leaves] = await Promise.all([api('/integrations/status'), api('/leaves')]);
  const mine = leaves.filter(l => l.employee_id === S.user.employee_id && ['approved', 'pending'].includes(l.status));
  const reps = [['employees', 'Employee list', isStaff()], ['attendance', 'Attendance', 1], ['leaves', 'Leaves', 1], ['payroll', 'Payroll', 1], ['feedback', 'Employee feedback', isHR()]].filter(r => r[2]);
  const gcal = l => 'https://calendar.google.com/calendar/render?action=TEMPLATE&text=' + encodeURIComponent(l.leave_type + ' leave') + '&dates=' + l.start_date.replace(/-/g, '') + '/' + iso(addDays(pd(l.end_date), 1)).replace(/-/g, '') + '&details=' + encodeURIComponent(l.reason || '');
  v.innerHTML = `<div class="card"><h3>Export reports</h3><div class="filters"><label>Report<select id="rk">${opts(reps.map(r => [r[0], r[1]]), '')}</select></label>
  <label>From<input type="date" id="rs" value="${iso(addDays(new Date(), -29))}"></label><label>To<input type="date" id="re" value="${iso(new Date())}"></label></div>
  <button class="btn primary" data-f="csv">Download CSV</button> <button class="btn" data-f="pdf">Download PDF</button>
  <p class="muted sm">You only get data you are allowed to see. The date range applies to attendance, leaves and feedback.</p></div>
  <div class="split"><div class="card"><h3>Calendar sync</h3><p class="muted">Download your leaves, task deadlines and onboarding dates as an .ics file, then import it into Google Calendar, Outlook or Apple Calendar.</p>
  <button class="btn" id="ics">Download calendar (.ics)</button><h4 style="margin:14px 0 6px">Add a leave to Google Calendar</h4>
  ${mine.length ? mine.map(l => `<p class="sm">${esc(l.leave_type)} · ${fmtDate(l.start_date)} – ${fmtDate(l.end_date)} ${pill(l.status)} <a href="${gcal(l)}" target="_blank" rel="noopener noreferrer">Add</a></p>`).join('') : '<div class="muted sm">No upcoming leaves.</div>'}</div>
  <div class="card"><h3>Email integration</h3><p>Mode: <b>${esc(st.email_mode)}</b> ${pill(st.email_configured ? 'active' : 'pending')}</p>
  <p class="muted sm">Alerts are emailed to users who turn on “Email alerts” in Profile &amp; settings. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD in the .env file to send real emails.</p>
  ${S.user.role === 'admin' ? '<form id="te" class="row"><label>Send test email to (optional)<input type="email" name="to" placeholder="your own email"></label><button class="btn fit">Send test</button></form>' : ''}</div></div>`;
  v.onclick = guard(async e => {
    const b = e.target.closest('[data-f]'); if (!b) return;
    const k = $('#rk').value, f = b.dataset.f;
    saveBlob(await fetchBlob(`/reports/${k}${qs({ format: f, start: $('#rs').value, end: $('#re').value })}`), `${k}-${iso(new Date())}.${f}`);
  });
  $('#ics').onclick = guard(async () => saveBlob(await fetchBlob('/integrations/calendar.ics'), 'worksphere-calendar.ics'));
  if ($('#te')) $('#te').onsubmit = guard(async e => { e.preventDefault(); const r = await api('/integrations/test-email', { method: 'POST', body: clean(Object.fromEntries(new FormData(e.target))) }); toast(r.message, 'ok'); });
};

/* ---------- Profile & settings ---------- */
const TYPE_LABELS = { late: 'Late attendance', leave: 'Leave updates', payroll: 'Payroll', document: 'Document expiry', performance: 'Performance reviews', announcement: 'Announcements', task: 'Tasks', onboarding: 'Onboarding', exit: 'Exit process' };
pages.profile = async v => {
  const [a, p] = await Promise.all([api('/account'), api('/employees/me')]);
  const pr = a.preferences;
  v.innerHTML = `<div class="card"><h3>Personal details</h3><div class="profile">${[['Name', p.name], ['Username', p.username], ['Email', p.email], ['System role', label(p.role)], ['Department', p.department], ['Job title', p.designation], ['Manager', p.manager || '—'], ['Shift', p.shift || 'Not assigned'], ['Joined', fmtDate(p.join_date)], ['Monthly salary', money(p.salary)]].map(([k, x]) => `<div><small>${k}</small>${esc(x)}</div>`).join('')}</div></div>
  <div class="split"><div class="card"><h3>Edit profile</h3><form id="pf"><label>Full name<input name="name" value="${esc(a.name)}" required minlength="2" maxlength="80"></label><label>Phone<input name="phone" value="${esc(a.phone || '')}" maxlength="30" placeholder="+91 98765 43210"></label>
  <label>Address<textarea name="address" rows="2" maxlength="200">${esc(a.address || '')}</textarea></label><button class="btn primary">Save profile</button></form></div>
  <div class="card"><h3>Change password</h3><form id="pw"><label>Current password<input type="password" name="old_password" required></label><label>New password (min 8)<input type="password" name="new_password" minlength="8" required></label><button class="btn primary">Update password</button></form></div></div>
  <div class="card"><h3>Notification preferences</h3><form id="np"><div class="checks"><label><input type="checkbox" name="pref_inapp" ${pr.pref_inapp ? 'checked' : ''}> In-app alerts (bell)</label><label><input type="checkbox" name="pref_email" ${pr.pref_email ? 'checked' : ''}> Email alerts</label></div>
  <h4 style="margin:14px 0 6px">Tell me about</h4><div class="checks">${a.mutable_types.map(t => `<label><input type="checkbox" name="t" value="${t}" ${pr.muted_types.includes(t) ? '' : 'checked'}> ${esc(TYPE_LABELS[t] || t)}</label>`).join('')}</div>
  <br><button class="btn primary">Save preferences</button></form></div>`;
  $('#pf').onsubmit = guard(async e => { e.preventDefault(); const r = await api('/account/profile', { method: 'PUT', body: Object.fromEntries(new FormData(e.target)) }); S.user.name = r.name; $('#who-name').textContent = r.name; toast('Profile saved', 'ok'); pages.profile(v); });
  $('#pw').onsubmit = guard(async e => { e.preventDefault(); await api('/auth/change-password', { method: 'POST', body: Object.fromEntries(new FormData(e.target)) }); toast('Password updated', 'ok'); e.target.reset(); });
  $('#np').onsubmit = guard(async e => {
    e.preventDefault(); const f = e.target, on = new FormData(f).getAll('t');
    await api('/account/preferences', { method: 'PUT', body: { pref_inapp: f.pref_inapp.checked, pref_email: f.pref_email.checked, muted_types: a.mutable_types.filter(t => !on.includes(t)) } }); toast('Preferences saved', 'ok');
  });
};
