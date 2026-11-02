// App shell: theme toggle (system / light / dark) and Ctrl+K search palette.
const root = document.documentElement;
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { v ? localStorage.setItem(k, v) : localStorage.removeItem(k); } catch (e) { /* private mode */ } },
};

// ---- theme ----
const themeBtn = document.getElementById('theme');
const modes = ['system', 'light', 'dark'];
function applyTheme(m) {
  if (m === 'light' || m === 'dark') root.dataset.theme = m; else delete root.dataset.theme;
  themeBtn.textContent = 'Theme: ' + m;
}
let mode = modes.includes(store.get('sfp-theme')) ? store.get('sfp-theme') : 'system';
applyTheme(mode);
themeBtn.addEventListener('click', () => {
  mode = modes[(modes.indexOf(mode) + 1) % modes.length];
  store.set('sfp-theme', mode === 'system' ? null : mode);
  applyTheme(mode);
});

// ---- search palette ----
const pal = document.getElementById('palette');
const q = document.getElementById('q');
const list = document.getElementById('results');
let timer = null, seq = 0, opener = null;
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function open() {
  opener = document.activeElement;
  pal.hidden = false;
  q.value = '';
  list.innerHTML = '';
  q.focus();
  search();
}
function close() {
  pal.hidden = true;
  if (opener && opener.focus) opener.focus();
}
async function search() {
  const mine = ++seq;
  const r = await fetch('/api/search?q=' + encodeURIComponent(q.value)).then((x) => x.json()).catch(() => ({ results: [] }));
  if (mine !== seq) return;
  list.innerHTML = r.results.map((x) =>
    `<li><a href="${esc(x.url)}"><span>${esc(x.name)}</span><span class="note">${esc(x.kind)}${x.detail ? ' · ' + esc(x.detail) : ''}</span></a></li>`).join('')
    || '<li class="note" style="padding:8px">No matches.</li>';
}
document.getElementById('open-search').addEventListener('click', open);
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); pal.hidden ? open() : close(); }
  else if (e.key === 'Escape' && !pal.hidden) close();
  else if (!pal.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
    const links = [...list.querySelectorAll('a')];
    if (!links.length) return;
    e.preventDefault();
    const i = links.indexOf(document.activeElement);
    const n = e.key === 'ArrowDown' ? (i + 1) % links.length : (i <= 0 ? links.length - 1 : i - 1);
    links[n].focus();
  }
});
q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(search, 120); });
q.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const a = list.querySelector('a'); if (a) location.href = a.href; } });
pal.addEventListener('click', (e) => { if (e.target === pal) close(); });
