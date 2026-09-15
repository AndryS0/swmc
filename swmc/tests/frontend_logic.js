/* Runs the real app.js inside a VM with a stub DOM and exercises its pure
 * logic. Not a substitute for clicking around in a browser, but it does run
 * the shipped code rather than a copy of it.
 *
 *   node tests/frontend_logic.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const SRC = fs.readFileSync(
  path.join(__dirname, '..', 'swmc', 'static', 'app.js'), 'utf8');

// ---- the smallest DOM that lets app.js finish loading --------------------
function fakeNode(tag) {
  const n = {
    tagName: (tag || 'div').toUpperCase(),
    style: {}, dataset: {}, classList: {
      add() {}, remove() {}, toggle() {}, contains() { return false; },
    },
    children: [], attrs: {}, textContent: '', value: '', checked: false,
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    appendChild(c) { this.children.push(c); return c; },
    removeChild(c) { return c; },
    remove() {},
    addEventListener() {}, removeEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
    closest() { return null; },
    focus() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 1200, height: 800 }; },
    insertBefore(c) { this.children.push(c); return c; },
  };
  Object.defineProperty(n, 'className', { get() { return ''; }, set() {} });
  return n;
}

const doc = {
  getElementById: () => fakeNode(),
  createElement: (t) => fakeNode(t),
  createElementNS: (_ns, t) => fakeNode(t),
  addEventListener() {},
  elementFromPoint: () => null,
  get activeElement() { return fakeNode('body'); },
  title: '',
};

const ctx = vm.createContext({
  document: doc,
  window: { addEventListener() {}, removeEventListener() {} },
  localStorage: { getItem: () => null, setItem() {} },
  fetch: () => Promise.reject(new Error('no network in this harness')),
  EventSource: function () { this.close = () => {}; },
  setTimeout: () => 0,
  clearTimeout: () => {},
  console,
  Math, JSON, Number, String, Object, Array, Map, Set, Function, Error,
  Infinity, NaN, isNaN, parseFloat, parseInt,
});

vm.runInContext(SRC, ctx, { filename: 'app.js' });

// `function` declarations land on the context object, but top-level `const`
// bindings live in the context's lexical scope -- reach them with a second
// evaluation in the same context.
const A = vm.runInContext(
  '({ S, snap, worldX, worldY, pinPos, wirePath, spec, evalNum,'
  + ' wrapLabel, layoutLabel, nodeBox, CHAR_W, LINE_H })', ctx);

let failures = 0;
function check(name, fn) {
  try { fn(); console.log('  ok   ' + name); }
  catch (e) { failures++; console.log('  FAIL ' + name + '\n       ' + e.message); }
}

// ---- evalNum: number properties may hold a typed expression --------------
console.log('evalNum');
check('plain number', () => assert.strictEqual(A.evalNum('2.5'), 2.5));
check('negative', () => assert.strictEqual(A.evalNum('-1.5'), -1.5));
check('empty is zero', () => assert.strictEqual(A.evalNum(''), 0));
check('fraction', () => assert.ok(Math.abs(A.evalNum('1/3') - 0.3333333) < 1e-6));
check('pi', () => assert.ok(Math.abs(A.evalNum('2*pi') - 6.2831853) < 1e-6));
check('parens', () => assert.strictEqual(A.evalNum('(1+2)*3'), 9));
check('words are rejected', () => assert.strictEqual(A.evalNum('abc'), 0));
check('no code execution', () => {
  assert.strictEqual(A.evalNum('fetch("/x")'), 0);
  assert.strictEqual(A.evalNum('this.constructor'), 0);
  assert.strictEqual(A.evalNum('[].map(x=>x)'), 0);
});
check('divide by zero is not Infinity', () => assert.strictEqual(A.evalNum('1/0'), 0));
check('nonsense arithmetic is zero', () => assert.strictEqual(A.evalNum('((('), 0));

// ---- geometry ------------------------------------------------------------
console.log('geometry');
const comp = {
  id: 1, x: 2, y: 3, w: 1.25, h: 0.5,
  in_fields: ['in1', 'in2'], n_out: 1, type: 1, bridge: false,
  inputs: {}, properties: {},
};
A.S.flipY = false;
A.S.doc = { grid: 0.25 };

check('input pins spread down the left edge', () => {
  const a = A.pinPos(comp, 'in', 0);
  const b = A.pinPos(comp, 'in', 1);
  assert.strictEqual(a.x, 2 * 48);
  assert.strictEqual(b.x, 2 * 48);
  assert.ok(b.y > a.y, 'second pin must sit below the first');
  assert.ok(a.y > 3 * 48 && b.y < 3 * 48 + 0.5 * 48, 'pins stay inside the box');
});
check('output pin sits on the right edge', () => {
  const o = A.pinPos(comp, 'out', 0);
  assert.strictEqual(o.x, 2 * 48 + 1.25 * 48);
});
check('flipY mirrors the y axis', () => {
  A.S.flipY = true;
  const f = A.pinPos(comp, 'in', 0);
  A.S.flipY = false;
  const n = A.pinPos(comp, 'in', 0);
  assert.notStrictEqual(f.y, n.y);
  assert.strictEqual(f.y - 0.125 * 48, -(3 * 48));
});
check('wirePath is a cubic bezier', () => {
  const d = A.wirePath({ x: 0, y: 0 }, { x: 100, y: 50 });
  assert.ok(/^M0,0 C[\d.]+,0 [\d.]+,50 100,50$/.test(d), d);
});
check('wirePath handles a backwards wire', () => {
  const d = A.wirePath({ x: 100, y: 0 }, { x: 0, y: 0 });
  assert.ok(d.startsWith('M100,0 C'), d);
  assert.ok(!/NaN/.test(d));
});

// ---- snapping ------------------------------------------------------------
console.log('snap');
check('snaps to the 0.25 grid', () => {
  A.S.snap = true;
  assert.strictEqual(A.snap(1.3), 1.25);
  assert.strictEqual(A.snap(-1.3), -1.25);
  assert.strictEqual(A.snap(0.12), 0);
});
check('free placement when snap is off', () => {
  A.S.snap = false;
  assert.strictEqual(A.snap(1.3333333), 1.333);
  A.S.snap = true;
});

// ---- label wrapping ------------------------------------------------------
console.log('labels');
check('wraps on word boundaries', () => {
  const r = A.wrapLabel('Composite Binary To Number', 10, 4);
  assert.deepStrictEqual(Array.from(r.lines), ['Composite', 'Binary To', 'Number']);
  assert.strictEqual(r.dropped, false);
  assert.strictEqual(r.hardBroken, false);
});
check('breaks after commas inside one word', () => {
  const r = A.wrapLabel('f(x,y,z,w,a,b,c,d)', 10, 4);
  assert.strictEqual(r.hardBroken, false, 'commas are break opportunities');
  assert.strictEqual(r.dropped, false);
  assert.strictEqual(r.lines.join(''), 'f(x,y,z,w,a,b,c,d)');
  assert.ok(r.lines.every((l) => l.length <= 10));
});
check('hard-breaks a word with nowhere to break', () => {
  const r = A.wrapLabel('Supercalifragilistic', 6, 4);
  assert.strictEqual(r.lines[0], 'Superc');
  assert.strictEqual(r.hardBroken, true);
});
check('respects the line budget and says it dropped text', () => {
  const r = A.wrapLabel('aaa bbb ccc ddd eee fff', 3, 2);
  assert.ok(r.lines.length <= 2);
  assert.strictEqual(r.dropped, true);
});
check('empty text yields no lines', () => {
  assert.strictEqual(A.wrapLabel('', 10, 3).lines.length, 0);
});

const LONG = 'Composite Binary To Number';
check('a long name fits whole in a default box', () => {
  // 1.25 x 0.5 grid units at 48 px/unit -> 60 x 24 px
  const lay = A.layoutLabel(LONG, 60, 24, [9, 8, 7, 6, 5.2]);
  assert.strictEqual(lay.complete, true,
    'expected the full name to fit, got ' + JSON.stringify(lay.lines));
  assert.strictEqual(lay.lines.join(' '), LONG);
  assert.ok(lay.lines.length > 1, 'it has to wrap to fit');
});
check('picks the largest size that fits', () => {
  const short = A.layoutLabel('AND', 60, 24, [9, 8, 7, 6, 5.2]);
  assert.strictEqual(short.fs, 9);
  assert.strictEqual(short.lines.length, 1);
  const long = A.layoutLabel(LONG, 60, 24, [9, 8, 7, 6, 5.2]);
  assert.ok(long.fs < 9, 'a long name must shrink');
});
check('every real component name fits a default box', () => {
  // test_frontend.py hands us all 60 names straight out of nodetypes.py.
  const names = process.env.SWMC_NAMES
    ? JSON.parse(process.env.SWMC_NAMES)
    : ['NOT', 'Numerical Switchbox', 'f(x, y, z, w, a, b, c, d)',
       'Boolean f(x,y,z,w,a,b,c,d)', 'Composite Binary To Number'];
  const bad = names.filter(
    (n) => !A.layoutLabel(n, 60, 24, [9, 8, 7, 6, 5.2]).complete);
  assert.deepStrictEqual(Array.from(bad), [],
    bad.length + ' name(s) still truncate: ' + JSON.stringify(bad));
  console.log('       (checked ' + names.length + ' names)');
});
check('falls back to an ellipsis rather than overflowing', () => {
  const lay = A.layoutLabel('x'.repeat(400), 60, 24, [9, 8, 7, 6, 5.2]);
  assert.strictEqual(lay.complete, false);
  assert.ok(lay.lines[lay.lines.length - 1].endsWith('…'));
});

console.log('roomy mode');
check('compact mode keeps the game footprint', () => {
  A.S.roomy = false;
  const box = A.nodeBox(comp);
  assert.strictEqual(box.w, 1.25 * 48);
  assert.strictEqual(box.h, 0.5 * 48);
});
check('roomy mode widens the box and spreads positions', () => {
  A.S.roomy = true;
  const box = A.nodeBox(comp);
  assert.ok(box.w > 1.25 * 48, 'box should widen');
  assert.strictEqual(A.worldX(2), 2 * 48 * 2, 'positions spread by 2x');
  const lay = A.layoutLabel(LONG, box.w, box.h, [10, 9, 8, 7]);
  assert.strictEqual(lay.complete, true);
  assert.ok(lay.fs >= 8, 'roomy mode should use a comfortable size');
  A.S.roomy = false;
  assert.strictEqual(A.worldX(2), 2 * 48, 'spread reverts');
});
check('roomy boxes still fit the spread gaps', () => {
  // The tightest real layout has columns 1.25 apart and rows 0.5 apart.
  A.S.roomy = true;
  const box = A.nodeBox(comp);
  assert.ok(box.w <= 1.25 * 48 * 2, 'a widened box must not reach the next column');
  assert.ok(box.h <= 0.5 * 48 * 2, 'a taller box must not reach the row below');
  A.S.roomy = false;
});

// ---- spec lookup ---------------------------------------------------------
console.log('spec');
A.S.types = {
  components: { 1: { name: 'AND', inputs: [{ dt: 0 }, { dt: 0 }], outputs: [{ dt: 0 }] } },
  bridge: { 3: { name: 'Number output', inputs: [{ dt: 1 }], outputs: [] } },
};
check('component types resolve', () => assert.strictEqual(A.spec(comp).name, 'AND'));
check('bridge types resolve from the bridge table', () => {
  assert.strictEqual(A.spec({ type: 3, bridge: true }).name, 'Number output');
});
check('unknown type degrades instead of throwing', () => {
  const s = A.spec({ type: 999, bridge: false });
  // deepStrictEqual would compare prototypes across VM realms, so check shape.
  assert.strictEqual(s.inputs.length, 0);
  assert.strictEqual(s.outputs.length, 0);
  assert.strictEqual(s.name, '?');
});

console.log(failures ? `\n${failures} failure(s)` : '\nall frontend logic checks passed');
process.exit(failures ? 1 : 0);
