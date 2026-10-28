/* WorkSphere pages */
const COLORS = { present: '#1b9e77', late: '#d98a00', absent: '#d6453d', on_leave: '#7b5be6' };

/* ---------- Dashboard ---------- */
pages.dashboard = async v => {
  const today = new Date();
  const [t, bal, up] = await Promise.all([api('/attendance/today'), api('/leaves/balance'),
  api('/leaves/calendar' + qs({ start: iso(today), end: iso(addDays(today, 14)) }))]);
  let kpis = '';
  if (isStaff()) {
    const k = (await api('/analytics/overview')).kpis;
    kpis = `<div class="grid">
      <div class="kpi"><b>${k.headcount}</b><span>Active employees</span></div>
      <div class="kpi ok"><b>${k.attendance_rate}%</b><span>Attendance, last 30 days</span></div>
      <div class="kpi warn"><b>${k.late_count}</b><span>Late check-ins</span></div>
      <div class="kpi leave"><b>${k.pending_leaves}</b><span>Leave requests waiting</span></div></div>`;
  }
  const r = t.record;
  const flag = r && r.checkin_flag ? ` ${pill(r.checkin_flag)}` : '';
  v.innerHTML = `${kpis}
  <div class="card checkin">
    <div><h3>Today</h3><div class="time">${r && r.check_in ? fmtTime(r.check_in) : '--:--'}</div>
      <div class="muted sm">${t.shift ? `${esc(t.shift.name)} shift, ${hhmm(t.shift.start_time)}–${hhmm(t.shift.end_time)} (late after ${t.grace_minutes} min)` : 'No shift assigned. Ask HR to assign one.'}</div></div>
    <div>${r ? pill(r.status) + flag : '<span class="muted">Not checked in</span>'}
      ${r && r.late_minutes ? `<div class="sm muted">${r.late_minutes} min late</div>` : ''}
      ${r && r.check_out ? `<div class="sm muted">Checked out ${fmtTime(r.check_out)}${r.early_leave_minutes ? `, ${r.early_leave_minutes} min early` : ''}</div>` : ''}</div>
    <div class="row fit"><button class="btn primary" id="ci" ${r && r.check_in ? 'disabled' : ''}>Check in</button>
      <button class="btn" id="co" ${!(r && r.check_in) || r.check_out ? 'disabled' : ''}>Check out</button></div>
  </div>
  <div class="split"><div class="card"><h3>My leave balance</h3>${table([{ h: 'Type', f: b => esc(b.leave_type) }, { h: 'Used', f: b => b.used }, { h: 'Remaining', f: b => b.remaining ?? 'Unlimited' }], bal)}</div>
  <div class="card"><h3>Team leave, next 14 days</h3>${table([{ h: 'Who', f: l => esc(l.name) }, { h: 'When', f: l => `${fmtDate(l.start_date)} – ${fmtDate(l.end_date)}` }, { h: 'Status', f: l => pill(l.status) }], up, 'No one is on leave.')}</div></div>`;
  $('#ci').onclick = guard(async () => { await api('/attendance/check-in', { method: 'POST' }); toast('Checked in', 'ok'); pollNotifications(); pages.dashboard(v); });
  $('#co').onclick = guard(async () => { await api('/attendance/check-out', { method: 'POST' }); toast('Checked out', 'ok'); pages.dashboard(v); });
};

/* ---------- Employees (advanced search + filters) ---------- */
pages.employees = async v => {
  const meta = await api('/employees/meta');
  v.innerHTML = `<div class="card"><div class="head"><h3>Find employees</h3>${isHR() ? '<button class="btn primary" id="add">Add employee</button>' : ''}</div>
  <div class="filters">
    <label>Search<input id="q" type="search" placeholder="Name, email, department or role"></label>
    <label>Department<select id="fd">${opts(meta.departments.map(d => [d, d]), '', 'All')}</select></label>
    <label>Role<input id="fr" list="roles" placeholder="e.g. manager, developer"><datalist id="roles">${['admin', 'hr', 'manager', 'employee', ...meta.designations].map(r => `<option value="${esc(r)}">`).join('')}</datalist></label>
    <label>Status<select id="fs"><option value="">Any</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="on_leave">On leave today</option></select></label>
    <label>Attendance today<select id="fa"><option value="">Any</option><option value="present">Present</option><option value="late">Late</option><option value="absent">Absent</option><option value="on_leave">On leave</option><option value="not_marked">Not marked</option></select></label>
    <label>Performance<select id="fp"><option value="">Any</option><option value="min:4.5">4.5 and above</option><option value="min:4">4 and above</option><option value="min:3">3 and above</option><option value="max:2.99">Below 3</option></select></label>
  </div><div class="head"><span class="muted sm" id="count"></span><button class="btn ghost sm" id="clr">Clear filters</button></div>
  <div id="list"></div></div>`;
  const load = guard(async () => {
    const p = { q: $('#q').value, department: $('#fd').value, role: $('#fr').value, status: $('#fs').value, attendance: $('#fa').value };
    const [k, val] = ($('#fp').value || ':').split(':'); if (k) p[k + '_rating'] = val;
    const rows = await api('/employees' + qs(p));
    $('#count').textContent = `${rows.length} employee${rows.length === 1 ? '' : 's'}`;
    const cols = [{ h: 'Name', f: e => `<b>${esc(e.name)}</b><div class="muted sm">${esc(e.email)}</div>` }, { h: 'Department', f: e => esc(e.department) },
    { h: 'Role', f: e => `${esc(e.designation)}<div class="muted sm">${label(e.role)}</div>` }, { h: 'Shift', f: e => esc(e.shift || '—') },
    { h: 'Today', f: e => pill(e.today_attendance) }, { h: 'Rating', f: e => stars(e.avg_rating) }, { h: 'Status', f: e => pill(e.on_leave_today ? 'on_leave' : e.status) }];
    if (isHR()) cols.push({ h: '', f: e => `<button class="btn sm" data-e="${e.id}">Edit</button>` });
    $('#list').innerHTML = table(cols, rows, 'No employees match these filters.');
    $('#list').onclick = ev => { const b = ev.target.closest('[data-e]'); if (b) editEmployee(rows.find(x => x.id == b.dataset.e), meta, load); };
  });
  const dl = debounce(load);
  $('#q').oninput = dl; $('#fr').oninput = dl; ['fd', 'fs', 'fa', 'fp'].forEach(i => $('#' + i).onchange = load);
  $('#clr').onclick = () => { ['q', 'fr'].forEach(i => $('#' + i).value = ''); ['fd', 'fs', 'fa', 'fp'].forEach(i => $('#' + i).value = ''); load(); };
  if (isHR()) $('#add').onclick = async () => {
    const shifts = await api('/shifts');
    openModal('Add employee', `<label>Full name<input name="name" required minlength="2"></label><label>Email<input name="email" type="email" required></label>
    <div class="row"><label>Department<input name="department" required list="dl"></label><label>Job title<input name="designation" required></label></div>
    <datalist id="dl">${meta.departments.map(d => `<option value="${esc(d)}">`).join('')}</datalist>
    <div class="row"><label>System role<select name="role"><option>employee</option><option>manager</option><option>hr</option>${S.user.role === 'admin' ? '<option>admin</option>' : ''}</select></label>
    <label>Manager<select name="manager_id">${opts(meta.managers.map(m => [m.id, m.name]), '', 'None')}</select></label></div>
    <div class="row"><label>Monthly salary<input name="salary" type="number" min="0" value="0"></label><label>Shift<select name="shift_id">${opts(shifts.map(s => [s.id, s.name]), '', 'None')}</select></label></div>
    <label>Temporary password (optional, min 8)<input name="password" minlength="8" placeholder="Default: Welcome@123"></label>`,
      async d => { const b = clean(d); ['manager_id', 'shift_id'].forEach(k => b[k] && (b[k] = +b[k])); if (b.salary) b.salary = +b.salary; await api('/employees', { method: 'POST', body: b }); toast('Employee added', 'ok'); load(); }, 'Add employee');
  };
  load();
};
function editEmployee(e, meta, reload) {
  openModal('Edit ' + e.name, `<div class="row"><label>Department<input name="department" value="${esc(e.department)}" required></label><label>Job title<input name="designation" value="${esc(e.designation)}" required></label></div>
  <div class="row"><label>System role<select name="role">${opts(['employee', 'manager', 'hr', 'admin'].map(r => [r, r]), e.role)}</select></label><label>Status<select name="status">${opts([['active', 'Active'], ['inactive', 'Inactive']], e.status)}</select></label></div>
  <div class="row"><label>Manager<select name="manager_id">${opts(meta.managers.filter(m => m.id !== e.id).map(m => [m.id, m.name]), e.manager_id, 'None')}</select></label><label>Monthly salary<input name="salary" type="number" min="0" value="${e.salary ?? 0}"></label></div>`,
    async d => { const b = clean(d); if (b.manager_id) b.manager_id = +b.manager_id; if (b.salary != null) b.salary = +b.salary; await api('/employees/' + e.id, { method: 'PUT', body: b }); toast('Saved', 'ok'); reload(); });
}

/* ---------- Shifts ---------- */
let weekOffset = 0;
pages.shifts = async v => {
  const mon = addDays(new Date(), -((new Date().getDay() + 6) % 7) + weekOffset * 7);
  const days = [...Array(7)].map((_, i) => addDays(mon, i));
  const [shifts, asg, lv] = await Promise.all([api('/shifts'), api('/shifts/assignments'),
  api('/leaves/calendar' + qs({ start: iso(days[0]), end: iso(days[6]) }))]);
  const cell = (a, d) => {
    const ds = iso(d);
    if (d.getDay() === 0 || d.getDay() === 6) return '<span class="chip off">Off</span>';
    if (lv.some(l => l.employee_id === a.employee_id && l.status === 'approved' && l.start_date <= ds && l.end_date >= ds)) return '<span class="chip lv">Leave</span>';
    return a.shift_name ? `<span class="chip s-${esc(a.shift_name)}" title="${hhmm(a.start_time)}–${hhmm(a.end_time)}">${esc(a.shift_name)}</span>` : '<span class="muted">—</span>';
  };
  v.innerHTML = `<div class="card"><div class="head"><h3>Weekly schedule</h3><div><button class="btn sm" id="pw">&lt; Prev</button> <b class="sm">${fmtDate(iso(days[0]))} – ${fmtDate(iso(days[6]))}</b> <button class="btn sm" id="nw">Next &gt;</button></div></div>
  <div class="tablewrap"><table class="sched"><thead><tr><th>Employee</th>${days.map(d => `<th>${d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })}</th>`).join('')}</tr></thead>
  <tbody>${asg.map(a => `<tr><td><b>${esc(a.name)}</b><div class="muted sm">${esc(a.department)}</div></td>${days.map(d => `<td>${cell(a, d)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></div>
  <div class="split"><div class="card"><div class="head"><h3>Shifts</h3>${isHR() ? '<button class="btn sm" id="ns">New shift</button>' : ''}</div>
  ${table([{ h: 'Name', f: s => `<span class="chip s-${esc(s.name)}">${esc(s.name)}</span>` }, { h: 'Start', f: s => hhmm(s.start_time) }, { h: 'End', f: s => hhmm(s.end_time) }, ...(isHR() ? [{ h: '', f: s => `<button class="btn sm" data-s="${s.id}">Edit</button>` }] : [])], shifts)}
  <p class="muted sm">Check-ins more than the grace period after start are marked late. Shifts that end before they start run overnight.</p></div>
  ${isStaff() ? `<div class="card"><h3>Assign shift</h3><label>Employee<select id="ae">${opts(asg.map(a => [a.employee_id, `${a.name} (${a.shift_name || 'no shift'})`]), '')}</select></label>
  <label>Shift<select id="as">${opts(shifts.map(s => [s.id, `${s.name} ${hhmm(s.start_time)}–${hhmm(s.end_time)}`]), '')}</select></label><button class="btn primary" id="go">Assign shift</button></div>` : ''}</div>`;
  $('#pw').onclick = () => { weekOffset--; pages.shifts(v); }; $('#nw').onclick = () => { weekOffset++; pages.shifts(v); };
  if (isStaff()) $('#go').onclick = guard(async () => { await api('/shifts/assign', { method: 'POST', body: { employee_id: +$('#ae').value, shift_id: +$('#as').value } }); toast('Shift assigned', 'ok'); pages.shifts(v); });
  const shiftForm = (s = {}) => `<label>Name<input name="name" required value="${esc(s.name || '')}"></label><div class="row"><label>Start<input type="time" name="start_time" required value="${hhmm(s.start_time)}"></label><label>End<input type="time" name="end_time" required value="${hhmm(s.end_time)}"></label></div>`;
  if (isHR()) {
    $('#ns').onclick = () => openModal('New shift', shiftForm(), async d => { await api('/shifts', { method: 'POST', body: d }); pages.shifts(v); });
    v.onclick = e => { const b = e.target.closest('[data-s]'); if (!b) return; const s = shifts.find(x => x.id == b.dataset.s); openModal('Edit shift', shiftForm(s), async d => { await api('/shifts/' + s.id, { method: 'PUT', body: d }); pages.shifts(v); }); };
  }
};

/* ---------- Attendance ---------- */
pages.attendance = async v => {
  const emps = isStaff() ? await api('/employees') : [];
  const end = iso(new Date()), start = iso(addDays(new Date(), -29));
  v.innerHTML = `<div class="card"><div class="head"><h3>Attendance records</h3>${isHR() ? '<button class="btn sm" id="am">Run auto-mark now</button>' : ''}</div>
  <div class="filters"><label>From<input type="date" id="s" value="${start}"></label><label>To<input type="date" id="e" value="${end}"></label>
  <label>Status<select id="st"><option value="">All</option><option value="present">Present</option><option value="late">Late</option><option value="half_day">Half day</option><option value="absent">Absent</option><option value="on_leave">On leave</option></select></label>
  ${isStaff() ? `<label>Employee<select id="em">${opts(emps.map(e => [e.id, e.name]), '', 'Everyone')}</select></label>` : ''}</div><div id="list"></div></div>`;
  const load = guard(async () => {
    const rows = await api('/attendance' + qs({ start: $('#s').value, end: $('#e').value, status: $('#st').value, employee_id: $('#em')?.value }));
    $('#list').innerHTML = table([{ h: 'Date', f: r => fmtDate(r.date) }, { h: 'Employee', f: r => esc(r.employee_name) }, { h: 'Status', f: r => pill(r.status) },
    { h: 'Check-in', f: r => fmtTime(r.check_in) + (r.checkin_flag ? ` ${pill(r.checkin_flag)}` : '') }, { h: 'Late by', f: r => r.late_minutes ? r.late_minutes + ' min' : '—' },
    { h: 'Check-out', f: r => fmtTime(r.check_out) + (r.early_leave_minutes ? `<div class="sm muted">${r.early_leave_minutes} min early</div>` : '') },
    { h: 'Hours', f: r => r.hours ?? '—' }, { h: 'Overtime', f: r => r.overtime_hours ? r.overtime_hours + ' h' : '—' }, { h: 'Source', f: r => r.source }], rows, 'No records in this range.');
  });
  ['s', 'e', 'st', 'em'].forEach(i => $('#' + i) && ($('#' + i).onchange = load));
  if (isHR()) $('#am').onclick = guard(async () => { const r = await api('/attendance/auto-mark', { method: 'POST' }); toast(`${r.marked_absent} marked absent`, 'ok'); load(); });
  load();
};

/* ---------- Leave requests ---------- */
pages.leaves = async v => {
  const [bal, pol, list] = await Promise.all([api('/leaves/balance'), api('/leaves/policies'), api('/leaves')]);
  v.innerHTML = `<div class="grid">${bal.map(b => `<div class="kpi leave"><b>${b.remaining ?? '∞'}</b><span>${esc(b.leave_type)} left${b.total ? ` of ${b.total}` : ''}</span></div>`).join('')}</div>
  <div class="split"><div class="card"><h3>Request leave</h3><form id="lf"><label>Type<select name="leave_type">${opts(pol.policies.map(p => [p.leave_type, p.leave_type]), '')}</select></label>
  <div class="row"><label>From<input type="date" name="start_date" required min="${iso(new Date())}"></label><label>To<input type="date" name="end_date" required min="${iso(new Date())}"></label></div>
  <div id="cf"></div><label>Reason<textarea name="reason" rows="2" maxlength="500"></textarea></label><button class="btn primary">Submit request</button></form></div>
  <div class="card"><h3>How conflicts work</h3><p class="muted">To keep teams covered, no more than ${pol.conflict_limit} people from one department can be on approved leave on the same day. If your dates clash, you will see it here before you submit.</p></div></div>
  <div class="card"><h3>${isStaff() ? 'Requests from my team' : 'My requests'}</h3><div id="ll"></div></div>`;
  const lf = $('#lf');
  const check = guard(async () => {
    const s = lf.start_date.value, e = lf.end_date.value; if (!s || !e || e < s) { $('#cf').innerHTML = ''; return; }
    const c = await api('/leaves/conflicts' + qs({ start: s, end: e }));
    $('#cf').innerHTML = c.dates.length ? `<div class="warnbox">Your department is at its limit on: ${c.dates.slice(0, 5).map(fmtDate).join(', ')}. Pick other dates.</div>` : '<div class="okbox">No conflicts with your team.</div>';
  });
  lf.start_date.onchange = lf.end_date.onchange = check;
  lf.onsubmit = guard(async e => { e.preventDefault(); const r = await api('/leaves', { method: 'POST', body: Object.fromEntries(new FormData(lf)) }); toast(`Request sent (${r.days} working days)`, 'ok'); pages.leaves(v); });
  $('#ll').innerHTML = table([{ h: 'Employee', f: l => esc(l.employee_name) }, { h: 'Type', f: l => esc(l.leave_type) }, { h: 'Dates', f: l => `${fmtDate(l.start_date)} – ${fmtDate(l.end_date)}` },
  { h: 'Days', f: l => l.days }, { h: 'Reason', f: l => esc(l.reason) }, { h: 'Status', f: l => pill(l.status) },
  { h: '', f: l => l.can_review ? `<button class="btn sm" data-a="approved" data-id="${l.id}">Approve</button> <button class="btn sm danger" data-a="rejected" data-id="${l.id}">Reject</button>` : (l.status === 'pending' && l.employee_id === S.user.employee_id ? `<button class="btn sm" data-c="${l.id}">Cancel</button>` : '') }], list, 'No leave requests yet.');
  $('#ll').onclick = guard(async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.a) await api(`/leaves/${b.dataset.id}/review`, { method: 'PUT', body: { status: b.dataset.a } });
    else if (b.dataset.c) await api('/leaves/' + b.dataset.c, { method: 'DELETE' }); else return;
    toast('Updated', 'ok'); pages.leaves(v);
  });
};

/* ---------- Leave calendar + team availability ---------- */
const CAL = { d: new Date(), sel: iso(new Date()), dept: '' };
pages.calendar = async v => {
  const y = CAL.d.getFullYear(), m = CAL.d.getMonth();
  const first = new Date(y, m, 1), gridStart = addDays(first, -((first.getDay() + 6) % 7));
  const cells = [...Array(42)].map((_, i) => addDays(gridStart, i));
  const meta = isHR() ? await api('/employees/meta') : null;
  const [leaves, av, pol] = await Promise.all([api('/leaves/calendar' + qs({ start: iso(cells[0]), end: iso(cells[41]), department: CAL.dept })),
  api('/leaves/availability' + qs({ day: CAL.sel, department: CAL.dept })), api('/leaves/policies')]);
  const on = ds => leaves.filter(l => l.start_date <= ds && l.end_date >= ds);
  v.innerHTML = `<div class="card"><div class="head"><div><button class="btn sm" id="pm">&lt;</button> <b>${first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</b> <button class="btn sm" id="nm">&gt;</button> <button class="btn sm ghost" id="td">Today</button></div>
  ${isHR() ? `<select id="dp" style="width:auto">${opts(meta.departments.map(d => [d, d]), CAL.dept, 'All departments')}</select>` : `<span class="muted sm">${esc(S.user.department || '')} team</span>`}</div>
  <div class="cal">${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => `<div class="dh">${d}</div>`).join('')}
  ${cells.map(d => { const ds = iso(d), L = on(ds), wk = d.getDay() % 6 === 0; const ap = L.filter(l => l.status === 'approved');
    return `<div class="day ${d.getMonth() !== m ? 'out' : ''} ${wk ? 'wk' : ''} ${ds === CAL.sel ? 'sel' : ''} ${ds === iso(new Date()) ? 'today' : ''} ${!wk && ap.length >= pol.conflict_limit ? 'full' : ''}" data-d="${ds}"><span class="n">${d.getDate()}</span>
    ${L.slice(0, 3).map(l => `<span class="lv-chip ${l.status}" title="${esc(l.name)}: ${esc(l.leave_type)} (${l.status})">${esc(l.name.split(' ')[0])}</span>`).join('')}${L.length > 3 ? `<span class="muted sm">+${L.length - 3} more</span>` : ''}</div>`; }).join('')}</div>
  <div class="legend"><span><i style="background:var(--leave)"></i>Approved leave</span><span><i style="border:1px dashed var(--leave)"></i>Pending</span><span><i style="box-shadow:inset 0 0 0 2px var(--bad)"></i>Team at its leave limit</span></div></div>
  <div class="card"><h3>Team availability, ${fmtDate(CAL.sel)}</h3>${av.departments.length ? av.departments.map(d => `<div><div style="display:flex;justify-content:space-between"><b>${esc(d.department)}</b><span>${d.available} of ${d.total} available</span></div>
  <div class="bar"><i style="width:${100 * d.available / d.total}%;background:${d.available / d.total < .6 ? 'var(--warn)' : 'var(--ok)'}"></i></div>
  <div class="sm muted">${d.on_leave.length ? 'On leave: ' + d.on_leave.map(x => `${esc(x.name)} (${esc(x.leave_type)})`).join(', ') : 'Everyone is in.'}</div></div><br>`).join('') : '<div class="empty">No team data.</div>'}</div>`;
  $('#pm').onclick = () => { CAL.d = new Date(y, m - 1, 1); pages.calendar(v); }; $('#nm').onclick = () => { CAL.d = new Date(y, m + 1, 1); pages.calendar(v); };
  $('#td').onclick = () => { CAL.d = new Date(); CAL.sel = iso(new Date()); pages.calendar(v); };
  if ($('#dp')) $('#dp').onchange = e => { CAL.dept = e.target.value; pages.calendar(v); };
  v.querySelectorAll('.day').forEach(el => el.onclick = () => { CAL.sel = el.dataset.d; pages.calendar(v); });
};

/* ---------- Documents ---------- */
pages.documents = async v => {
  const emps = isHR() ? await api('/employees') : [];
  v.innerHTML = `<div class="card"><h3>Upload document</h3><form id="uf" class="row">
  ${isHR() ? `<label>Employee<select name="employee_id">${opts(emps.map(e => [e.id, e.name]), S.user.employee_id)}</select></label>` : ''}
  <label>Type<select name="doc_type">${['ID proof', 'Address proof', 'Certificate', 'Contract', 'Resume', 'Other'].map(t => `<option>${t}</option>`).join('')}</select></label>
  <label>Expiry date (optional)<input type="date" name="expiry_date"></label>
  <label>File (PDF, PNG, JPG, DOC, DOCX, max 5 MB)<input type="file" name="file" required accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"></label>
  <button class="btn primary fit">Upload</button></form></div>
  <div class="card"><div class="head"><h3>Documents</h3>${isHR() ? `<select id="fe" style="width:auto">${opts(emps.map(e => [e.id, e.name]), '', 'All employees')}</select>` : ''}</div><div id="dl"></div></div>`;
  $('#uf').onsubmit = guard(async e => {
    e.preventDefault(); const fd = new FormData(e.target);
    for (const [k, val] of [...fd.entries()]) if (val === '') fd.delete(k);
    await api('/documents', { method: 'POST', form: fd }); toast('Document uploaded', 'ok'); pages.documents(v);
  });
  const load = guard(async () => {
    const rows = await api('/documents' + qs({ employee_id: $('#fe')?.value }));
    const soon = d => d && pd(d) <= addDays(new Date(), 30);
    $('#dl').innerHTML = table([{ h: 'File', f: d => `<b>${esc(d.file_name)}</b>` }, { h: 'Type', f: d => esc(d.doc_type) }, ...(isHR() ? [{ h: 'Employee', f: d => esc(d.employee_name) }] : []),
    { h: 'Uploaded', f: d => fmtDate(d.uploaded_at) }, { h: 'Expires', f: d => d.expiry_date ? fmtDate(d.expiry_date) + (soon(d.expiry_date) ? ' ' + pill(pd(d.expiry_date) < new Date() ? 'expired' : 'pending') : '') : '—' },
    { h: 'Size', f: d => Math.max(1, Math.round(d.size / 1024)) + ' KB' },
    { h: '', f: d => `<button class="btn sm" data-v="${d.id}">View</button> <button class="btn sm" data-dl="${d.id}">Download</button> <button class="btn sm danger" data-x="${d.id}">Delete</button>` }], rows, 'No documents uploaded yet.');
    $('#dl').onclick = guard(async e => {
      const b = e.target.closest('button'); if (!b) return; const d = rows.find(r => r.id == (b.dataset.v || b.dataset.dl || b.dataset.x));
      if (b.dataset.x) { if (!confirm('Delete ' + d.file_name + '?')) return; await api('/documents/' + d.id, { method: 'DELETE' }); load(); return; }
      const blob = await fetchBlob(`/documents/${d.id}/download${b.dataset.v ? '?inline=true' : ''}`); const url = URL.createObjectURL(blob);
      if (b.dataset.dl) { const a = document.createElement('a'); a.href = url; a.download = d.file_name; a.click(); return; }
      if (d.content_type.startsWith('image/')) openModal(d.file_name, `<img src="${url}" alt="" style="max-width:100%">`, null, '', true);
      else if (d.content_type === 'application/pdf') openModal(d.file_name, `<iframe src="${url}" style="width:100%;height:70vh;border:0"></iframe>`, null, '', true);
      else { const a = document.createElement('a'); a.href = url; a.download = d.file_name; a.click(); toast('This type cannot be previewed, so it was downloaded.'); }
    });
  });
  if ($('#fe')) $('#fe').onchange = load; load();
};

/* ---------- Performance ---------- */
pages.performance = async v => {
  const emps = isStaff() ? (await api('/employees')).filter(e => e.id !== S.user.employee_id) : [];
  v.innerHTML = `${isStaff() ? `<div class="card"><h3>Add review</h3><form id="pf"><div class="row"><label>Employee<select name="employee_id" id="pe" required>${opts(emps.map(e => [e.id, `${e.name} (${e.department})`]), '', 'Choose…')}</select></label>
  <label>Review period<input name="review_period" required placeholder="e.g. 2026 Q3" maxlength="40"></label></div>
  <label>Rating</label><div class="rate">${[[1, 'Needs work'], [2, 'Below'], [3, 'Meets'], [4, 'Strong'], [5, 'Outstanding']].map(([n, t]) => `<label><input type="radio" name="rating" value="${n}" ${n === 4 ? 'checked' : ''}><span>${n} · ${t}</span></label>`).join('')}</div><br>
  <label>Feedback<textarea name="feedback" rows="3" maxlength="2000" placeholder="What went well, and what to improve next period"></textarea></label><button class="btn primary">Save review</button></form></div>` : ''}
  <div class="card"><div class="head"><h3>${isStaff() ? 'Review history' : 'My reviews'}</h3><span id="avg" class="muted"></span></div><div id="ph"></div></div>`;
  const load = guard(async () => {
    const rows = await api('/performance' + qs({ employee_id: isStaff() ? $('#pe')?.value : '' }));
    if (rows.length) $('#avg').innerHTML = 'Average ' + stars(Math.round(rows.reduce((a, r) => a + r.rating, 0) / rows.length * 100) / 100);
    $('#ph').innerHTML = table([{ h: 'Employee', f: r => esc(r.employee_name) }, { h: 'Period', f: r => esc(r.review_period) }, { h: 'Rating', f: r => stars(r.rating) },
    { h: 'Feedback', f: r => esc(r.feedback) }, { h: 'Reviewer', f: r => esc(r.reviewer) }, { h: 'Date', f: r => fmtDate(r.created_at) }], rows, 'No reviews yet.');
  });
  if (isStaff()) {
    $('#pe').onchange = load;
    $('#pf').onsubmit = guard(async e => {
      e.preventDefault(); const b = Object.fromEntries(new FormData(e.target)); if (!b.employee_id) throw new Error('Choose an employee first');
      b.employee_id = +b.employee_id; b.rating = +b.rating; await api('/performance', { method: 'POST', body: b }); toast('Review saved', 'ok'); e.target.review_period.value = ''; e.target.feedback.value = ''; load();
    });
  }
  load();
};

/* ---------- Payroll + payslip ---------- */
function payslipHtml(p) {
  const r = (a, b) => `<tr><td>${a}</td><td>${b}</td></tr>`;
  return `<div class="payslip"><h3>Payslip, ${esc(p.month)}</h3><div class="muted sm">${esc(p.employee_name)} · ${esc(p.department)}</div>
  <table><thead><tr><th>Earnings</th><th>Amount</th></tr></thead><tbody>${r('Basic salary', money(p.basic))}${r('Allowances (HRA & other)', money(p.allowances))}${r('Overtime / bonus', money(p.bonus))}</tbody>
  <thead><tr><th>Deductions</th><th></th></tr></thead><tbody>${r('Absence / half-day deductions', money(p.deductions))}<tr class="net"><td>Net pay</td><td>${money(p.net)}</td></tr></tbody></table></div>`;
}
pages.payroll = async v => {
  const rows = await api('/payroll');
  const byMonth = Object.values(rows.reduce((m, p) => { (m[p.month] ||= { month: p.month, n: 0, net: 0, ded: 0 }); m[p.month].n++; m[p.month].net += p.net; m[p.month].ded += p.deductions; return m; }, {}));
  v.innerHTML = `${isHR() ? `<div class="card"><h3>Process payroll</h3><form id="rf" class="row"><label>Month<input type="month" name="month" required value="${iso(new Date()).slice(0, 7)}"></label><button class="btn primary fit">Process payroll</button></form>
  <p class="muted sm">Salary split: 60% basic + 40% allowances. Absences are deducted at salary ÷ 22 (half-days count half). Overtime beyond 8 hours is paid at 1.5×.</p></div>
  <div class="card"><h3>Monthly summary</h3>${table([{ h: 'Month', f: m => m.month }, { h: 'Employees paid', f: m => m.n }, { h: 'Total deductions', f: m => money(m.ded) }, { h: 'Total net payout', f: m => `<b>${money(m.net)}</b>` }], byMonth, 'No payroll yet.')}</div>` : ''}
  <div class="card"><h3>${isHR() ? 'Payroll history' : 'My salary history'}</h3>${table([{ h: 'Month', f: p => p.month }, ...(isHR() ? [{ h: 'Employee', f: p => esc(p.employee_name) }] : []), { h: 'Basic', f: p => money(p.basic) }, { h: 'Allowances', f: p => money(p.allowances) },
  { h: 'Bonus/OT', f: p => money(p.bonus) }, { h: 'Deductions', f: p => money(p.deductions) }, { h: 'Net pay', f: p => `<b>${money(p.net)}</b>` }, { h: '', f: p => `<button class="btn sm" data-p="${p.id}">Payslip</button>` }], rows, 'No payroll processed yet.')}</div>`;
  if (isHR()) $('#rf').onsubmit = guard(async e => { e.preventDefault(); const r = await api('/payroll/process', { method: 'POST', body: { month: e.target.month.value } }); toast(`Processed ${r.processed} employee(s)`, 'ok'); pages.payroll(v); });
  v.onclick = e => {
    const b = e.target.closest('[data-p]'); if (!b) return; const p = rows.find(x => x.id == b.dataset.p);
    openModal('Payslip', payslipHtml(p) + '<button type="button" class="btn sm" id="psdl" style="margin-top:10px">Download payslip</button>', null, '', true);
    $('#psdl').onclick = () => {
      const html = `<!doctype html><meta charset="utf-8"><title>Payslip ${p.month}</title><style>body{font-family:Arial;max-width:560px;margin:30px auto}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #ccc;text-align:left}td:last-child,th:last-child{text-align:right}.net td{font-weight:bold;border-top:2px solid #000}</style>${payslipHtml(p)}`;
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([html], { type: 'text/html' })); a.download = `payslip-${p.employee_name.replace(/\s+/g, '_')}-${p.month}.html`; a.click();
    };
  };
};

/* ---------- My profile (self-service) ---------- */
pages.profile = async v => {
  const p = await api('/employees/me');
  v.innerHTML = `<div class="card"><h3>Personal details</h3><div class="profile">
  ${[['Name', p.name], ['Username', p.username], ['Email', p.email], ['System role', label(p.role)], ['Department', p.department], ['Job title', p.designation], ['Manager', p.manager || '—'], ['Shift', p.shift || 'Not assigned'], ['Joined', fmtDate(p.join_date)], ['Status', label(p.status)], ['Monthly salary', money(p.salary)]].map(([k, x]) => `<div><small>${k}</small>${esc(x)}</div>`).join('')}</div></div>
  <div class="card"><h3>Change password</h3><form id="pw" class="row"><label>Current password<input type="password" name="old_password" required></label><label>New password (min 8)<input type="password" name="new_password" minlength="8" required></label><button class="btn primary fit">Update</button></form></div>`;
  $('#pw').onsubmit = guard(async e => { e.preventDefault(); await api('/auth/change-password', { method: 'POST', body: Object.fromEntries(new FormData(e.target)) }); toast('Password updated', 'ok'); e.target.reset(); });
};

/* ---------- Admin: user management ---------- */
pages.users = async v => {
  const [users, meta] = await Promise.all([api('/users'), api('/employees/meta')]);
  v.innerHTML = `<div class="card"><div class="head"><h3>Users and roles</h3><button class="btn primary" id="nu">Add user</button></div>
  ${table([{ h: 'User', f: u => `<b>${esc(u.name || u.username)}</b><div class="muted sm">@${esc(u.username)} · ${esc(u.email)}</div>` }, { h: 'Department', f: u => esc(u.department || '—') },
  { h: 'Role', f: u => `<select data-role="${u.id}" ${u.id === S.user.id ? 'disabled' : ''} style="width:auto">${opts(['employee', 'manager', 'hr', 'admin'].map(r => [r, label(r)]), u.role)}</select>` },
  { h: 'Status', f: u => pill(u.is_active ? 'active' : 'inactive') },
  { h: '', f: u => u.id === S.user.id ? '<span class="muted sm">You</span>' : `<button class="btn sm" data-t="${u.id}">${u.is_active ? 'Deactivate' : 'Activate'}</button> <button class="btn sm" data-r="${u.id}">Reset password</button> <button class="btn sm danger" data-x="${u.id}">Delete</button>` }], users)}</div>`;
  v.onchange = guard(async e => { const s = e.target.closest('[data-role]'); if (!s) return; await api('/users/' + s.dataset.role, { method: 'PUT', body: { role: s.value } }); toast('Role updated', 'ok'); });
  v.onclick = guard(async e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.t) { const u = users.find(x => x.id == b.dataset.t); await api('/users/' + u.id, { method: 'PUT', body: { is_active: !u.is_active } }); pages.users(v); }
    else if (b.dataset.x) { const u = users.find(x => x.id == b.dataset.x); if (!confirm(`Delete ${u.username} and ALL their records? This cannot be undone.`)) return; await api('/users/' + u.id, { method: 'DELETE' }); toast('User deleted', 'ok'); pages.users(v); }
    else if (b.dataset.r) { const u = users.find(x => x.id == b.dataset.r); openModal('Reset password for ' + u.username, '<label>New password (min 8)<input name="new_password" type="password" minlength="8" required></label>', async d => { await api(`/users/${u.id}/reset-password`, { method: 'POST', body: d }); toast('Password reset', 'ok'); }, 'Reset'); }
  });
  $('#nu').onclick = () => openModal('Add user', `<div class="row"><label>Full name<input name="name" required minlength="2"></label><label>Username<input name="username" pattern="[A-Za-z0-9_.\\-]{3,40}" placeholder="auto from email"></label></div>
  <label>Email<input name="email" type="email" required></label><div class="row"><label>Department<input name="department" required list="dl2"></label><label>Job title<input name="designation" required></label></div>
  <datalist id="dl2">${meta.departments.map(d => `<option value="${esc(d)}">`).join('')}</datalist>
  <div class="row"><label>Role<select name="role"><option>employee</option><option>manager</option><option>hr</option><option>admin</option></select></label><label>Password (min 8)<input name="password" type="password" minlength="8" required></label></div>`,
    async d => { await api('/employees', { method: 'POST', body: clean(d) }); toast('User created', 'ok'); pages.users(v); }, 'Create user');
};

/* ---------- Analytics ---------- */
pages.analytics = async v => {
  const meta = await api('/employees/meta');
  v.innerHTML = `<div class="card"><div class="filters"><label>From<input type="date" id="s" value="${iso(addDays(new Date(), -29))}"></label><label>To<input type="date" id="e" value="${iso(new Date())}"></label>
  <label>Department<select id="d">${opts(meta.departments.map(d => [d, d]), '', 'All departments')}</select></label></div></div><div id="out"></div>`;
  const load = guard(async () => {
    const a = await api('/analytics/overview' + qs({ start: $('#s').value, end: $('#e').value, department: $('#d').value }));
    const k = a.kpis, t = a.attendance_trend, lt = a.leave_trend;
    const lc = ['#7b5be6', '#2f5bea', '#d98a00', '#1b9e77', '#d6453d'];
    $('#out').innerHTML = `<div class="grid"><div class="kpi"><b>${k.headcount}</b><span>Employees</span></div><div class="kpi ok"><b>${k.attendance_rate}%</b><span>Attendance rate</span></div>
    <div class="kpi warn"><b>${k.late_count}</b><span>Late check-ins</span></div><div class="kpi bad"><b>${k.absent_count}</b><span>Absences</span></div>
    <div class="kpi leave"><b>${k.leave_days}</b><span>Leave days taken</span></div><div class="kpi"><b>${k.avg_rating ?? '—'}</b><span>Average rating</span></div></div>
    <div class="card"><h3>Attendance trend</h3>${t.length ? lineChart(t.map(x => x.date), ['present', 'late', 'absent', 'on_leave'].map(s => ({ name: label(s), color: COLORS[s], values: t.map(x => x[s]) }))) : '<div class="empty">No weekdays in range.</div>'}</div>
    <div class="split"><div class="card"><h3>Leave trend (days by month)</h3>${lt.months.length ? stackedBars(lt.months, lt.types.map((ty, i) => ({ name: ty, color: lc[i % 5], values: lt.data[ty] }))) : '<div class="empty">No approved leave in this range.</div>'}</div>
    <div class="card"><h3>Rating distribution</h3>${hbars(Object.entries(a.rating_distribution).map(([r, n]) => [r + ' star' + (r > 1 ? 's' : ''), n]), Math.max(1, ...Object.values(a.rating_distribution)), 'var(--warn)')}
    <h3 style="margin-top:14px">Top performers</h3>${a.top_performers.map(p => `<div class="sm" style="display:flex;justify-content:space-between;padding:3px 0"><span>${esc(p.name)}</span>${stars(p.rating)}</div>`).join('') || '<div class="empty">No reviews yet.</div>'}</div></div>
    <div class="card"><div class="head"><h3>Department report</h3><button class="btn sm" id="csv">Export CSV</button></div>${table([{ h: 'Department', f: d => `<b>${esc(d.department)}</b>` }, { h: 'Headcount', f: d => d.headcount },
    { h: 'Attendance', f: d => d.attendance_rate + '%' }, { h: 'Late rate', f: d => d.late_rate + '%' }, { h: 'Absences', f: d => d.absent }, { h: 'Leave days', f: d => d.leave_days }, { h: 'Avg rating', f: d => stars(d.avg_rating) }], a.departments, 'No data for this filter.')}</div>`;
    $('#csv').onclick = () => {
      const head = ['Department', 'Headcount', 'Attendance %', 'Late %', 'Absences', 'Leave days', 'Avg rating'];
      const csv = [head, ...a.departments.map(d => [d.department, d.headcount, d.attendance_rate, d.late_rate, d.absent, d.leave_days, d.avg_rating ?? ''])].map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\n');
      const l = document.createElement('a'); l.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); l.download = 'department-report.csv'; l.click();
    };
  });
  ['s', 'e', 'd'].forEach(i => $('#' + i).onchange = load); load();
};

/* ---------- Alerts ---------- */
pages.notifications = async v => {
  const d = await api('/notifications');
  v.innerHTML = `<div class="card"><div class="head"><h3>Alerts <span class="muted sm">(${d.unread} unread)</span></h3><button class="btn sm" id="ra">Mark all read</button></div>
  ${d.items.length ? `<ul class="note">${d.items.map(n => `<li class="${n.is_read ? '' : 'unread'}" data-id="${n.id}"><span class="dot"></span><div><b>${esc(n.title)}</b> ${pill(n.type)}<div>${esc(n.message)}</div><time>${new Date(n.created_at).toLocaleString()}</time></div></li>`).join('')}</ul>` : '<div class="empty">You are all caught up.</div>'}</div>`;
  $('#ra').onclick = guard(async () => { await api('/notifications/read-all', { method: 'POST' }); S.lastUnread = 0; pollNotifications(); pages.notifications(v); });
  v.querySelectorAll('li.unread').forEach(li => li.onclick = guard(async () => { await api(`/notifications/${li.dataset.id}/read`, { method: 'POST' }); li.classList.remove('unread'); pollNotifications(); }));
};
