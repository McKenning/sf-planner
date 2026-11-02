// Save import page: pick a .sav -> worker parses -> server groups two ways -> review/edit -> save.
const $ = (s, r = document) => r.querySelector(s);
const PALETTE = ['#1f77b4', '#d95f02', '#1b9e77', '#7570b3', '#e7298a', '#66a61e', '#a6761d', '#e6ab02', '#17becf', '#8c564b'];
const state = { payload: null, fileName: '', results: {}, groups: [], method: null, selected: new Set(), params: { threshold: 60, long_link: 300 } };
const factories = JSON.parse($('#factories-json').textContent);

const post = async (url, body) => {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });

function setStatus(msg, kind = '') {
  const el = $('#status');
  el.textContent = msg;
  el.className = 'note ' + kind;
}

// ---- 1. parse in a worker ----
$('#file').addEventListener('change', async (ev) => {
  const f = ev.target.files[0];
  if (!f) return;
  state.fileName = f.name;
  $('#review').hidden = true;
  setStatus(`Reading ${f.name} (${(f.size / 1048576).toFixed(1)} MB)…`);
  const bar = $('#bar');
  bar.hidden = false;
  const buffer = await f.arrayBuffer();
  const worker = new Worker('/static/js/import.worker.js', { type: 'module' });
  worker.onmessage = async (m) => {
    const d = m.data;
    if (d.type === 'progress') {
      bar.value = d.phase === 'extract' ? 100 : Math.round((d.progress || 0) * 100);
      setStatus(d.phase === 'extract' ? 'Extracting buildings…' : `Parsing save… ${bar.value}% ${d.msg || ''}`);
    } else if (d.type === 'done') {
      worker.terminate();
      state.payload = d.payload;
      const p = d.payload;
      window.__parseSeconds = p.game.parseSeconds; // read by the browser check
      setStatus(`Parsed in ${p.game.parseSeconds.toFixed(1)} s: ${p.buildings.length} buildings, ${p.links.length} links (${(JSON.stringify(p).length / 1024).toFixed(0)} KB sent to the server).`, 'ok');
      bar.hidden = true;
      await regroup();
    } else if (d.type === 'error') {
      worker.terminate();
      bar.hidden = true;
      setStatus('Could not read that save: ' + d.message, 'bad');
    }
  };
  worker.postMessage({ buffer, name: f.name }, [buffer]);
});

// ---- 2. group both ways ----
let regroupTimer = null;
async function regroup() {
  setStatus('Grouping…');
  const common = { payload: state.payload, threshold: state.params.threshold, long_link: state.params.long_link };
  const [c, d] = await Promise.all([post('/api/import/group', { ...common, method: 'connection' }),
                                    post('/api/import/group', { ...common, method: 'distance' })]);
  state.results = { connection: c, distance: d };
  $('#review').hidden = false;
  renderCompare();
  if (state.method) useMethod(state.method, false);
  setStatus(`Grouped: ${c.groups.length} groups by connection, ${d.groups.length} by distance.`, 'ok');
}
for (const id of ['threshold', 'long_link']) {
  $('#' + id).addEventListener('input', (e) => {
    state.params[id] = Number(e.target.value);
    $('#' + id + '-val').textContent = e.target.value + ' m';
    clearTimeout(regroupTimer);
    regroupTimer = setTimeout(() => state.payload && regroup(), 400);
  });
}

function plot(svg, groups, selected) {
  const B = state.payload.buildings;
  const pts = [];
  groups.forEach((g, gi) => g.members.forEach((i) => {
    if (B[i].kind !== 'junction') pts.push([B[i].x, B[i].y, gi]);
  }));
  if (!pts.length) { svg.innerHTML = ''; return; }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1), pad = Math.max(w, h) * 0.03;
  svg.setAttribute('viewBox', `${x0 - pad} ${y0 - pad} ${w + 2 * pad} ${h + 2 * pad}`);
  const r = Math.max(w, h) / 260;
  svg.innerHTML = pts.map(([x, y, gi]) => {
    const dim = selected && selected.size && !selected.has(gi) ? 0.15 : 0.9;
    return `<circle cx="${x}" cy="${y}" r="${r}" fill="${PALETTE[gi % PALETTE.length]}" opacity="${dim}"/>`;
  }).join('');
}

function groupRow(g, gi) {
  const sw = `<span class="sw" style="background:${PALETTE[gi % PALETTE.length]}"></span>`;
  const st = Object.entries(g.stations).map(([k, v]) => `${v} ${k} station${v > 1 ? 's' : ''}`).join(', ');
  return `${sw}<strong>${esc(g.name)}</strong> <span class="tag">${g.label}</span>
    <span class="note">${g.machines} machines · ${g.extractors} extractors · ${g.generators} generators · ${fmt(g.power_mw)} MW${st ? ' · ' + st : ''}</span>`;
}

function renderCompare() {
  for (const m of ['connection', 'distance']) {
    const r = state.results[m];
    plot($('#plot-' + m), r.groups);
    $('#list-' + m).innerHTML = r.groups.map((g, gi) => `<li>${groupRow(g, gi)}</li>`).join('');
    $('#count-' + m).textContent = `${r.groups.length} groups`;
  }
}

$('#use-connection').onclick = () => useMethod('connection', true);
$('#use-distance').onclick = () => useMethod('distance', true);
function useMethod(m, reset) {
  state.method = m;
  if (reset) state.groups = state.results[m].groups.map((g) => ({ ...g, include: g.label !== 'other', attach: '' }));
  state.selected.clear();
  $('#edit').hidden = false;
  renderEdit();
}

// ---- 3. edit: rename, label, attach, merge, split ----
function renderEdit() {
  const rows = $('#rows');
  rows.innerHTML = state.groups.map((g, gi) => `
    <tr data-i="${gi}" class="${state.selected.has(gi) ? 'cur' : ''}">
      <td><input type="checkbox" class="sel" aria-label="Select ${esc(g.name)}" ${state.selected.has(gi) ? 'checked' : ''}></td>
      <td><span class="sw" style="background:${PALETTE[gi % PALETTE.length]}"></span><input class="nm" value="${esc(g.name)}" aria-label="Group name"></td>
      <td><select class="lb" aria-label="Type">${['factory', 'outpost', 'power', 'other'].map((l) => `<option ${l === g.label ? 'selected' : ''}>${l}</option>`).join('')}</select></td>
      <td class="num">${g.machines}</td><td class="num">${g.extractors}</td><td class="num">${g.generators}</td>
      <td class="num">${fmt(g.power_mw)} MW</td>
      <td>${g.outputs.slice(0, 2).map((o) => `${esc(o.item)} ${fmt(o.rate)}/min`).join('<br>') || '—'}</td>
      <td><select class="at" aria-label="Attach to planned factory"><option value="">New factory</option>${factories.map((f) => `<option value="${f.id}" ${String(f.id) === String(g.attach) ? 'selected' : ''}>${esc(f.name)}</option>`).join('')}</select></td>
      <td><label><input type="checkbox" class="inc" ${g.include ? 'checked' : ''}> import</label></td>
      <td><button class="quiet split">Split</button></td>
    </tr>`).join('');
  plot($('#plot-edit'), state.groups, state.selected);
  $('#summary-edit').textContent = `${state.groups.filter((g) => g.include).length} of ${state.groups.length} groups will be imported.`;
}

$('#rows').addEventListener('input', (e) => {
  const tr = e.target.closest('tr'); if (!tr) return;
  const g = state.groups[+tr.dataset.i];
  if (e.target.classList.contains('nm')) g.name = e.target.value;
  if (e.target.classList.contains('lb')) g.label = e.target.value;
  if (e.target.classList.contains('at')) g.attach = e.target.value;
  if (e.target.classList.contains('inc')) { g.include = e.target.checked; renderEdit(); }
  if (e.target.classList.contains('sel')) {
    const i = +tr.dataset.i;
    e.target.checked ? state.selected.add(i) : state.selected.delete(i);
    renderEdit();
  }
});
$('#rows').addEventListener('click', async (e) => {
  if (!e.target.classList.contains('split')) return;
  const gi = +e.target.closest('tr').dataset.i;
  await splitGroup(gi);
});

$('#merge').onclick = () => {
  const ids = [...state.selected].sort((a, b) => a - b);
  if (ids.length < 2) { setStatus('Tick two or more groups to merge.', 'bad'); return; }
  const first = state.groups[ids[0]];
  const merged = ids.map((i) => state.groups[i]);
  first.members = merged.flatMap((g) => g.members).sort((a, b) => a - b);
  for (const k of ['machines', 'extractors', 'generators', 'power_mw', 'size']) first[k] = merged.reduce((s, g) => s + g[k], 0);
  first.outputs = []; first.needs = []; first.recipes = merged.flatMap((g) => g.recipes);
  first.name = merged.sort((a, b) => b.machines - a.machines)[0].name;
  first.label = merged.some((g) => g.label === 'factory') ? 'factory' : first.label;
  state.groups = state.groups.filter((g, i) => i === ids[0] || !ids.includes(i));
  state.selected.clear();
  renderEdit();
  setStatus(`Merged ${ids.length} groups. Rates are recomputed when you save.`, 'ok');
};

async function splitGroup(gi) {
  // split = regroup just this group's buildings with the *other* method
  const g = state.groups[gi];
  const other = state.method === 'connection' ? 'distance' : 'connection';
  const keep = new Map(g.members.map((old, n) => [old, n]));
  const B = state.payload.buildings;
  const sub = { format: 1, game: state.payload.game, buildings: g.members.map((i) => B[i]),
    links: state.payload.links.filter(([a, b]) => keep.has(a) && keep.has(b)).map(([a, b, l]) => [keep.get(a), keep.get(b), l]) };
  const r = await post('/api/import/group', { payload: sub, method: other, threshold: state.params.threshold / 2, long_link: state.params.long_link });
  if (r.groups.length < 2) { setStatus(`Splitting by ${other} gives one group — try the sliders.`, 'bad'); return; }
  const parts = r.groups.map((p) => ({ ...p, members: p.members.map((n) => g.members[n]), include: true, attach: '' }));
  state.groups.splice(gi, 1, ...parts);
  state.selected.clear();
  renderEdit();
  setStatus(`Split into ${parts.length} groups (by ${other}).`, 'ok');
}

// ---- 4. save ----
$('#save').onclick = async () => {
  const B = state.payload.buildings;
  const groups = state.groups.filter((g) => g.include).map((g) => ({
    ids: g.members.map((i) => B[i].id), name: g.name, label: g.label, attach_factory_id: g.attach ? Number(g.attach) : null }));
  if (!groups.length) { setStatus('Nothing selected to import.', 'bad'); return; }
  $('#save').disabled = true;
  try {
    const r = await post('/api/import/save', { payload: state.payload, groups, file_name: state.fileName, params: state.params });
    $('#result').hidden = false;
    $('#result').innerHTML = r.unchanged
      ? `<strong>No changes.</strong> ${esc(r.message)}`
      : `<strong>Saved.</strong> ${r.created} new factories, ${r.updated} updated from the previous import, ${r.attached} attached to planned factories, ${r.plants} power plant rows, ${r.flows} flows.
         ${r.unmatched.length ? `<br>Not found in this save (kept, flagged): ${r.unmatched.map(esc).join(', ')}` : ''}
         <br><a href="/factories">Factories</a> · <a href="/">World</a> · <a href="/flows">Flows</a>`;
    setStatus('Import saved.', 'ok');
  } catch (e) {
    setStatus('Save failed: ' + e.message, 'bad');
  } finally {
    $('#save').disabled = false;
  }
};
