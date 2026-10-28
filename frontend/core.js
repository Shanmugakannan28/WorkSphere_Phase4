/* WorkSphere core: helpers, API client, charts, router, notifications */
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const S = { token: localStorage.getItem('ws_token'), user: null, lastUnread: null };
const isStaff = () => ['admin', 'hr', 'manager'].includes(S.user.role);
const isHR = () => ['admin', 'hr'].includes(S.user.role);
const iso = d => { const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return z.toISOString().slice(0, 10); };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const pd = s => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDate = s => s ? pd(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
const fmtTime = s => s ? new Date(s).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';
const hhmm = t => (t || '').slice(0, 5);
const label = s => String(s || '').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
const pill = s => `<span class="pill ${esc(s)}">${esc(label(s))}</span>`;
const stars = r => r == null ? '—' : `<span class="stars" title="${r}/5">${'★'.repeat(Math.round(r))}${'☆'.repeat(5 - Math.round(r))}</span> ${r}`;
const money = n => (n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
const qs = o => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== '' && v != null) p.set(k, v); const s = p.toString(); return s ? '?' + s : ''; };
const clean = o => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v != null));

async function request(path, { method = 'GET', body, form } = {}) {
  const headers = {};
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  let data;
  if (form) data = form; else if (body !== undefined) { headers['Content-Type'] = 'application/json'; data = JSON.stringify(body); }
  const r = await fetch('/api' + path, { method, headers, body: data });
  if (r.status === 401 && path !== '/auth/login') { logout(); throw new Error('Your session expired. Please sign in again.'); }
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : (j.detail || []).map(e => (e.loc || []).slice(1).join('.') + ': ' + e.msg).join('; '); } catch { }
    throw new Error(msg);
  }
  return r;
}
const api = async (path, opt) => { const r = await request(path, opt); return r.json(); };
const fetchBlob = async path => (await request(path)).blob();

function toast(msg, kind = '') {
  const t = document.createElement('div'); t.className = 'toast ' + kind; t.textContent = msg;
  $('#toasts').append(t); setTimeout(() => t.remove(), 4200);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, 'err'); } };

function openModal(title, body, onSubmit, submitLabel = 'Save', wide = false) {
  const m = $('#modal'); m.className = wide ? 'wide' : '';
  m.innerHTML = `<form class="mform"><h3>${esc(title)}</h3>${body}<div class="actions"><button type="button" class="btn ghost" data-close>Cancel</button>${onSubmit ? `<button class="btn primary">${esc(submitLabel)}</button>` : ''}</div></form>`;
  const f = $('form', m);
  $('[data-close]', m).onclick = () => m.close();
  f.onsubmit = async e => {
    e.preventDefault();
    if (!onSubmit) return;
    try { await onSubmit(Object.fromEntries(new FormData(f)), f); m.close(); } catch (err) { toast(err.message, 'err'); }
  };
  m.showModal();
}

function table(cols, rows, empty = 'Nothing here yet.') {
  if (!rows.length) return `<div class="empty">${esc(empty)}</div>`;
  return `<div class="tablewrap"><table><thead><tr>${cols.map(c => `<th>${esc(c.h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(c => `<td>${c.f(r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
const opts = (items, sel, all) => (all ? `<option value="">${esc(all)}</option>` : '') + items.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(sel) ? 'selected' : ''}>${esc(t)}</option>`).join('');
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

/* ---------- charts (dependency-free SVG) ---------- */
function lineChart(labels, series) {
  const W = 640, H = 230, L = 34, B = 26, T = 10, R = 8;
  const max = Math.max(1, ...series.flatMap(s => s.values));
  const nice = Math.ceil(max / 4) * 4 || 4;
  const x = i => L + (labels.length < 2 ? 0 : i * (W - L - R) / (labels.length - 1));
  const y = v => T + (H - T - B) * (1 - v / nice);
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = nice * i / 4; g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; }
  const step = Math.max(1, Math.ceil(labels.length / 8));
  labels.forEach((l, i) => { if (i % step === 0) g += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(l.slice(5))}</text>`; });
  const lines = series.map(s => `<polyline fill="none" stroke="${s.color}" stroke-width="2.2" stroke-linejoin="round" points="${s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ')}"><title>${esc(s.name)}</title></polyline>`).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Trend chart">${g}${lines}</svg>` + legend(series);
}
const legend = s => `<div class="legend">${s.map(x => `<span><i style="background:${x.color}"></i>${esc(x.name)}</span>`).join('')}</div>`;
function stackedBars(labels, series) {
  const W = 640, H = 220, L = 34, B = 26, T = 10;
  const totals = labels.map((_, i) => series.reduce((a, s) => a + s.values[i], 0));
  const nice = Math.ceil(Math.max(1, ...totals) / 4) * 4 || 4;
  const bw = Math.min(60, (W - L) / Math.max(1, labels.length) * .6);
  let g = '';
  for (let i = 0; i <= 4; i++) { const v = nice * i / 4, yy = T + (H - T - B) * (1 - v / nice); g += `<line class="grid" x1="${L}" x2="${W}" y1="${yy}" y2="${yy}"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end">${v}</text>`; }
  labels.forEach((l, i) => {
    const cx = L + (i + .5) * (W - L) / labels.length; let acc = 0;
    series.forEach(s => { const h = (H - T - B) * s.values[i] / nice; acc += h; g += `<rect x="${cx - bw / 2}" y="${H - B - acc}" width="${bw}" height="${h}" fill="${s.color}"><title>${esc(s.name)}: ${s.values[i]}</title></rect>`; });
    g += `<text x="${cx}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>`;
  });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Leave chart">${g}</svg>` + legend(series);
}
function hbars(items, max, color = 'var(--accent)', fmt = v => v) {
  if (!items.length) return '<div class="empty">No data for this filter.</div>';
  return items.map(([n, v]) => `<div class="sm"><div style="display:flex;justify-content:space-between"><span>${esc(n)}</span><b>${v == null ? '—' : esc(fmt(v))}</b></div><div class="bar"><i style="width:${v == null ? 0 : Math.min(100, 100 * v / max)}%;background:${color}"></i></div></div>`).join('');
}

/* ---------- router ---------- */
const pages = {};
const NAV = [['dashboard', 'Dashboard'], ['announcements', 'Announcements'], ['tasks', 'Tasks'], ['onboarding', 'Onboarding'], ['employees', 'Employees', 1],
['shifts', 'Shifts & schedule'], ['attendance', 'Attendance'], ['leaves', 'Leave requests'], ['calendar', 'Leave calendar'], ['documents', 'Documents'],
['performance', 'Performance'], ['payroll', 'Payroll'], ['exit', 'Resignation & exit'], ['feedback', 'Feedback'], ['analytics', 'Analytics', 1],
['integrations', 'Reports & integrations'], ['users', 'User management', 2], ['profile', 'Profile & settings'], ['notifications', 'Alerts']];
const allowed = n => !n[2] || (n[2] === 1 && isStaff()) || (n[2] === 2 && S.user.role === 'admin');

function buildNav() {
  $('#nav').innerHTML = NAV.filter(allowed).map(n => `<a href="#/${n[0]}" data-p="${n[0]}">${n[1]}</a>`).join('');
}
async function route() {
  if (!S.user) return;
  const seg = location.hash.replace(/^#\//, '').split('/'); const p = seg[0] || 'dashboard', arg = seg[1];
  const item = NAV.find(n => n[0] === p && allowed(n));
  if (!item) { location.hash = '#/dashboard'; return; }
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.p === p));
  $('#page-title').textContent = item[1]; $('#side').classList.remove('open');
  const v = $('#view'); v.onclick = null; v.onchange = null; v.innerHTML = '<div class="empty">Loading…</div>';
  try { await pages[p](v, arg); } catch (e) { v.innerHTML = `<div class="card"><div class="warnbox">${esc(e.message)}</div></div>`; }
}

/* ---------- notifications (polling every 6s) ---------- */
async function pollNotifications() {
  if (!S.user) return;
  try {
    const d = await api('/notifications?unread_only=true');
    const b = $('#badge'); b.textContent = d.unread; b.classList.toggle('hidden', !d.unread);
    if (S.lastUnread !== null && d.unread > S.lastUnread) {
      d.items.slice(0, d.unread - S.lastUnread).forEach(n => toast(n.title + ': ' + n.message));
      if (location.hash === '#/notifications') route();
    }
    S.lastUnread = d.unread;
  } catch { }
}

/* ---------- auth + boot ---------- */
function logout() {
  localStorage.removeItem('ws_token'); S.token = null; S.user = null; S.lastUnread = null;
  $('#app').classList.add('hidden'); $('#login').classList.remove('hidden');
}
function enterApp() {
  $('#login').classList.add('hidden'); $('#app').classList.remove('hidden');
  $('#who-name').textContent = S.user.name; $('#who-role').textContent = label(S.user.role);
  buildNav(); route(); pollNotifications();
}
async function boot() {
  $('#login-form').onsubmit = async e => {
    e.preventDefault(); $('#login-err').textContent = '';
    try {
      const d = await api('/auth/login', { method: 'POST', body: Object.fromEntries(new FormData(e.target)) });
      S.token = d.access_token; S.user = d.user; localStorage.setItem('ws_token', S.token);
      location.hash = '#/dashboard'; enterApp();
    } catch (err) { $('#login-err').textContent = err.message; }
  };
  document.querySelectorAll('.demo button').forEach(b => b.onclick = () => {
    const f = $('#login-form'); f.email.value = b.dataset.u; f.password.value = b.dataset.p;
  });
  $('#reg').onclick = e => {
    e.preventDefault();
    openModal('Create employee account', `<label>Full name<input name="full_name" required minlength="2"></label><label>Username<input name="username" required pattern="[A-Za-z0-9_.\\-]{3,40}" title="3-40 letters, numbers, . _ -"></label>
    <label>Email<input name="email" type="email" required></label><label>Password (min 8 characters)<input name="password" type="password" required minlength="8"></label>`,
      async d => { const r = await api('/auth/register', { method: 'POST', body: d }); S.token = r.access_token; S.user = r.user; localStorage.setItem('ws_token', S.token); location.hash = '#/dashboard'; enterApp(); }, 'Create account');
  };
  $('#logout').onclick = logout;
  $('#burger').onclick = () => $('#side').classList.toggle('open');
  window.addEventListener('hashchange', route);
  setInterval(pollNotifications, 6000);
  if (S.token) { try { S.user = await api('/auth/me'); enterApp(); return; } catch { } }
  $('#login').classList.remove('hidden');
}
