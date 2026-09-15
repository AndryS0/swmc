/* Stormworks microprocessor editor.
 *
 * Renders <group><components> as an SVG node graph. All mutations go through
 * POST /api/edit, which applies them with the same batch semantics the MCP
 * server uses, so the browser and an agent editing the same document stay in
 * agreement. Server-sent events tell us when to refetch.
 */
'use strict';

const PPU = 48;                 // pixels per game grid unit at zoom 1
const SVG_NS = 'http://www.w3.org/2000/svg';

/* Signal colours. Keys are the engine's logic-node data types; the values are
 * defined in style.css so the palette lives in one place. Must stay in step
 * with DATA_TYPE in nodetypes.py -- tests/test_frontend.py checks that. */
const DT_COLOR = {
  0: 'var(--dt-bool)', 1: 'var(--dt-number)', 5: 'var(--dt-composite)',
  6: 'var(--dt-video)', 7: 'var(--dt-audio)',
};
const DT_NAME = {
  0: 'on/off', 1: 'number', 5: 'composite', 6: 'video', 7: 'audio',
};
const CAT_COLOR = {
  arithmetic: 'var(--cat-arithmetic)', logical: 'var(--cat-logical)',
  control: 'var(--cat-control)', composite: 'var(--cat-composite)',
  property: 'var(--cat-property)', bridge: 'var(--cat-bridge)',
};

const $ = (id) => document.getElementById(id);
const el = (tag, attrs, kids) => {
  const n = document.createElementNS(SVG_NS, tag);
  for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
  for (const c of kids || []) n.appendChild(c);
  return n;
};
const h = (tag, attrs, kids) => {
  const n = document.createElement(tag);
  for (const k in attrs || {}) {
    if (k === 'class') n.className = attrs[k];
    else if (k === 'text') n.textContent = attrs[k];
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), attrs[k]);
    else n.setAttribute(k, attrs[k]);
  }
  for (const c of kids || []) n.appendChild(c);
  return n;
};

// --------------------------------------------------------------------------
// state
// --------------------------------------------------------------------------
const S = {
  doc: null,
  types: { components: {}, bridge: {} },
  byId: new Map(),
  sel: new Set(),
  selWire: null,
  view: { tx: 0, ty: 0, s: 1 },
  flipY: false,
  snap: true,
  /* Roomy mode spreads the drawn positions apart and enlarges the boxes so a
   * full component name fits. The file's coordinates never change -- only the
   * rendering -- which is why the spread factor has to be divided back out
   * whenever screen space is converted to game space. */
  roomy: false,
  drag: null,
  link: null,
  busy: false,
};

const ROOMY_SPREAD = 2;
const ROOMY_W = 2.2;            // grid units
const spread = () => (S.roomy ? ROOMY_SPREAD : 1);

const worldY = (y) => (S.flipY ? -y : y) * PPU * spread();
const worldX = (x) => x * PPU * spread();
const unWorldY = (py) => (S.flipY ? -py : py) / (PPU * spread());
const unWorldX = (px) => px / (PPU * spread());
const snap = (v) => (S.snap ? Math.round(v / (S.doc?.grid || 0.25)) * (S.doc?.grid || 0.25) : Math.round(v * 1000) / 1000);

function screenToWorld(ev) {
  const r = $('canvas').getBoundingClientRect();
  const px = (ev.clientX - r.left - S.view.tx) / S.view.s;
  const py = (ev.clientY - r.top - S.view.ty) / S.view.s;
  return { x: unWorldX(px), y: unWorldY(py), px, py };
}

function spec(c) {
  const t = S.types || { components: {}, bridge: {} };
  const table = (c.bridge ? t.bridge : t.components) || {};
  return table[c.type] || { inputs: [], outputs: [], properties: [], name: '?' };
}

// --------------------------------------------------------------------------
// label layout
// --------------------------------------------------------------------------
const CHAR_W = 0.53;            // mean glyph width as a fraction of font size
const LINE_H = 1.16;

/**
 * Split into the smallest pieces a line may break between: words, and the
 * comma-separated runs inside them. Component names like
 * "Boolean f(x,y,z,w,a,b,c,d)" are otherwise one 18-character unbreakable word.
 */
function atomize(text) {
  const atoms = [];
  String(text).split(/\s+/).filter(Boolean).forEach((word, wi) => {
    const parts = [];
    let cur = '';
    for (const ch of word) {
      cur += ch;
      if (ch === ',') { parts.push(cur); cur = ''; }
    }
    if (cur) parts.push(cur);
    parts.forEach((p, pi) => atoms.push({ t: p, space: wi > 0 && pi === 0 }));
  });
  return atoms;
}

/**
 * Greedy wrap. Reports whether it had to break mid-atom (`hardBroken`) or drop
 * text entirely (`dropped`), so the caller can prefer a size that does neither.
 */
function wrapLabel(text, maxChars, maxLines) {
  if (maxChars < 1) return { lines: [], dropped: true, hardBroken: false };
  const atoms = atomize(text);
  const lines = [];
  let cur = '';
  let hardBroken = false;
  let i = 0;
  for (; i < atoms.length; i++) {
    const a = atoms[i];
    const cand = cur + (cur && a.space ? ' ' : '') + a.t;
    if (cand.length <= maxChars) { cur = cand; continue; }
    if (cur) {
      if (lines.length >= maxLines) break;
      lines.push(cur);
      cur = '';
    }
    let w = a.t;
    while (w.length > maxChars) {
      if (lines.length >= maxLines) break;
      lines.push(w.slice(0, maxChars));
      w = w.slice(maxChars);
      hardBroken = true;
    }
    if (lines.length >= maxLines && w.length > maxChars) break;
    cur = w;
  }
  if (cur && lines.length < maxLines) { lines.push(cur); cur = ''; }
  const dropped = i < atoms.length || !!cur;
  return { lines: lines.slice(0, maxLines), dropped, hardBroken };
}

/**
 * Pick the largest font size at which `text` fits the box whole, and return the
 * wrapped lines. Falls back to the smallest size with an ellipsis if nothing
 * fits -- the full name is always on the node's tooltip regardless.
 */
function layoutLabel(text, boxW, boxH, sizes) {
  const usableW = boxW - 12;
  const usableH = boxH - 4;
  const want = String(text).replace(/\s+/g, ' ').trim();
  const at = (fs) => {
    const maxChars = Math.floor(usableW / (fs * CHAR_W));
    const maxLines = Math.max(1, Math.floor(usableH / (fs * LINE_H)));
    return { fs, maxChars, maxLines, ...wrapLabel(want, maxChars, maxLines) };
  };
  const tries = sizes.map(at);
  // Best case: the whole name fits without breaking any word apart.
  const clean = tries.find((t) => !t.dropped && !t.hardBroken);
  if (clean) return { lines: clean.lines, fs: clean.fs, complete: true };
  // Next best: still every character, just split mid-token.
  const whole = tries.find((t) => !t.dropped);
  if (whole) return { lines: whole.lines, fs: whole.fs, complete: true };

  const last = tries[tries.length - 1];
  const lines = last.lines.slice();
  if (lines.length) {
    const tail = lines[lines.length - 1];
    lines[lines.length - 1] =
      tail.slice(0, Math.max(1, last.maxChars - 1)) + '…';
  }
  return { lines, fs: last.fs, complete: false };
}

/** Drawn size of a node in pixels. Roomy mode grows it to fit the full name. */
function nodeBox(c) {
  if (!S.roomy) return { w: c.w * PPU, h: c.h * PPU };
  const text = c.label || spec(c).name || '';
  const w = Math.max(c.w, ROOMY_W) * PPU;
  const probe = layoutLabel(text, w, 999, [10]);
  const needed = probe.lines.length * 10 * LINE_H + (c.label ? 11 : 0) + 8;
  return { w, h: Math.max(c.h * PPU, needed) };
}

// --------------------------------------------------------------------------
// transport
// --------------------------------------------------------------------------
function toast(msg, isErr) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'show' + (isErr ? ' err' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.className = ''; }, isErr ? 6000 : 2200);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({ error: r.statusText }));
  if (!r.ok) throw new Error(body.error || ('HTTP ' + r.status));
  return body;
}

async function edit(ops, label) {
  if (S.busy) return;
  S.busy = true;
  try {
    const doc = await api('/api/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ops }),
    });
    applyDoc(doc);
    if (label) toast(label);
    return doc;
  } catch (e) {
    toast(e.message, true);
    await refresh();
    throw e;
  } finally {
    S.busy = false;
  }
}

async function tool(name, args) {
  const out = await api('/api/call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool: name, args: args || {} }),
  });
  if (out.state) applyDoc(out.state);
  return out.result;
}

async function refresh() {
  applyDoc(await api('/api/state'));
}

// --------------------------------------------------------------------------
// render
// --------------------------------------------------------------------------
function applyDoc(doc) {
  S.doc = doc;
  S.byId = new Map(doc.components.map((c) => [c.id, c]));
  for (const id of [...S.sel]) if (!S.byId.has(id)) S.sel.delete(id);
  render();
  renderInspector();
  renderStatus();
  if (!$('issues').classList.contains('hidden')) renderIssues();
  if (!$('view-lua').hidden) { renderLuaPicker(); loadLuaSource(false); }
}

function renderLegend() {
  const box = $('hudLegend');
  if (box.children.length) return;   // static; build once
  for (const dt of Object.keys(DT_NAME)) {
    const chip = h('span', { class: 'chip' }, []);
    const dot = h('i', {});
    dot.style.background = DT_COLOR[dt];
    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(DT_NAME[dt]));
    box.appendChild(chip);
  }
}

function renderStatus() {
  const d = S.doc;
  $('mcName').textContent = d.header.name || '(unnamed)';
  $('mcPath').textContent = d.path;
  document.title = (d.header.name || 'microprocessor') + ' — swmc';
  const st = $('saveState');
  if (d.conflict) { st.textContent = 'CONFLICT on disk'; st.className = 'savestate conflict'; }
  else if (d.dirty) { st.textContent = 'unsaved'; st.className = 'savestate dirty'; }
  else { st.textContent = 'saved'; st.className = 'savestate'; }
  $('btnUndo').disabled = !d.undo_depth;
  $('btnRedo').disabled = !d.redo_depth;
  const errs = d.issues.filter((i) => i.level === 'error').length;
  $('btnValidate').textContent = errs ? `Validate (${errs})` : 'Validate';
  $('hudCount').textContent =
    `${d.components.length} components · ${d.wires.length} wires` +
    (S.sel.size ? ` · ${S.sel.size} selected` : '');
}

function pinPos(c, kind, index) {
  const n = kind === 'in' ? Math.max(1, c.in_fields.length) : Math.max(1, c.n_out);
  const box = nodeBox(c);
  const x = worldX(c.x) + (kind === 'in' ? 0 : box.w);
  const y = worldY(c.y) + ((index + 0.5) / n) * box.h;
  return { x, y };
}

function wirePath(a, b) {
  const dx = Math.max(24, Math.abs(b.x - a.x) * 0.45);
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}

function render() {
  const wires = $('layerWires');
  const nodes = $('layerNodes');
  wires.textContent = '';
  nodes.textContent = '';

  for (const w of S.doc.wires) {
    const src = S.byId.get(w.from);
    const dst = S.byId.get(w.to);
    if (!src || !dst) continue;
    const a = pinPos(src, 'out', w.out);
    const b = pinPos(dst, 'in', w.index);
    const dt = (spec(dst).inputs[w.index] || {}).dt;
    const key = `${w.to}:${w.field}`;
    const path = wirePath(a, b);
    const hit = el('path', { class: 'wirehit', d: path });
    const line = el('path', {
      class: 'wire' + (S.selWire === key ? ' sel' : ''),
      d: path, stroke: DT_COLOR[dt] || '#7c8798',
    });
    hit.addEventListener('mousedown', (ev) => {
      ev.stopPropagation();
      S.sel.clear(); S.selWire = key; render(); renderInspector(); renderStatus();
    });
    hit.addEventListener('dblclick', (ev) => {
      ev.stopPropagation();
      edit([{ op: 'disconnect', target: w.to, input: w.field }], 'wire removed');
    });
    const g = el('g', {}, [line, hit]);
    g.appendChild(el('title', {}, [])).textContent =
      `#${w.from} → #${w.to}.${w.field}  (double-click to remove)`;
    wires.appendChild(g);
  }

  for (const c of S.doc.components) {
    nodes.appendChild(nodeEl(c));
  }
}

function nodeEl(c) {
  const sp = spec(c);
  const x = worldX(c.x), y = worldY(c.y);
  const box = nodeBox(c);
  const w = box.w, hh = box.h;
  const g = el('g', {
    class: 'node' + (S.sel.has(c.id) ? ' selected' : ''),
    transform: `translate(${x},${y})`,
    'data-id': c.id,
  });

  g.appendChild(el('rect', { class: 'body', x: 0, y: 0, width: w, height: hh }));
  g.appendChild(el('rect', {
    class: 'cat', x: 0, y: 0, width: 4, height: hh,
    fill: CAT_COLOR[c.bridge ? 'bridge' : c.category] || '#444',
  }));

  // The full name always reaches the user, even when the box truncates it.
  const tip = el('title', {});
  tip.textContent = `#${c.id}  ${sp.name}` +
    (c.label ? `\n"${c.label}"` : '') +
    (sp.description ? `\n\n${sp.description}` : '');
  g.appendChild(tip);

  const primary = c.label || sp.name || ('type ' + c.type);
  const secondary = c.label ? sp.name : null;
  const sizes = S.roomy ? [10, 9, 8, 7] : [9, 8, 7, 6, 5.2];
  const subH = secondary ? 8 : 0;
  const lay = layoutLabel(primary, w, hh - subH, sizes);

  const blockH = lay.lines.length * lay.fs * LINE_H;
  let top = (hh - subH - blockH) / 2 + lay.fs * 0.82;
  const t = el('text', { class: 'lbl', x: 8, 'font-size': lay.fs });
  for (const line of lay.lines) {
    const span = el('tspan', { x: 8, y: top });
    span.textContent = line;
    t.appendChild(span);
    top += lay.fs * LINE_H;
  }
  g.appendChild(t);

  if (secondary) {
    const sub = layoutLabel(secondary, w, 10, [7, 6, 5.2]);
    const s2 = el('text', { class: 'sub', x: 8, y: hh - 4, 'font-size': sub.fs });
    s2.textContent = sub.lines[0] || '';
    g.appendChild(s2);
  }

  const nin = c.in_fields.length;
  for (let i = 0; i < nin; i++) {
    const p = { x: 0, y: ((i + 0.5) / nin) * hh };
    const dt = (sp.inputs[i] || {}).dt;
    g.appendChild(el('circle', {
      class: 'pin', cx: p.x, cy: p.y, r: 3.2,
      fill: DT_COLOR[dt] || '#7c8798',
      'data-pin': 'in', 'data-index': i,
    }));
    const hit = el('circle', {
      class: 'pinhit', cx: p.x, cy: p.y, r: 8,
      'data-pin': 'in', 'data-index': i,
    });
    hit.appendChild(el('title', {})).textContent =
      `${c.in_fields[i]} — ${(sp.inputs[i] || {}).label || ''} (${(sp.inputs[i] || {}).dt_name || '?'})`;
    g.appendChild(hit);
  }
  for (let i = 0; i < c.n_out; i++) {
    const p = { x: w, y: ((i + 0.5) / c.n_out) * hh };
    const dt = (sp.outputs[i] || {}).dt;
    g.appendChild(el('circle', {
      class: 'pin', cx: p.x, cy: p.y, r: 3.2,
      fill: DT_COLOR[dt] || '#7c8798',
      'data-pin': 'out', 'data-index': i,
    }));
    const hit = el('circle', {
      class: 'pinhit', cx: p.x, cy: p.y, r: 8,
      'data-pin': 'out', 'data-index': i,
    });
    hit.appendChild(el('title', {})).textContent =
      `output ${i} — ${(sp.outputs[i] || {}).label || ''} (${(sp.outputs[i] || {}).dt_name || '?'})`;
    g.appendChild(hit);
  }
  return g;
}

function applyView() {
  $('world').setAttribute('transform',
    `translate(${S.view.tx},${S.view.ty}) scale(${S.view.s})`);
  const pt = `translate(${S.view.tx},${S.view.ty}) scale(${S.view.s})`;
  $('grid').setAttribute('patternTransform', pt);
  $('gridBig').setAttribute('patternTransform', pt);
  $('hudZoom').textContent = Math.round(S.view.s * 100) + '%';
}

function fitView() {
  const cs = S.doc.components;
  const r = $('canvas').getBoundingClientRect();
  if (!cs.length) { S.view = { tx: r.width / 2, ty: r.height / 2, s: 1 }; return applyView(); }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const c of cs) {
    const box = nodeBox(c);
    x0 = Math.min(x0, worldX(c.x)); x1 = Math.max(x1, worldX(c.x) + box.w);
    const a = worldY(c.y), b = worldY(c.y) + box.h;
    y0 = Math.min(y0, Math.min(a, b)); y1 = Math.max(y1, Math.max(a, b));
  }
  const pad = 60;
  const s = Math.min((r.width - pad * 2) / (x1 - x0 || 1),
                     (r.height - pad * 2) / (y1 - y0 || 1), 3);
  S.view.s = Math.max(0.15, s);
  S.view.tx = r.width / 2 - ((x0 + x1) / 2) * S.view.s;
  S.view.ty = r.height / 2 - ((y0 + y1) / 2) * S.view.s;
  applyView();
}

// --------------------------------------------------------------------------
// palette
// --------------------------------------------------------------------------
function renderPalette() {
  const q = $('paletteSearch').value.trim().toLowerCase();
  const list = $('paletteList');
  list.textContent = '';
  const groups = {};
  const push = (t, bridge) => {
    const hay = `${t.type} ${t.name} ${t.cls} ${t.category} ${t.description}`.toLowerCase();
    if (q && !hay.includes(q)) return;
    const cat = bridge ? 'bridge pins' : t.category;
    (groups[cat] = groups[cat] || []).push({ t, bridge });
  };
  Object.values(S.types.components).forEach((t) => push(t, false));
  Object.values(S.types.bridge).forEach((t) => push(t, true));

  const order = ['arithmetic', 'logical', 'control', 'composite', 'property', 'bridge pins'];
  for (const cat of order) {
    const items = groups[cat];
    if (!items || !items.length) continue;
    const box = h('div', { class: 'pgroup' }, [h('h4', { text: cat })]);
    for (const { t, bridge } of items) {
      const row = h('div', {
        class: 'pitem', draggable: 'true',
        title: t.description || t.name,
      }, [
        h('span', { class: 'sw' }),
        h('span', { class: 'nm', text: t.name }),
        h('span', { class: 'ty', text: (bridge ? 'b' : '') + t.type }),
      ]);
      row.querySelector('.sw').style.background =
        CAT_COLOR[bridge ? 'bridge' : t.category] || '#444';
      row.addEventListener('dragstart', (ev) => {
        ev.dataTransfer.setData('text/plain', JSON.stringify({ type: t.type, bridge }));
        ev.dataTransfer.effectAllowed = 'copy';
      });
      row.addEventListener('click', () => {
        const r = $('canvas').getBoundingClientRect();
        addAt(t.type, bridge, screenToWorld({
          clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
        }));
      });
      box.appendChild(row);
    }
    list.appendChild(box);
  }
  if (!list.children.length) list.appendChild(h('div', { class: 'empty', text: 'no match' }));
}

async function addAt(type, bridge, pt) {
  const doc = await edit([{
    op: 'add_component', type, bridge,
    x: snap(pt.x), y: snap(pt.y),
  }], 'added');
  // select whatever is newest so the inspector opens on it
  if (doc) {
    const newest = doc.components.reduce((a, b) => (b.id > (a ? a.id : -1) ? b : a), null);
    if (newest) { S.sel.clear(); S.sel.add(newest.id); render(); renderInspector(); renderStatus(); }
  }
}

// --------------------------------------------------------------------------
// inspector
// --------------------------------------------------------------------------
function renderInspector() {
  const body = $('inspBody');
  const title = $('inspTitle');
  body.textContent = '';

  if (S.selWire) {
    const [to, field] = S.selWire.split(':');
    const w = S.doc.wires.find((x) => x.to == to && x.field === field);
    title.textContent = 'Wire';
    if (!w) { S.selWire = null; return renderInspector(); }
    body.appendChild(kv('from', '#' + w.from + (w.out ? ' (output ' + w.out + ')' : '')));
    body.appendChild(kv('to', `#${w.to} . ${w.field}`));
    body.appendChild(h('button', {
      class: 'danger', text: 'Remove wire',
      onclick: () => edit([{ op: 'disconnect', target: w.to, input: w.field }], 'wire removed'),
    }));
    return;
  }

  if (S.sel.size === 0) { title.textContent = 'Nothing selected'; return headerForm(body); }

  if (S.sel.size > 1) {
    title.textContent = S.sel.size + ' selected';
    const ids = [...S.sel];
    body.appendChild(h('h3', { class: 'sect', text: 'Align' }));
    const mk = (label, fn) => h('button', { text: label, onclick: fn });
    const row = h('div', { class: 'row' });
    row.style.display = 'flex'; row.style.gap = '6px'; row.style.flexWrap = 'wrap';
    row.appendChild(mk('Left', () => alignTo(ids, 'x', Math.min)));
    row.appendChild(mk('Right', () => alignTo(ids, 'x', Math.max)));
    row.appendChild(mk('Top', () => alignTo(ids, 'y', Math.min)));
    row.appendChild(mk('Bottom', () => alignTo(ids, 'y', Math.max)));
    body.appendChild(row);
    body.appendChild(h('h3', { class: 'sect', text: 'Danger' }));
    body.appendChild(h('button', {
      class: 'danger', text: `Delete ${ids.length} components`,
      onclick: () => removeSelection(),
    }));
    return;
  }

  const c = S.byId.get([...S.sel][0]);
  if (!c) { title.textContent = 'Nothing selected'; return; }
  const sp = spec(c);
  title.textContent = `#${c.id} ${sp.name}`;

  body.appendChild(kv('type', (c.bridge ? 'bridge ' : '') + c.type + ' — ' + sp.name));
  body.appendChild(kv('category', c.bridge ? 'bridge' : c.category));
  if (sp.description) {
    body.appendChild(h('div', {
      class: 'hint', text: sp.description,
    }));
  }

  body.appendChild(h('h3', { class: 'sect', text: 'Position' }));
  const pos = h('div', { class: 'row' });
  pos.style.display = 'flex'; pos.style.gap = '6px';
  const xi = h('input', { type: 'number', step: S.doc.grid, value: c.x });
  const yi = h('input', { type: 'number', step: S.doc.grid, value: c.y });
  const apply = () => edit([{
    op: 'move_component', id: c.id,
    x: parseFloat(xi.value) || 0, y: parseFloat(yi.value) || 0,
  }]);
  xi.addEventListener('change', apply);
  yi.addEventListener('change', apply);
  pos.appendChild(xi); pos.appendChild(yi);
  body.appendChild(pos);

  if (sp.properties && sp.properties.length) {
    body.appendChild(h('h3', { class: 'sect', text: 'Properties' }));
    for (const p of sp.properties) body.appendChild(propField(c, p));
  }

  body.appendChild(h('h3', { class: 'sect', text: 'Inputs' }));
  if (!c.in_fields.length) body.appendChild(h('div', { class: 'empty', text: 'no inputs' }));
  const ul = h('ul', { class: 'inslist' });
  c.in_fields.forEach((f, i) => {
    const info = sp.inputs[i] || {};
    const link = c.inputs[f];
    const li = h('li', {}, [
      h('span', { class: 'dt' }),
      h('span', { text: f }),
      h('span', { class: 'who', text: info.label || '' }),
    ]);
    li.querySelector('.dt').style.background = DT_COLOR[info.dt] || '#7c8798';
    if (link) {
      const a = h('span', { class: 'who link', text: '← #' + link.component_id });
      a.addEventListener('click', () => selectOnly(link.component_id, true));
      li.appendChild(a);
      const x = h('button', {
        class: 'linkish', text: '✕', title: 'disconnect',
        onclick: () => edit([{ op: 'disconnect', target: c.id, input: f }]),
      });
      li.appendChild(x);
    }
    ul.appendChild(li);
  });
  body.appendChild(ul);

  const feeds = S.doc.wires.filter((w) => w.from === c.id);
  body.appendChild(h('h3', { class: 'sect', text: `Feeds (${feeds.length})` }));
  if (!feeds.length) body.appendChild(h('div', { class: 'empty', text: 'nothing reads this' }));
  const fl = h('ul', { class: 'inslist' });
  for (const w of feeds) {
    const tgt = S.byId.get(w.to);
    const li = h('li', {}, [h('span', { text: `#${w.to} . ${w.field}` })]);
    const a = h('span', { class: 'who link', text: tgt ? spec(tgt).name : '?' });
    a.addEventListener('click', () => selectOnly(w.to, true));
    li.appendChild(a);
    fl.appendChild(li);
  }
  body.appendChild(fl);

  const pin = S.doc.io_pins.find((p) => p.component_id === c.id);
  if (c.bridge) {
    body.appendChild(h('h3', { class: 'sect', text: 'External pin' }));
    if (pin) {
      body.appendChild(kv('label', pin.label));
      body.appendChild(kv('face slot', `x ${pin.x}, z ${pin.z}`));
    } else {
      const nameIn = h('input', { type: 'text', placeholder: 'pin label' });
      body.appendChild(nameIn);
      body.appendChild(h('button', {
        text: 'Add pin on block face',
        onclick: async () => {
          if (!nameIn.value.trim()) return toast('give the pin a label', true);
          await tool('add_io_pin', { component_id: c.id, label: nameIn.value.trim() });
          toast('pin added');
        },
      }));
    }
  }

  body.appendChild(h('h3', { class: 'sect', text: 'Danger' }));
  const rewire = h('label', { class: 'check' }, []);
  const cb = h('input', { type: 'checkbox' });
  rewire.appendChild(cb);
  rewire.appendChild(document.createTextNode(' rewire consumers to this node’s first input'));
  body.appendChild(rewire);
  body.appendChild(h('button', {
    class: 'danger', text: 'Delete component',
    onclick: () => edit([{ op: 'remove_component', id: c.id, rewire: cb.checked }], 'deleted'),
  }));
}

function headerForm(body) {
  body.appendChild(h('h3', { class: 'sect', text: 'Microprocessor' }));
  const name = h('input', { type: 'text', value: S.doc.header.name || '' });
  name.addEventListener('change', () =>
    edit([{ op: 'set_header', name: name.value }], 'renamed'));
  body.appendChild(h('div', { class: 'field' }, [h('label', { text: 'name' }), name]));
  const desc = h('textarea', {});
  desc.value = S.doc.header.description || '';
  desc.addEventListener('change', () =>
    edit([{ op: 'set_header', description: desc.value }], 'description updated'));
  body.appendChild(h('div', { class: 'field' }, [h('label', { text: 'description' }), desc]));
  body.appendChild(kv('size', `${S.doc.header.width} × ${S.doc.header.length}`));
  body.appendChild(kv('components', S.doc.components.length));
  body.appendChild(kv('io pins', S.doc.io_pins.length));
  body.appendChild(h('div', { class: 'hint',
    text: 'Click a component to edit it. Drag from an output pin to an input pin to wire.' }));
}

function kv(k, v) {
  return h('div', { class: 'kv' }, [h('span', { text: k }), h('span', { text: String(v) })]);
}

/* Stormworks lets a number property hold a typed expression; keep the text and
 * evaluate it for the `value` the game caches alongside. */
function evalNum(text) {
  const t = String(text).trim();
  const direct = Number(t);
  if (t !== '' && Number.isFinite(direct)) return direct;
  if (!/^[-+*/(). 0-9epi]*$/i.test(t)) return 0;
  try {
    const v = Function('"use strict";const pi=Math.PI;const e=Math.E;return (' + t + ');')();
    return Number.isFinite(v) ? v : 0;
  } catch (_) { return 0; }
}

function propField(c, p) {
  const cur = c.properties[p.field];
  const wrap = h('div', { class: 'field' });
  const isBig = p.field === 'script' || (typeof cur === 'string' && cur.length > 60);
  wrap.appendChild(h('label', { text: `${p.field}  ·  ${p.kind.replace('attr_', '')}` }));

  const send = (value) =>
    edit([{ op: 'set_property', id: c.id, field: p.field, value }]);

  if (p.field === 'script') {
    const text = cur || '';
    const lines = text.split('\n');
    wrap.appendChild(h('button', {
      text: 'Edit in Lua view →',
      onclick: () => luaOpen(c.id),
    }));
    wrap.appendChild(h('pre', {
      class: 'scriptpeek',
      text: lines.slice(0, 4).join('\n') || '(empty script)',
    }));
    wrap.appendChild(h('div', {
      class: 'ty',
      text: text.length + ' chars · ' + lines.length + ' lines',
    }));
    return wrap;
  }

  if (p.kind === 'prop_num') {
    const txt = cur && typeof cur === 'object' ? cur.text : (cur == null ? '' : cur);
    const inp = h('input', { type: 'text', value: txt });
    const out = h('span', { class: 'ty' });
    const sync = () => { out.textContent = '= ' + evalNum(inp.value); };
    inp.addEventListener('input', sync);
    inp.addEventListener('change', () =>
      send({ text: inp.value, value: evalNum(inp.value) }));
    sync();
    const row = h('div', { class: 'row' }, [inp, out]);
    row.style.display = 'flex'; row.style.gap = '6px'; row.style.alignItems = 'center';
    wrap.appendChild(row);
  } else if (p.kind === 'attr_int' || p.kind === 'attr_float') {
    const inp = h('input', {
      type: 'number', step: p.kind === 'attr_int' ? 1 : 'any',
      value: cur == null ? '' : cur,
    });
    inp.addEventListener('change', () => {
      const v = p.kind === 'attr_int' ? parseInt(inp.value, 10) : parseFloat(inp.value);
      send(Number.isFinite(v) ? v : 0);
    });
    wrap.appendChild(inp);
  } else if (isBig) {
    const ta = h('textarea', {});
    ta.value = cur == null ? '' : cur;
    if (p.field === 'script') ta.style.minHeight = '220px';
    ta.addEventListener('change', () => send(ta.value));
    wrap.appendChild(ta);
  } else {
    const inp = h('input', { type: 'text', value: cur == null ? '' : cur });
    inp.addEventListener('change', () => send(inp.value));
    wrap.appendChild(inp);
  }
  return wrap;
}

function alignTo(ids, axis, pick) {
  const vals = ids.map((i) => S.byId.get(i)[axis]);
  const target = pick(...vals);
  edit(ids.map((i) => ({ op: 'move_component', id: i, [axis]: target })), 'aligned');
}

function selectOnly(id, centre) {
  S.sel.clear(); S.selWire = null; S.sel.add(id);
  render(); renderInspector(); renderStatus();
  if (centre) {
    const c = S.byId.get(id);
    if (!c) return;
    const r = $('canvas').getBoundingClientRect();
    const box = nodeBox(c);
    S.view.tx = r.width / 2 - (worldX(c.x) + box.w / 2) * S.view.s;
    S.view.ty = r.height / 2 - (worldY(c.y) + box.h / 2) * S.view.s;
    applyView();
  }
}

function removeSelection() {
  if (!S.sel.size) return;
  const ids = [...S.sel];
  S.sel.clear();
  edit(ids.map((id) => ({ op: 'remove_component', id })), `deleted ${ids.length}`);
}

// --------------------------------------------------------------------------
// canvas interaction
// --------------------------------------------------------------------------
function initCanvas() {
  const svg = $('canvas');

  svg.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const k = Math.exp(-ev.deltaY * 0.0015);
    const s2 = Math.min(6, Math.max(0.1, S.view.s * k));
    S.view.tx = mx - (mx - S.view.tx) * (s2 / S.view.s);
    S.view.ty = my - (my - S.view.ty) * (s2 / S.view.s);
    S.view.s = s2;
    applyView();
  }, { passive: false });

  svg.addEventListener('mousedown', (ev) => {
    svg.focus();
    const pinHit = ev.target.closest('[data-pin]');
    const nodeHit = ev.target.closest('.node');

    if (pinHit && nodeHit) {
      ev.preventDefault();
      return startLink(nodeHit, pinHit, ev);
    }
    if (nodeHit) {
      ev.preventDefault();
      const id = +nodeHit.dataset.id;
      if (ev.shiftKey || ev.ctrlKey) {
        S.sel.has(id) ? S.sel.delete(id) : S.sel.add(id);
      } else if (!S.sel.has(id)) {
        S.sel.clear(); S.sel.add(id);
      }
      S.selWire = null;
      render(); renderInspector(); renderStatus();
      return startDrag(ev);
    }
    if (ev.button === 1 || ev.altKey || ev.button === 2) return startPan(ev);
    if (ev.button === 0) {
      if (!ev.shiftKey) { S.sel.clear(); S.selWire = null; render(); renderInspector(); renderStatus(); }
      return startMarquee(ev);
    }
  });

  svg.addEventListener('contextmenu', (ev) => ev.preventDefault());

  svg.addEventListener('dblclick', (ev) => {
    const nodeHit = ev.target.closest('.node');
    if (!nodeHit) return;
    const c = S.byId.get(+nodeHit.dataset.id);
    if (c && c.type === 56) { ev.preventDefault(); luaOpen(c.id); }
  });

  svg.addEventListener('mousemove', (ev) => {
    const p = screenToWorld(ev);
    $('hudCursor').textContent = `${p.x.toFixed(2)}, ${p.y.toFixed(2)}`;
  });

  svg.addEventListener('dragover', (ev) => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'copy'; });
  svg.addEventListener('drop', (ev) => {
    ev.preventDefault();
    let data;
    try { data = JSON.parse(ev.dataTransfer.getData('text/plain')); } catch (_) { return; }
    addAt(data.type, data.bridge, screenToWorld(ev));
  });

  window.addEventListener('keydown', (ev) => {
    if (!$('view-lua').hidden) return;      // the Lua view owns the keyboard
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (typing) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') {
      ev.preventDefault();
      if (S.selWire) {
        const [to, field] = S.selWire.split(':');
        S.selWire = null;
        return edit([{ op: 'disconnect', target: +to, input: field }], 'wire removed');
      }
      return removeSelection();
    }
    if (ev.key === 'f' || ev.key === 'F') return fitView();
    if (ev.key === 'Escape') { S.sel.clear(); S.selWire = null; render(); renderInspector(); renderStatus(); }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'a') {
      ev.preventDefault();
      S.doc.components.forEach((c) => S.sel.add(c.id));
      render(); renderInspector(); renderStatus();
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z') {
      ev.preventDefault();
      tool(ev.shiftKey ? 'redo' : 'undo').catch((e) => toast(e.message, true));
    }
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') {
      ev.preventDefault();
      tool('save').then(() => toast('saved')).catch((e) => toast(e.message, true));
    }
  });
}

function startPan(ev) {
  const svg = $('canvas');
  svg.classList.add('panning');
  const x0 = ev.clientX, y0 = ev.clientY, t0 = { ...S.view };
  const move = (e) => {
    S.view.tx = t0.tx + (e.clientX - x0);
    S.view.ty = t0.ty + (e.clientY - y0);
    applyView();
  };
  const up = () => {
    svg.classList.remove('panning');
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

function startDrag(ev) {
  const start = screenToWorld(ev);
  const ids = [...S.sel];
  const origin = new Map(ids.map((i) => {
    const c = S.byId.get(i);
    return [i, { x: c.x, y: c.y }];
  }));
  ids.forEach((i) => {
    const g = $('layerNodes').querySelector(`[data-id="${i}"]`);
    if (g) g.classList.add('dragging');
  });
  let moved = false, dx = 0, dy = 0;

  const move = (e) => {
    const p = screenToWorld(e);
    dx = snap(p.x - start.x);
    dy = snap(p.y - start.y);
    if (dx || dy) moved = true;
    for (const i of ids) {
      const o = origin.get(i);
      const c = S.byId.get(i);
      c.x = o.x + dx; c.y = o.y + dy;
      const g = $('layerNodes').querySelector(`[data-id="${i}"]`);
      if (g) g.setAttribute('transform', `translate(${worldX(c.x)},${worldY(c.y)})`);
    }
    redrawWires();
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
    ids.forEach((i) => {
      const g = $('layerNodes').querySelector(`[data-id="${i}"]`);
      if (g) g.classList.remove('dragging');
    });
    if (!moved) return;
    edit([{ op: 'move_component', id: ids.length === 1 ? ids[0] : ids, dx, dy }]);
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

function redrawWires() {
  // Called on every drag frame: rebuild the wire layer only, and without the
  // per-wire hit areas and tooltips that full render() attaches.
  const wires = $('layerWires');
  wires.textContent = '';
  for (const w of S.doc.wires) {
    const src = S.byId.get(w.from), dst = S.byId.get(w.to);
    if (!src || !dst) continue;
    const dt = (spec(dst).inputs[w.index] || {}).dt;
    wires.appendChild(el('path', {
      class: 'wire', d: wirePath(pinPos(src, 'out', w.out), pinPos(dst, 'in', w.index)),
      stroke: DT_COLOR[dt] || '#7c8798',
    }));
  }
}

function startLink(nodeG, pinEl, ev) {
  const svg = $('canvas');
  svg.classList.add('linking');
  const id = +nodeG.dataset.id;
  const kind = pinEl.dataset.pin;
  const index = +pinEl.dataset.index;
  const c = S.byId.get(id);
  const anchor = pinPos(c, kind, index);

  // Dragging off a wired input detaches it and lets you re-aim the wire.
  let from = null;
  if (kind === 'in') {
    const field = c.in_fields[index];
    const link = c.inputs[field];
    if (link) from = { id: link.component_id, out: link.id };
  }

  const ghost = el('path', { class: 'wire ghost', d: '' });
  $('layerOverlay').appendChild(ghost);

  const move = (e) => {
    const p = screenToWorld(e);
    const tip = { x: worldX(p.x), y: worldY(p.y) };
    let a, b;
    if (kind === 'out') {
      a = anchor; b = tip;                       // output -> cursor
    } else if (from && S.byId.has(from.id)) {
      a = pinPos(S.byId.get(from.id), 'out', from.out);
      b = tip;                                   // detached: source stays put
    } else {
      a = tip; b = anchor;                       // cursor -> empty input
    }
    ghost.setAttribute('d', wirePath(a, b));
  };
  const up = (e) => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
    ghost.remove();
    svg.classList.remove('linking');

    const target = document.elementFromPoint(e.clientX, e.clientY);
    const pin2 = target && target.closest('[data-pin]');
    const node2 = target && target.closest('.node');
    if (!pin2 || !node2) {
      if (kind === 'in' && from) {
        edit([{ op: 'disconnect', target: id, input: c.in_fields[index] }], 'wire removed');
      }
      return;
    }
    const id2 = +node2.dataset.id;
    const kind2 = pin2.dataset.pin;
    const index2 = +pin2.dataset.index;

    if (kind === kind2) {
      // Dragging a wire off one input and onto another moves it.
      if (kind === 'in' && from) {
        const dst2 = S.byId.get(id2);
        if (!dst2) return;
        return edit([
          { op: 'disconnect', target: id, input: c.in_fields[index] },
          { op: 'connect', target: id2, input: dst2.in_fields[index2],
            source: from.id, source_output: from.out },
        ], 'wire moved');
      }
      return toast('connect an output to an input', true);
    }

    const [srcId, srcOut, dstId, dstIdx] = kind === 'out'
      ? [id, index, id2, index2]
      : [id2, index2, id, index];
    const dst = S.byId.get(dstId);
    edit([{
      op: 'connect', target: dstId, input: dst.in_fields[dstIdx],
      source: srcId, source_output: srcOut,
    }], 'connected');
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

function startMarquee(ev) {
  const start = screenToWorld(ev);
  const rect = el('rect', { class: 'marquee' });
  $('layerOverlay').appendChild(rect);
  const base = new Set(S.sel);
  const move = (e) => {
    const p = screenToWorld(e);
    const x0 = Math.min(worldX(start.x), worldX(p.x));
    const y0 = Math.min(worldY(start.y), worldY(p.y));
    const w = Math.abs(worldX(p.x) - worldX(start.x));
    const hgt = Math.abs(worldY(p.y) - worldY(start.y));
    rect.setAttribute('x', x0); rect.setAttribute('y', y0);
    rect.setAttribute('width', w); rect.setAttribute('height', hgt);
    S.sel = new Set(base);
    for (const c of S.doc.components) {
      const cx = worldX(c.x), cy = worldY(c.y), box = nodeBox(c);
      if (cx + box.w >= x0 && cx <= x0 + w && cy + box.h >= y0 && cy <= y0 + hgt) {
        S.sel.add(c.id);
      }
    }
    render(); renderStatus();
  };
  const up = () => {
    window.removeEventListener('mousemove', move);
    window.removeEventListener('mouseup', up);
    rect.remove();
    renderInspector();
  };
  window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
}

// --------------------------------------------------------------------------
// issues
// --------------------------------------------------------------------------
function renderIssues() {
  const box = $('issuesBody');
  box.textContent = '';
  const items = S.doc.issues;
  if (!items.length) {
    box.appendChild(h('div', { class: 'empty', text: 'No problems found.' }));
    return;
  }
  for (const i of items) {
    const row = h('div', { class: 'issue ' + i.level }, [
      h('span', { class: 'lvl', text: i.level }),
      h('span', { text: i.message }),
    ]);
    if (i.component) row.addEventListener('click', () => selectOnly(i.component, true));
    box.appendChild(row);
  }
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------
function initEvents() {
  let es;
  const connect = () => {
    es = new EventSource('/api/events');
    es.onopen = () => $('live').classList.add('on');
    es.addEventListener('changed', () => refresh().catch(() => {}));
    es.onerror = () => {
      $('live').classList.remove('on');
      es.close();
      setTimeout(connect, 1500);
    };
  };
  connect();
}

async function boot() {
  S.flipY = localStorage.getItem('swmc.flipY') === '1';
  S.snap = localStorage.getItem('swmc.snap') !== '0';
  S.roomy = localStorage.getItem('swmc.roomy') === '1';
  $('chkFlipY').checked = S.flipY;
  $('chkSnap').checked = S.snap;
  $('chkRoomy').checked = S.roomy;

  S.types = await api('/api/types');
  renderPalette();
  renderLegend();
  try {
    await refresh();
  } catch (e) {
    toast('no document open — start the server with --file', true);
    return;
  }
  fitView();
  initCanvas();
  initEvents();
  initLua();

  $('paletteSearch').addEventListener('input', renderPalette);
  $('btnFit').addEventListener('click', fitView);
  $('btnUndo').addEventListener('click', () => tool('undo').catch((e) => toast(e.message, true)));
  $('btnRedo').addEventListener('click', () => tool('redo').catch((e) => toast(e.message, true)));
  $('btnValidate').addEventListener('click', () => {
    $('issues').classList.toggle('hidden');
    if (!$('issues').classList.contains('hidden')) renderIssues();
  });
  $('btnCloseIssues').addEventListener('click', () => $('issues').classList.add('hidden'));
  $('chkFlipY').addEventListener('change', (e) => {
    S.flipY = e.target.checked;
    localStorage.setItem('swmc.flipY', S.flipY ? '1' : '0');
    render(); fitView();
  });
  $('chkSnap').addEventListener('change', (e) => {
    S.snap = e.target.checked;
    localStorage.setItem('swmc.snap', S.snap ? '1' : '0');
  });
  $('chkRoomy').addEventListener('change', (e) => {
    S.roomy = e.target.checked;
    localStorage.setItem('swmc.roomy', S.roomy ? '1' : '0');
    render(); fitView();
  });
  window.addEventListener('resize', applyView);
}

boot().catch((e) => { console.error(e); toast(String(e.message || e), true); });
