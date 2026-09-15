/* The Lua script view: highlighting, completion and static checks.
 *
 * Layout: one outer element scrolls (#luaScroll) and the textarea never does.
 * The earlier arrangement let the textarea scroll and tried to keep a gutter
 * and a highlight layer in step with it; the gutter had no height cap, so it
 * stretched the grid row to the full document height and nothing ended up with
 * a scrollbar at all. Scrolling the container instead moves all three layers
 * together by construction, at the cost of having to bring the caret into view
 * ourselves -- which the completion popup needs the arithmetic for anyway.
 */
'use strict';

const LUA_KEYWORDS = new Set([
  'and', 'break', 'do', 'else', 'elseif', 'end', 'false', 'for', 'function',
  'goto', 'if', 'in', 'local', 'nil', 'not', 'or', 'repeat', 'return', 'then',
  'true', 'until', 'while',
]);
const LUA_STDLIB = new Set([
  'assert', 'error', 'getmetatable', 'ipairs', 'math', 'next', 'os', 'pairs',
  'pcall', 'rawget', 'rawset', 'select', 'setmetatable', 'string', 'table',
  'tonumber', 'tostring', 'type', 'unpack',
]);
const TAB_SIZE = 4;

const L = {
  id: null,
  dirty: false,
  timer: null,
  analysisTimer: null,
  lastSaved: '',
  tokens: [],
  issues: [],
  charW: 7.5,
  lineH: 19,
  padX: 16,
  padY: 12,
  ac: null,          // open completion popup state
};

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// --------------------------------------------------------------------------
// tokenizer -- one pass feeds highlighting, checks and completion
// --------------------------------------------------------------------------
function tokenizeLua(src) {
  const out = [];
  let i = 0;
  const n = src.length;
  const longBracket = (at) => {
    const m = /^\[(=*)\[/.exec(src.slice(at));
    if (!m) return -1;
    const close = ']' + m[1] + ']';
    const end = src.indexOf(close, at + m[0].length);
    return end < 0 ? n : end + close.length;
  };
  const push = (type, start, end, extra) =>
    out.push(Object.assign({ type, start, end, value: src.slice(start, end) }, extra));

  while (i < n) {
    const ch = src[i];
    if (ch === '-' && src[i + 1] === '-') {
      const long = longBracket(i + 2);
      let end = long > 0 ? long : src.indexOf('\n', i);
      if (end < 0) end = n;
      push('comment', i, end);
      i = end;
      continue;
    }
    if (ch === '[') {
      const long = longBracket(i);
      if (long > 0) { push('string', i, long, { closed: true }); i = long; continue; }
    }
    if (ch === '"' || ch === "'") {
      let j = i + 1;
      let closed = false;
      while (j < n) {
        if (src[j] === '\\') { j += 2; continue; }
        if (src[j] === '\n') break;
        if (src[j] === ch) { closed = true; j++; break; }
        j++;
      }
      push('string', i, j, { closed });
      i = j;
      continue;
    }
    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(src[i + 1] || ''))) {
      const m = /^(0[xX][0-9a-fA-F]+|[0-9]*\.?[0-9]+([eE][+-]?[0-9]+)?)/.exec(src.slice(i));
      if (m) { push('number', i, i + m[0].length); i += m[0].length; continue; }
    }
    if (/[A-Za-z_]/.test(ch)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
      push('name', i, i + m[0].length);
      i += m[0].length;
      continue;
    }
    if (/\s/.test(ch)) {
      let j = i;
      while (j < n && /\s/.test(src[j])) j++;
      push('space', i, j);
      i = j;
      continue;
    }
    push('op', i, i + 1);
    i++;
  }
  return out;
}

function highlightFromTokens(tokens, src) {
  let out = '';
  let last = 0;
  for (const t of tokens) {
    if (t.start > last) out += esc(src.slice(last, t.start));
    let cls = '';
    if (t.type === 'comment') cls = 'c';
    else if (t.type === 'string') cls = t.closed === false ? 's bad' : 's';
    else if (t.type === 'number') cls = 'n';
    else if (t.type === 'name') {
      if (LUA_KEYWORDS.has(t.value)) cls = 'k';
      else if (LUA_API_GLOBALS.includes(t.value)) cls = 'api';
      else if (LUA_API_CALLBACKS.includes(t.value)) cls = 'cb';
      else if (LUA_STDLIB.has(t.value)) cls = 'std';
      else if (/^\s*\(/.test(src.slice(t.end))) cls = 'f';
    }
    out += cls ? '<span class="' + cls + '">' + esc(t.value) + '</span>' : esc(t.value);
    last = t.end;
  }
  if (last < src.length) out += esc(src.slice(last));
  return out;
}

function highlightLua(src) {
  return highlightFromTokens(tokenizeLua(src), src);
}

// --------------------------------------------------------------------------
// analysis
//
// Syntax comes from luaparse (vendored, MIT) configured for Lua 5.3 -- the
// version Stormworks embeds. A real parser is the only way to catch things like
// a bare `a = `, which no amount of token counting can see.
//
// Everything on top of that is semantic and specific to this game: channel
// ranges, which callback a call sits in, and property labels checked against the
// components actually on this microprocessor.
// --------------------------------------------------------------------------

/** Globals a script may use without declaring them. */
const LUA_GLOBALS_OK = new Set([
  // Stormworks API
  'input', 'output', 'property', 'screen', 'map', 'async', 'debug',
  'onTick', 'onDraw', 'httpReply',
  // Lua 5.3 base library
  '_G', '_VERSION', 'assert', 'collectgarbage', 'coroutine', 'dofile', 'error',
  'getmetatable', 'io', 'ipairs', 'load', 'loadfile', 'math', 'next', 'os',
  'pairs', 'pcall', 'print', 'rawequal', 'rawget', 'rawlen', 'rawset',
  'require', 'select', 'setmetatable', 'string', 'table', 'tonumber',
  'tostring', 'type', 'utf8', 'xpcall', 'unpack', 'loadstring', 'self',
]);

/** Which property component type answers which property.get* call. */
const PROPERTY_GETTER = {
  19: 'getNumber',   // Property Slider
  20: 'getNumber',   // Property Dropdown
  33: 'getBool',     // Property Toggle
  34: 'getNumber',   // Property Number
  58: 'getText',     // Property Text
};

/** label -> {type, kind, getter} for every property component in the document. */
function propertyIndex() {
  if (!S.doc) return null;
  const out = new Map();
  for (const c of S.doc.components) {
    if (c.category !== 'property') continue;
    const p = c.properties || {};
    const label = typeof p.n === 'string' ? p.n
      : (typeof p.name === 'string' ? p.name : null);
    if (!label) continue;
    out.set(label, { id: c.id, type: c.type, name: c.name,
                     getter: PROPERTY_GETTER[c.type] || null });
  }
  return out;
}

/** Depth-first walk over every AST node. */
function walkAst(node, visit, parents) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const item of node) walkAst(item, visit, parents);
    return;
  }
  if (typeof node.type !== 'string') return;
  visit(node, parents);
  const next = parents.concat([node]);
  for (const key of Object.keys(node)) {
    if (key === 'loc' || key === 'range' || key === 'globals') continue;
    walkAst(node[key], visit, next);
  }
}

function parseLua(src) {
  if (typeof luaparse === 'undefined') return { ast: null, unavailable: true };
  try {
    return {
      ast: luaparse.parse(src, {
        luaVersion: '5.3', locations: true, ranges: true,
        scope: true, comments: false,
      }),
    };
  } catch (err) {
    return { ast: null, err };
  }
}

/** Strip luaparse's own "[line:col] " prefix; we show the location separately. */
function cleanParseMessage(err) {
  return String(err.message || 'syntax error').replace(/^\[\d+:\d+\]\s*/, '');
}

function analyzeLua(src) {
  const issues = [];
  if (!src.trim()) return issues;

  const push = (node, level, message) => {
    const loc = node && node.loc ? node.loc.start : { line: 1, column: 0 };
    issues.push({
      line: loc.line, column: loc.column, level, message,
      index: node && node.range ? node.range[0] : 0,
    });
  };

  const parsed = parseLua(src);
  if (parsed.unavailable) {
    return [{ line: 1, column: 0, level: 'warning', index: 0,
              message: 'the Lua parser did not load, so only the editor is available' }];
  }
  if (!parsed.ast) {
    const err = parsed.err;
    return [{
      line: err.line || 1, column: err.column || 0, level: 'error',
      index: typeof err.index === 'number' ? err.index : 0,
      message: cleanParseMessage(err),
    }];
  }
  const ast = parsed.ast;

  // Which callback body is a node inside? FunctionDeclaration nodes carry their
  // own range, so containment is a plain interval test.
  const callbacks = [];
  walkAst(ast, (node) => {
    if (node.type === 'FunctionDeclaration' && node.identifier
        && node.identifier.type === 'Identifier'
        && LUA_API_CALLBACKS.includes(node.identifier.name)) {
      callbacks.push({ name: node.identifier.name, range: node.range });
    }
  }, []);
  const callbackAt = (node) => {
    if (!node.range) return null;
    let found = null;
    for (const cb of callbacks) {
      if (node.range[0] >= cb.range[0] && node.range[1] <= cb.range[1]) found = cb.name;
    }
    return found;
  };

  const props = propertyIndex();
  const assignedGlobals = new Set();
  const definedNames = new Set();

  walkAst(ast, (node) => {
    if (node.type === 'AssignmentStatement') {
      for (const target of node.variables) {
        if (target.type === 'Identifier') assignedGlobals.add(target.name);
      }
    } else if (node.type === 'FunctionDeclaration' && node.identifier) {
      if (node.identifier.type === 'Identifier') {
        assignedGlobals.add(node.identifier.name);
        definedNames.add(node.identifier.name);
      }
    }
  }, []);

  walkAst(ast, (node) => {
    if (node.type !== 'MemberExpression' || node.indexer !== '.') return;
    if (!node.base || node.base.type !== 'Identifier') return;
    const obj = node.base.name;
    const member = node.identifier ? node.identifier.name : null;
    if (!member) return;
    const known = LUA_MEMBERS[obj];

    if (known && LUA_API_GLOBALS.includes(obj)
        && !known.some((m) => m.name === member)) {
      const close = known.map((m) => m.name)
        .filter((n) => n.toLowerCase().startsWith(member.slice(0, 3).toLowerCase()));
      push(node.identifier, 'warning',
           obj + '.' + member + ' is not part of the Stormworks API'
           + (close.length ? ' (did you mean ' + close.slice(0, 3).join(', ') + '?)' : ''));
    }

    const where = callbackAt(node);
    if (where === 'onTick' && obj === 'screen') {
      push(node, 'warning', 'screen.* does nothing in onTick; draw from onDraw');
    } else if (where === 'onDraw' && (obj === 'input' || obj === 'output')) {
      push(node, 'warning',
           obj + '.* does nothing in onDraw; read and write in onTick');
    }
  }, []);

  walkAst(ast, (node) => {
    if (node.type !== 'CallExpression') return;
    const base = node.base;
    if (!base || base.type !== 'MemberExpression' || base.indexer !== '.') return;
    if (!base.base || base.base.type !== 'Identifier') return;
    const obj = base.base.name;
    const member = base.identifier ? base.identifier.name : '';
    const args = node.arguments || [];

    if ((obj === 'input' || obj === 'output') && args.length) {
      const first = args[0];
      if (first.type === 'NumericLiteral') {
        const ch = first.value;
        if (!Number.isInteger(ch) || ch < 1 || ch > 32) {
          push(first, 'error',
               obj + '.' + member + ' channel ' + ch + ' is outside 1..32');
        }
      }
    }

    if (obj === 'property' && props && args.length) {
      const first = args[0];
      if (first.type === 'StringLiteral') {
        const label = first.value != null ? first.value
          : String(first.raw || '').slice(1, -1);
        const hit = props.get(label);
        if (!hit) {
          const names = [...props.keys()];
          push(first, 'warning',
               'no property component is labelled "' + label + '"'
               + (names.length ? ' (have: ' + names.join(', ') + ')'
                               : ' (this microprocessor has no property components)'));
        } else if (hit.getter && hit.getter !== member) {
          push(base.identifier, 'error',
               '"' + label + '" is a ' + hit.name + ', so use property.'
               + hit.getter + ' rather than property.' + member);
        }
      }
    }
  }, []);

  // Globals that are only ever read. An assigned global is ordinary Stormworks
  // style (scripts keep state in globals between ticks), so only reads count.
  const reported = new Set();
  for (const g of (ast.globals || [])) {
    if (assignedGlobals.has(g.name) || LUA_GLOBALS_OK.has(g.name)) continue;
    if (reported.has(g.name)) continue;
    reported.add(g.name);
    push(g, 'warning', "'" + g.name + "' is never assigned; is it a typo?");
  }

  if (!definedNames.has('onTick') && !definedNames.has('onDraw')) {
    issues.push({ line: 1, column: 0, level: 'warning', index: 0,
                  message: 'neither onTick nor onDraw is defined, so this script does nothing' });
  }

  issues.sort((a, b) => a.line - b.line || a.column - b.column);
  return issues;
}

// --------------------------------------------------------------------------
// geometry
// --------------------------------------------------------------------------
function measureMetrics() {
  const probe = h('span', { text: 'x'.repeat(100) });
  probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre';
  const hl = $('luaHl');
  hl.appendChild(probe);
  const w = probe.getBoundingClientRect().width / 100;
  probe.remove();
  if (w > 0) L.charW = w;
  const cs = getComputedStyle(hl);
  L.lineH = parseFloat(cs.lineHeight) || 19;
  L.padX = parseFloat(cs.paddingLeft) || 16;
  L.padY = parseFloat(cs.paddingTop) || 12;
}

/** 1-based line number containing `index`. */
function lineOf(src, index) {
  let line = 1;
  for (let i = 0; i < index && i < src.length; i++) if (src[i] === '\n') line++;
  return line;
}

/** Visual column of `index` within its line, honouring tab stops. */
function visualCol(src, index) {
  const start = src.lastIndexOf('\n', index - 1) + 1;
  let col = 0;
  for (let i = start; i < index; i++) {
    col = src[i] === '\t' ? col + (TAB_SIZE - (col % TAB_SIZE)) : col + 1;
  }
  return col;
}

function caretPixel(index) {
  const src = $('luaCode').value;
  const line = lineOf(src, index) - 1;
  return {
    x: L.padX + visualCol(src, index) * L.charW,
    y: L.padY + line * L.lineH,
    line,
  };
}

function scrollCaretIntoView() {
  const box = $('luaCode');
  const pane = $('luaScroll');
  const p = caretPixel(box.selectionStart);
  const gutterW = $('luaGutter').getBoundingClientRect().width;
  const viewW = pane.clientWidth - gutterW;
  if (p.y < pane.scrollTop + 8) pane.scrollTop = Math.max(0, p.y - 8);
  else if (p.y + L.lineH > pane.scrollTop + pane.clientHeight - 8) {
    pane.scrollTop = p.y + L.lineH - pane.clientHeight + 8;
  }
  const x = p.x;
  if (x < pane.scrollLeft + 8) pane.scrollLeft = Math.max(0, x - 40);
  else if (x > pane.scrollLeft + viewW - 24) pane.scrollLeft = x - viewW + 60;
}

// --------------------------------------------------------------------------
// view
// --------------------------------------------------------------------------
function luaComponents() {
  return (S.doc ? S.doc.components : []).filter((c) => c.type === 56);
}

function luaOpen(id) {
  const list = luaComponents();
  if (!list.length) { toast('this microprocessor has no Lua Script component', true); return; }
  const target = list.find((c) => c.id === id) || list[0];
  L.id = target.id;
  L.dirty = false;
  $('view-canvas').hidden = true;
  $('view-lua').hidden = false;
  renderLuaPicker();
  loadLuaSource(true);
  renderLuaApi();
  measureMetrics();
  paintLua();
  scheduleAnalysis(0);
  $('luaCode').focus();
}

function luaClose() {
  acClose();
  luaFlush();
  $('view-lua').hidden = true;
  $('view-canvas').hidden = false;
  applyView();
}

function renderLuaPicker() {
  const sel = $('luaPicker');
  const keep = sel.value;
  sel.textContent = '';
  for (const c of luaComponents()) {
    const o = h('option', { value: String(c.id) });
    o.textContent = '#' + c.id + (c.label ? ' — ' + c.label : '')
      + '   (' + c.x + ', ' + c.y + ')';
    sel.appendChild(o);
  }
  sel.value = String(L.id != null ? L.id : keep);
}

function loadLuaSource(force) {
  const c = S.byId.get(L.id);
  if (!c) { luaClose(); return; }
  const src = (c.properties && c.properties.script) || '';
  const box = $('luaCode');
  if (!force && L.dirty) return;        // never clobber what is being typed
  if (!force && box.value === src) return;
  box.value = src;
  L.lastSaved = src;
  L.dirty = false;
  paintLua();
}

function paintLua() {
  const box = $('luaCode');
  const src = box.value;
  L.tokens = tokenizeLua(src);
  $('luaHl').innerHTML = highlightFromTokens(L.tokens, src) + '\n';

  const lines = src.split('\n');
  const gutter = $('luaGutter');
  if (gutter.dataset.lines !== String(lines.length)) {
    gutter.dataset.lines = String(lines.length);
    let g = '';
    for (let i = 1; i <= lines.length; i++) g += i + '\n';
    gutter.textContent = g;
  }
  // The textarea must cover the highlight exactly, so it is sized to content
  // and the container does the scrolling.
  const longest = lines.reduce((m, l) => Math.max(m, visualCol(l, l.length)), 0);
  box.style.height = (lines.length * L.lineH + L.padY * 2) + 'px';
  box.style.width = Math.max(200, longest * L.charW + L.padX * 2 + 40) + 'px';

  renderLuaStats(src, lines.length);
}

function renderLuaStats(src, lineCount) {
  const errs = L.issues.filter((i) => i.level === 'error').length;
  const warns = L.issues.length - errs;
  $('luaStats').textContent = src.length + ' chars · ' + lineCount + ' lines'
    + (errs ? ' · ' + errs + ' error' + (errs > 1 ? 's' : '') : '')
    + (warns ? ' · ' + warns + ' warning' + (warns > 1 ? 's' : '') : '')
    + (L.dirty ? ' · unsaved' : '');
  $('luaStats').className = 'savestate' + (errs ? ' conflict' : (L.dirty ? ' dirty' : ''));
}

/**
 * Analysis is debounced separately from painting. Half-typed code is a syntax
 * error almost by definition, and re-reporting it on every keystroke makes the
 * Problems panel flicker; highlighting stays instant.
 */
function scheduleAnalysis(delay) {
  clearTimeout(L.analysisTimer);
  L.analysisTimer = setTimeout(() => {
    const src = $('luaCode').value;
    L.issues = analyzeLua(src);
    renderLuaIssues();
    renderLuaStats(src, src.split('\n').length);
  }, delay == null ? 350 : delay);
}

function renderLuaIssues() {
  const box = $('luaProblemList');
  box.textContent = '';
  if (!L.issues.length) {
    box.appendChild(h('div', { class: 'empty', text: 'No problems found.' }));
    $('luaProblems').dataset.count = '0';
    return;
  }
  $('luaProblems').dataset.count = String(L.issues.length);
  for (const it of L.issues) {
    const row = h('div', { class: 'issue ' + it.level }, [
      h('span', { class: 'lvl', text: it.level }),
      h('span', { class: 'ln', text: 'L' + it.line }),
      h('span', { text: it.message }),
    ]);
    row.addEventListener('click', () => gotoIndex(it.index));
    box.appendChild(row);
  }
}

function gotoIndex(index) {
  const box = $('luaCode');
  box.focus();
  box.setSelectionRange(index, index);
  scrollCaretIntoView();
}

function luaTouched() {
  L.dirty = true;
  paintLua();
  scheduleAnalysis();
  clearTimeout(L.timer);
  L.timer = setTimeout(luaFlush, 900);
}

async function luaFlush() {
  clearTimeout(L.timer);
  if (!L.dirty || L.id == null) return;
  const value = $('luaCode').value;
  if (value === L.lastSaved) { L.dirty = false; paintLua(); return; }
  try {
    await edit([{ op: 'set_property', id: L.id, field: 'script', value }]);
    L.lastSaved = value;
    L.dirty = false;
    paintLua();
  } catch (e) {
    // edit() already surfaced the error; keep the buffer so nothing is lost.
  }
}

/** Replace the selection, keeping the textarea's native undo stack intact. */
function insertAtCaret(text, selectFrom) {
  const box = $('luaCode');
  box.focus();
  const start = box.selectionStart;
  let ok = false;
  try { ok = document.execCommand('insertText', false, text); } catch (e) { ok = false; }
  if (!ok) {
    const s = box.selectionStart, e2 = box.selectionEnd;
    box.value = box.value.slice(0, s) + text + box.value.slice(e2);
    box.selectionStart = box.selectionEnd = s + text.length;
  }
  if (selectFrom != null) {
    box.setSelectionRange(start + selectFrom[0], start + selectFrom[1]);
  }
  luaTouched();
  scrollCaretIntoView();
}

// --------------------------------------------------------------------------
// completion
// --------------------------------------------------------------------------
function currentWord() {
  const box = $('luaCode');
  const src = box.value;
  const caret = box.selectionStart;
  let start = caret;
  while (start > 0 && /[A-Za-z0-9_]/.test(src[start - 1])) start--;
  const word = src.slice(start, caret);
  let obj = null;
  if (start > 0 && src[start - 1] === '.') {
    let os = start - 1;
    while (os > 0 && /[A-Za-z0-9_]/.test(src[os - 1])) os--;
    obj = src.slice(os, start - 1) || null;
  }
  return { word, start, caret, obj };
}

/** Identifiers already present in the buffer, so local names complete too. */
function bufferWords(exclude) {
  const seen = new Map();
  for (const t of L.tokens) {
    if (t.type !== 'name' || t.value === exclude) continue;
    if (LUA_KEYWORDS.has(t.value)) continue;
    seen.set(t.value, (seen.get(t.value) || 0) + 1);
  }
  return [...seen.keys()];
}

function completionsFor(ctx) {
  const pre = ctx.word.toLowerCase();
  const items = [];
  const add = (label, detail, doc, insert) => {
    if (pre && !label.toLowerCase().startsWith(pre)) return;
    items.push({ label, detail: detail || '', doc: doc || '', insert: insert || label });
  };

  if (ctx.obj) {
    for (const m of (LUA_MEMBERS[ctx.obj] || [])) {
      add(m.name, '(' + m.params + ')', m.doc,
          m.params ? m.name + '(' + m.params + ')' : m.name);
    }
    return items.slice(0, 40);
  }
  for (const g of LUA_API_GLOBALS) add(g, 'stormworks', 'API table');
  for (const cb of LUA_API_CALLBACKS) {
    add(cb, 'callback', 'Stormworks entry point', 'function ' + cb + '()\n\t\nend');
  }
  for (const k of LUA_KEYWORDS) add(k, 'keyword', '');
  for (const s of LUA_STDLIB) add(s, 'lua', '');
  for (const w of bufferWords(ctx.word)) add(w, 'in file', '');
  const seen = new Set();
  return items.filter((it) => !seen.has(it.label) && seen.add(it.label)).slice(0, 40);
}

function acOpen() {
  const ctx = currentWord();
  if (!ctx.obj && ctx.word.length < 2) return acClose();
  const items = completionsFor(ctx);
  if (!items.length) return acClose();
  L.ac = { ctx, items, index: 0 };
  acRender();
}

function acRender() {
  const pop = $('luaAc');
  pop.textContent = '';
  pop.hidden = false;
  L.ac.items.forEach((it, i) => {
    const row = h('div', { class: 'acitem' + (i === L.ac.index ? ' on' : '') }, [
      h('span', { class: 'aclabel', text: it.label }),
      h('span', { class: 'acdetail', text: it.detail }),
    ]);
    row.addEventListener('mousedown', (ev) => { ev.preventDefault(); acAccept(i); });
    pop.appendChild(row);
  });
  const doc = L.ac.items[L.ac.index].doc;
  if (doc) pop.appendChild(h('div', { class: 'acdoc', text: doc }));

  const p = caretPixel(L.ac.ctx.start);
  const pane = $('luaScroll');
  const gutterW = $('luaGutter').getBoundingClientRect().width;
  pop.style.left = Math.max(0, gutterW + p.x - pane.scrollLeft) + 'px';
  pop.style.top = (p.y + L.lineH - pane.scrollTop) + 'px';
  const room = pane.clientHeight - (p.y + L.lineH - pane.scrollTop);
  pop.style.maxHeight = Math.max(120, Math.min(260, room - 10)) + 'px';
}

function acMove(delta) {
  L.ac.index = (L.ac.index + delta + L.ac.items.length) % L.ac.items.length;
  acRender();
  const on = $('luaAc').querySelector('.acitem.on');
  if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest' });
}

function acAccept(index) {
  if (!L.ac) return;
  const it = L.ac.items[index == null ? L.ac.index : index];
  const box = $('luaCode');
  box.setSelectionRange(L.ac.ctx.start, L.ac.ctx.caret);
  const paren = it.insert.indexOf('(');
  const select = paren >= 0 && it.insert.endsWith(')') && it.insert.length > paren + 2
    ? [paren + 1, it.insert.length - 1]
    : null;
  acClose();
  insertAtCaret(it.insert, select);
}

function acClose() {
  L.ac = null;
  const pop = $('luaAc');
  if (pop) { pop.hidden = true; pop.textContent = ''; }
}

// --------------------------------------------------------------------------
// find
// --------------------------------------------------------------------------
function findRun(dir) {
  const needle = $('luaFindInput').value;
  const box = $('luaCode');
  const src = box.value;
  if (!needle) { $('luaFindCount').textContent = ''; return; }
  const hay = src.toLowerCase();
  const want = needle.toLowerCase();
  let total = 0;
  for (let i = hay.indexOf(want); i >= 0; i = hay.indexOf(want, i + 1)) total++;
  $('luaFindCount').textContent = total ? total + ' match' + (total > 1 ? 'es' : '') : 'no match';
  if (!total) return;
  let at;
  if (dir < 0) {
    at = hay.lastIndexOf(want, Math.max(0, box.selectionStart - 1));
    if (at < 0) at = hay.lastIndexOf(want);
  } else {
    at = hay.indexOf(want, box.selectionEnd);
    if (at < 0) at = hay.indexOf(want);
  }
  box.focus();
  box.setSelectionRange(at, at + needle.length);
  scrollCaretIntoView();
}

function findToggle(show) {
  const bar = $('luaFind');
  bar.hidden = show === false ? true : !bar.hidden;
  if (!bar.hidden) {
    const sel = $('luaCode').value.slice(
      $('luaCode').selectionStart, $('luaCode').selectionEnd);
    if (sel && !sel.includes('\n')) $('luaFindInput').value = sel;
    $('luaFindInput').focus();
    $('luaFindInput').select();
    findRun(0);
  } else {
    $('luaCode').focus();
  }
}

// --------------------------------------------------------------------------
// editing behaviour
// --------------------------------------------------------------------------
const BLOCK_OPEN = /(^|[^\w])(function|then|do|else|repeat)\s*$|[({]\s*$/;

function toggleComment() {
  const box = $('luaCode');
  const src = box.value;
  const from = src.lastIndexOf('\n', box.selectionStart - 1) + 1;
  let to = src.indexOf('\n', box.selectionEnd);
  if (to < 0) to = src.length;
  const block = src.slice(from, to);
  const allCommented = block.split('\n').every((l) => !l.trim() || /^\s*--/.test(l));
  const next = block.split('\n').map((l) => {
    if (!l.trim()) return l;
    return allCommented ? l.replace(/^(\s*)--\s?/, '$1') : l.replace(/^(\s*)/, '$1-- ');
  }).join('\n');
  box.setSelectionRange(from, to);
  insertAtCaret(next);
  box.setSelectionRange(from, from + next.length);
}

function luaKeydown(ev) {
  const box = $('luaCode');

  if (L.ac) {
    if (ev.key === 'ArrowDown') { ev.preventDefault(); return acMove(1); }
    if (ev.key === 'ArrowUp') { ev.preventDefault(); return acMove(-1); }
    if (ev.key === 'Enter' || ev.key === 'Tab') { ev.preventDefault(); return acAccept(); }
    if (ev.key === 'Escape') { ev.preventDefault(); return acClose(); }
  }

  const val = box.value;
  const s = box.selectionStart, e = box.selectionEnd;
  const mod = ev.ctrlKey || ev.metaKey;

  if (mod && ev.key === ' ') { ev.preventDefault(); return acOpen(); }
  if (mod && ev.key.toLowerCase() === 'f') { ev.preventDefault(); return findToggle(); }
  if (mod && (ev.key === '/' || ev.key === '7')) { ev.preventDefault(); return toggleComment(); }
  if (mod && ev.key.toLowerCase() === 's') {
    ev.preventDefault();
    luaFlush().then(() => toast('script saved'));
    return;
  }
  if (ev.key === 'F3') { ev.preventDefault(); return findRun(ev.shiftKey ? -1 : 1); }

  if (ev.key === 'Tab') {
    ev.preventDefault();
    const lineStart = val.lastIndexOf('\n', s - 1) + 1;
    if (s !== e && val.slice(s, e).includes('\n')) {
      let endLine = val.indexOf('\n', e);
      if (endLine < 0) endLine = val.length;
      const block = val.slice(lineStart, endLine);
      const shifted = ev.shiftKey
        ? block.replace(/^[\t ]/gm, '')
        : block.replace(/^(?=.)/gm, '\t');
      box.setSelectionRange(lineStart, endLine);
      insertAtCaret(shifted);
      box.setSelectionRange(lineStart, lineStart + shifted.length);
      return;
    }
    if (ev.shiftKey) {
      if (/^[\t ]/.test(val.slice(lineStart))) {
        box.setSelectionRange(lineStart, lineStart + 1);
        insertAtCaret('');
      }
      return;
    }
    insertAtCaret('\t');
    return;
  }

  if (ev.key === 'Enter') {
    ev.preventDefault();
    const lineStart = val.lastIndexOf('\n', s - 1) + 1;
    const line = val.slice(lineStart, s);
    const indent = (/^[\t ]*/.exec(line) || [''])[0];
    const deeper = BLOCK_OPEN.test(line) ? '\t' : '';
    const after = val.slice(e, e + 4);
    if (deeper && /^\s*(end|until|\)|\})/.test(after)) {
      // put the closing token on its own line below the new one
      insertAtCaret('\n' + indent + '\t\n' + indent, [1 + indent.length + 1,
                                                      1 + indent.length + 1]);
      return;
    }
    insertAtCaret('\n' + indent + deeper);
    return;
  }

  if (ev.key === 'Escape') { ev.preventDefault(); luaClose(); }
}

function luaInput(ev) {
  luaTouched();
  if (ev && ev.inputType && ev.inputType.startsWith('delete')) { acClose(); return; }
  const ctx = currentWord();
  if (ctx.obj || ctx.word.length >= 2) acOpen(); else acClose();
}

function initLua() {
  const box = $('luaCode');
  box.addEventListener('input', luaInput);
  box.addEventListener('keydown', luaKeydown);
  box.addEventListener('blur', () => { acClose(); luaFlush(); });
  box.addEventListener('click', acClose);
  $('luaScroll').addEventListener('scroll', () => { if (L.ac) acRender(); });
  $('luaBack').addEventListener('click', luaClose);
  $('luaPicker').addEventListener('change', (ev) => {
    const next = Number(ev.target.value);
    luaFlush().then(() => luaOpen(next));
  });
  $('luaApiSearch').addEventListener('input', renderLuaApi);
  $('luaFindInput').addEventListener('input', () => findRun(0));
  $('luaFindInput').addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') { ev.preventDefault(); findRun(ev.shiftKey ? -1 : 1); }
    if (ev.key === 'Escape') { ev.preventDefault(); findToggle(false); }
  });
  $('luaFindNext').addEventListener('click', () => findRun(1));
  $('luaFindPrev').addEventListener('click', () => findRun(-1));
  $('luaFindClose').addEventListener('click', () => findToggle(false));
  $('btnLua').addEventListener('click', () => {
    const sel = [...S.sel].map((id) => S.byId.get(id)).find((c) => c && c.type === 56);
    luaOpen(sel ? sel.id : undefined);
  });
  window.addEventListener('resize', () => { if (!$('view-lua').hidden) measureMetrics(); });
}

// --------------------------------------------------------------------------
// api reference panel
// --------------------------------------------------------------------------
function renderLuaApi() {
  const box = $('luaApiList');
  const q = $('luaApiSearch').value.trim().toLowerCase();
  box.textContent = '';

  const snippets = LUA_SNIPPETS.filter((s) => !q || s.name.toLowerCase().includes(q));
  if (snippets.length) {
    const g = h('div', { class: 'pgroup' }, [h('h4', { text: 'snippets' })]);
    for (const s of snippets) {
      const row = h('div', { class: 'apiitem', title: 'insert this template' }, [
        h('span', { class: 'nm', text: s.name }),
      ]);
      row.addEventListener('click', () => insertAtCaret(s.body));
      g.appendChild(row);
    }
    box.appendChild(g);
  }

  for (const grp of LUA_API) {
    const items = grp.items.filter(
      (it) => !q || it.sig.toLowerCase().includes(q) || it.doc.toLowerCase().includes(q));
    if (!items.length) continue;
    const g = h('div', { class: 'pgroup' }, [h('h4', { text: grp.group })]);
    for (const it of items) {
      const row = h('div', { class: 'apiitem', title: it.doc }, [
        h('code', { text: it.sig }),
        h('small', { text: it.doc }),
      ]);
      row.addEventListener('click', () => insertAtCaret(it.insert));
      g.appendChild(row);
    }
    box.appendChild(g);
  }
  if (!box.children.length) box.appendChild(h('div', { class: 'empty', text: 'no match' }));
}
