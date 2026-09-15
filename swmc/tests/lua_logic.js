/* Exercises the shipped lua.js highlighter against real Stormworks scripts.
 *
 *   node tests/lua_logic.js            (SWMC_SCRIPT may hold a real script)
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const S_DIR = path.join(__dirname, '..', 'swmc', 'static');
const read = (f) => fs.readFileSync(path.join(S_DIR, f), 'utf8');

function fakeNode(tag) {
  const n = {
    tagName: (tag || 'div').toUpperCase(), style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    children: [], attrs: {}, textContent: '', value: '', innerHTML: '',
    hidden: false, selectionStart: 0, selectionEnd: 0,
    setAttribute() {}, getAttribute() {}, appendChild(c) { return c; },
    remove() {}, addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; }, focus() {}, setSelectionRange() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 1200, height: 800 }; },
  };
  Object.defineProperty(n, 'className', { get() { return ''; }, set() {} });
  return n;
}

const ctx = vm.createContext({
  document: {
    getElementById: () => fakeNode(), createElement: (t) => fakeNode(t),
    createElementNS: (_n, t) => fakeNode(t), addEventListener() {},
    elementFromPoint: () => null, get activeElement() { return fakeNode(); },
    title: '', execCommand: () => false,
  },
  window: { addEventListener() {}, removeEventListener() {} },
  localStorage: { getItem: () => null, setItem() {} },
  fetch: () => Promise.reject(new Error('offline harness')),
  EventSource: function () { this.close = () => {}; },
  setTimeout: () => 0, clearTimeout: () => {},
  console, Math, JSON, Number, String, Object, Array, Map, Set, Function, Error,
  Infinity, NaN, isNaN, parseFloat, parseInt, RegExp, Boolean, Promise,
});

for (const f of ['vendor/luaparse.js', 'luaapi.js', 'app.js', 'lua.js']) {
  vm.runInContext(read(f), ctx, { filename: f });
}
const A = vm.runInContext(
  '({ highlightLua, tokenizeLua, analyzeLua, parseLua, completionsFor, visualCol,'
  + ' propertyIndex, LUA_API, LUA_SNIPPETS, LUA_API_GLOBALS, LUA_MEMBERS, L, S })', ctx);

let failures = 0;
function check(name, fn) {
  try { fn(); console.log('  ok   ' + name); }
  catch (e) { failures++; console.log('  FAIL ' + name + '\n       ' + e.message); }
}

const strip = (html) => html
  .replace(/<span class="[a-z ]+">/g, '').replace(/<\/span>/g, '')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

console.log('highlighter');
check('never loses or invents a character', () => {
  const samples = [
    'x = 1',
    'function onTick() output.setNumber(1, input.getNumber(1)) end',
    "s = 'it\\'s'  -- a comment with \"quotes\"",
    'a = b < c and d > e  -- < > & must survive escaping',
    'long = [[ multi\nline ]]',
    '--[[ block\ncomment ]] y = 2',
    'n = 0xFF + .5 + 1e-3',
  ];
  for (const src of samples) {
    assert.strictEqual(strip(A.highlightLua(src)), src,
      'round trip failed for: ' + JSON.stringify(src));
  }
});
check('escapes html so a script cannot break out', () => {
  const html = A.highlightLua('x = "</span><script>bad()</script>"');
  assert.ok(!/<script>/.test(html), 'raw <script> leaked into the highlight layer');
  assert.ok(html.includes('&lt;script&gt;'));
});
check('classifies keywords, api, callbacks, strings, numbers, comments', () => {
  const html = A.highlightLua(
    'function onTick()\n\tlocal v = input.getNumber(1) -- read\n\toutput.setBool(1, true)\nend');
  assert.ok(/<span class="k">function<\/span>/.test(html), 'function keyword');
  assert.ok(/<span class="cb">onTick<\/span>/.test(html), 'onTick callback');
  assert.ok(/<span class="api">input<\/span>/.test(html), 'input api');
  assert.ok(/<span class="api">output<\/span>/.test(html), 'output api');
  assert.ok(/<span class="k">local<\/span>/.test(html), 'local keyword');
  assert.ok(/<span class="n">1<\/span>/.test(html), 'number');
  assert.ok(/<span class="c">-- read<\/span>/.test(html), 'line comment');
});
check('a comment swallows code to end of line only', () => {
  const html = A.highlightLua('-- x = input.getNumber(1)\ny = 2');
  assert.ok(/<span class="c">-- x = input.getNumber\(1\)<\/span>/.test(html));
  assert.ok(/<span class="n">2<\/span>/.test(html), 'code after the comment still highlights');
});
check('an unterminated string does not run away', () => {
  const html = A.highlightLua("s = 'oops\nnext = 1");
  assert.strictEqual(strip(html), "s = 'oops\nnext = 1");
  assert.ok(/<span class="n">1<\/span>/.test(html), 'the next line still highlights');
  assert.ok(/class="s bad"/.test(html), 'and it is marked as broken');
});
check('handles an empty document', () => {
  assert.strictEqual(A.highlightLua(''), '');
});

console.log('api reference');
check('every entry has a signature, insert text and doc', () => {
  let count = 0;
  for (const g of A.LUA_API) {
    assert.ok(g.group, 'group needs a name');
    assert.ok(g.items.length, g.group + ' is empty');
    for (const it of g.items) {
      assert.ok(it.sig && it.insert && it.doc, 'incomplete entry: ' + JSON.stringify(it));
      count++;
    }
  }
  console.log('       (' + count + ' api entries)');
});
check('inserted text is syntactically plausible Lua', () => {
  for (const g of A.LUA_API) {
    for (const it of g.items) {
      const open = (it.insert.match(/\(/g) || []).length;
      const close = (it.insert.match(/\)/g) || []).length;
      assert.strictEqual(open, close, 'unbalanced parens in ' + it.sig);
    }
  }
});
check('snippets are balanced and highlight cleanly', () => {
  for (const s of A.LUA_SNIPPETS) {
    assert.ok(s.name && s.body, 'snippet needs a name and body');
    const fn = (s.body.match(/\bfunction\b/g) || []).length;
    const end = (s.body.match(/\bend\b/g) || []).length;
    assert.ok(end >= fn, s.name + ': more function than end');
    assert.strictEqual(strip(A.highlightLua(s.body)), s.body, s.name + ' round trip');
  }
});
check('api globals are the ones the highlighter colours', () => {
  const used = new Set();
  for (const g of A.LUA_API) {
    for (const it of g.items) {
      const m = /^([a-z]+)\./.exec(it.sig);
      if (m) used.add(m[1]);
    }
  }
  for (const name of used) {
    assert.ok(A.LUA_API_GLOBALS.includes(name),
      name + ' is used in the reference but not coloured by the highlighter');
  }
});

console.log('real script');
check('the sample microprocessor script survives a round trip', () => {
  const src = process.env.SWMC_SCRIPT;
  if (!src) { console.log('       (SWMC_SCRIPT not set, skipped)'); return; }
  assert.strictEqual(strip(A.highlightLua(src)), src);
  const html = A.highlightLua(src);
  assert.ok(html.includes('class="cb"'), 'expected a callback to be coloured');
  assert.ok(html.includes('class="api"'), 'expected an api global to be coloured');
  console.log('       (' + src.length + ' chars, ' + src.split('\n').length + ' lines)');
});

// --------------------------------------------------------------------------
console.log('parser');
const lint = (src) => A.analyzeLua(src);
const msgs = (src) => lint(src).map((i) => i.level + ': ' + i.message);
const has = (src, needle) => msgs(src).some((m) => m.includes(needle));
const errorsIn = (src) => lint(src).filter((i) => i.level === 'error');

check('luaparse loaded and is configured for Lua 5.3', () => {
  assert.ok(A.parseLua('x = 1').ast, 'parser should be available');
  // 5.3-only syntax must parse; if the version were wrong these would fail.
  for (const src of ['x = 7 // 2', 'x = 1 << 2 | 3 ~ 4', '::top:: goto top',
                     'x = 3 & 5', 'x = ~7']) {
    assert.ok(A.parseLua(src).ast, 'should parse as 5.3: ' + src);
  }
});
check('a bare assignment with no value is a syntax error', () => {
  const out = errorsIn('a = ');
  assert.strictEqual(out.length, 1);
  assert.ok(/<expression> expected/.test(out[0].message), out[0].message);
  assert.strictEqual(out[0].line, 1);
  assert.strictEqual(out[0].column, 4);
});
check('syntax errors carry a line, a column and an offset', () => {
  const out = errorsIn('function onTick()\n\tx = \nend\n');
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].line, 3);
  assert.ok(typeof out[0].column === 'number');
  assert.ok(out[0].index > 0);
});
check('the parser message loses its [line:col] prefix', () => {
  assert.ok(!/^\[\d+:\d+\]/.test(errorsIn('a = ')[0].message));
});
check('unclosed block', () => {
  assert.ok(has('function onTick()\n\tx = 1\n', 'end'));
});
check('mismatched bracket', () => {
  assert.ok(errorsIn('function onTick()\n\tx = (1 + 2]\nend').length > 0);
});
check('unterminated string', () => {
  assert.ok(errorsIn("x = 'oops\n").length > 0);
});
check('= where == was meant is caught', () => {
  assert.ok(errorsIn('function onTick()\n\tif a = b then end\nend').length > 0);
});
check('a call with a hole in its arguments is caught', () => {
  assert.ok(errorsIn('function onTick()\n\toutput.setNumber(1, )\nend').length > 0);
});
check('for/while ... do parses without complaint', () => {
  const src = 'function onTick()\n\tfor i = 1, 3 do x = i end\n'
            + '\twhile x > 0 do x = x - 1 end\n\trepeat x = 1 until x > 0\nend\n';
  assert.deepStrictEqual(Array.from(errorsIn(src)), []);
});
check('a clean script reports nothing at all', () => {
  const src = 'function onTick()\n\toutput.setNumber(1, input.getNumber(1))\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});
check('an empty script is not nagged about', () => {
  assert.deepStrictEqual(Array.from(msgs('')), []);
  assert.deepStrictEqual(Array.from(msgs('   \n')), []);
});

console.log('semantics');
check('channel outside 1..32', () => {
  assert.ok(has('function onTick() x = input.getNumber(33) end', 'outside 1..32'));
  assert.ok(has('function onTick() output.setBool(0, true) end', 'outside 1..32'));
  assert.ok(!has('function onTick() x = input.getNumber(32) end', 'outside 1..32'));
});
check('drawing from onTick is flagged', () => {
  assert.ok(has('function onTick()\n\tscreen.drawClear()\nend', 'does nothing in onTick'));
});
check('io from onDraw is flagged', () => {
  assert.ok(has('function onDraw()\n\tx = input.getNumber(1)\nend', 'does nothing in onDraw'));
});
check('the same calls are fine in the right callback', () => {
  const src = 'function onTick()\n\tx = input.getNumber(1)\nend\n'
            + 'function onDraw()\n\tscreen.drawClear()\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});
check('a helper called from onDraw is not mistaken for onTick', () => {
  const src = 'function paint()\n\tscreen.drawClear()\nend\n'
            + 'function onTick()\n\tx = input.getNumber(1)\nend\n'
            + 'function onDraw()\n\tpaint()\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});
check('a script with no entry point is flagged', () => {
  assert.ok(has('x = 1\n', 'does nothing'));
});
check('unknown api member, with a suggestion', () => {
  const m = msgs('function onTick() screen.drawSquare(1,1) end');
  assert.ok(m.some((x) => x.includes('not part of the Stormworks API')), m);
  assert.ok(m.some((x) => x.includes('did you mean')), m);
});
check('a typo global that is never assigned is flagged', () => {
  assert.ok(has('function onTick()\n\tx = outpout.getNumber(1)\nend', 'typo'));
});
check('globals the script assigns are not flagged', () => {
  const src = 'prev = false\nfunction onTick()\n\tv = input.getBool(1)\n'
            + '\toutput.setBool(1, v and not prev)\n\tprev = v\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});
check('locals and parameters are not flagged', () => {
  const src = 'function onTick()\n\tlocal a = 1\n\tfor i = 1, 3 do a = a + i end\n'
            + '\tlocal function f(p) return p * a end\n\toutput.setNumber(1, f(a))\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});
check('standard library use is not flagged', () => {
  const src = 'function onTick()\n\toutput.setNumber(1, math.floor(input.getNumber(1)))\n'
            + '\tlocal t = {}\n\ttable.insert(t, 1)\n\tlocal s = string.format("%d", #t)\nend\n';
  assert.deepStrictEqual(Array.from(msgs(src)), []);
});

console.log('property cross-check');
const DOC = { components: [
  { id: 1, category: 'property', type: 19, name: 'Property Slider',
    properties: { name: 'Gain' } },
  { id: 2, category: 'property', type: 33, name: 'Property Toggle',
    properties: { n: 'Enabled' } },
  { id: 3, category: 'property', type: 58, name: 'Property Text',
    properties: { n: 'Label' } },
  { id: 4, category: 'arithmetic', type: 6, properties: {} },
] };
check('the index picks up both n and name', () => {
  A.S.doc = DOC;
  const idx = A.propertyIndex();
  assert.deepStrictEqual(Array.from(idx.keys()).sort(), ['Enabled', 'Gain', 'Label']);
  A.S.doc = null;
});
check('a label that exists is accepted', () => {
  A.S.doc = DOC;
  assert.deepStrictEqual(
    Array.from(msgs("function onTick() g = property.getNumber('Gain') end")), []);
  A.S.doc = null;
});
check('a mistyped label is flagged and the real ones listed', () => {
  A.S.doc = DOC;
  const m = msgs("function onTick() g = property.getNumber('Gian') end");
  assert.ok(m.some((x) => x.includes('no property component is labelled')), m);
  assert.ok(m.some((x) => x.includes('Gain')), m);
  A.S.doc = null;
});
check('the wrong getter for the component type is an error', () => {
  A.S.doc = DOC;
  const m = msgs("function onTick() x = property.getNumber('Enabled') end");
  assert.ok(m.some((x) => x.includes('Property Toggle') && x.includes('getBool')), m);
  assert.deepStrictEqual(
    Array.from(msgs("function onTick() x = property.getBool('Enabled') end")), []);
  assert.deepStrictEqual(
    Array.from(msgs("function onTick() x = property.getText('Label') end")), []);
  A.S.doc = null;
});
check('the property check is skipped with no document loaded', () => {
  A.S.doc = null;
  assert.ok(!has("function onTick() g = property.getNumber('x') end", 'no property'));
});

console.log('the real script');
check('the sample script has no syntax errors', () => {
  const src = process.env.SWMC_SCRIPT;
  if (!src) { console.log('       (SWMC_SCRIPT not set, skipped)'); return; }
  const errs = errorsIn(src);
  assert.deepStrictEqual(
    Array.from(errs.map((e) => 'L' + e.line + ':' + e.column + ' ' + e.message)), [],
    'a script the game runs must not produce syntax errors');
  for (const w of lint(src)) {
    console.log('       L' + w.line + ' ' + w.level + ': ' + w.message);
  }
});
check('it does find the real typo in that script', () => {
  const src = process.env.SWMC_SCRIPT;
  if (!src || !/rpsOld,wsOld=rps,ws\b/.test(src)) {
    console.log('       (not the gyro sample, skipped)');
    return;
  }
  // Line 86 reads a bare `ws`; the script only ever assigns `wsT` and `wsOld`,
  // so `wsOld` is nil on every tick. A genuine latent bug in a published
  // microprocessor, and the reason this check earns its place.
  assert.ok(lint(src).some((i) => i.message.includes("'ws' is never assigned")),
            'expected the undefined-global check to catch ws');
});

console.log('completion');
check('members after a dot', () => {
  const names = A.completionsFor({ word: '', obj: 'input' }).map((i) => i.label);
  assert.deepStrictEqual(Array.from(names).sort(), ['getBool', 'getNumber']);
});
check('a prefix filters members', () => {
  const names = A.completionsFor({ word: 'draw', obj: 'screen' }).map((i) => i.label);
  assert.ok(names.length > 5);
  assert.ok(Array.from(names).every((n) => n.startsWith('draw')));
});
check('stdlib members are offered', () => {
  const names = Array.from(A.completionsFor({ word: '', obj: 'math' }).map((i) => i.label));
  assert.ok(names.includes('floor'));
  assert.ok(names.includes('pi'));
});
check('bare words offer globals and callbacks', () => {
  A.L.tokens = [];
  const names = Array.from(A.completionsFor({ word: 'on', obj: null }).map((i) => i.label));
  assert.ok(names.includes('onTick'));
  assert.ok(names.includes('onDraw'));
});
check('identifiers already in the buffer complete', () => {
  A.L.tokens = A.tokenizeLua('myHeading = 1\nmyHelper = 2');
  const names = Array.from(A.completionsFor({ word: 'myH', obj: null }).map((i) => i.label));
  assert.ok(names.includes('myHeading'));
  assert.ok(names.includes('myHelper'));
  A.L.tokens = [];
});
check('an unknown object offers nothing rather than throwing', () => {
  assert.strictEqual(A.completionsFor({ word: '', obj: 'nope' }).length, 0);
});
check('a completed call carries its parameter list', () => {
  const it = A.completionsFor({ word: 'getNum', obj: 'input' })[0];
  assert.strictEqual(it.insert, 'getNumber(index)');
});

console.log('tab stops');
check('visualCol honours tab size 4', () => {
  assert.strictEqual(A.visualCol('\tx', 2), 5);
  assert.strictEqual(A.visualCol('ab\tx', 4), 5);
  assert.strictEqual(A.visualCol('abcd\tx', 6), 9);
  assert.strictEqual(A.visualCol('no tabs here', 5), 5);
});

console.log(failures ? '\n' + failures + ' failure(s)' : '\nall lua checks passed');
process.exit(failures ? 1 : 0);
