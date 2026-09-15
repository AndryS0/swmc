/* Stormworks microcontroller Lua API reference.
 *
 * Compiled from the Japanese community wiki, https://wikiwiki.jp/sbarjp/
 * (「Luaスクリプト」 and 「Lua例文集」), which documents the in-game API more
 * completely than the official tooltips do.
 *
 * `sig` is shown in the list, `insert` is what lands at the caret when clicked
 * (${...} placeholders are stripped; the first one is selected afterwards).
 */
'use strict';

const LUA_API = [
  {
    group: 'Callbacks',
    items: [
      { sig: 'onTick()',
        insert: 'function onTick()\n\t\nend\n',
        doc: 'Runs once per logic tick (60/s). Composite input and output live '
           + 'here. screen.* calls do nothing in onTick.' },
      { sig: 'onDraw()',
        insert: 'function onDraw()\n\t\nend\n',
        doc: 'Runs when a monitor draws this script, once per connected monitor. '
           + 'input/output do nothing in onDraw.' },
      { sig: 'httpReply(port, request, response)',
        insert: 'function httpReply(port, request, response)\n\t\nend\n',
        doc: 'Called when an async.httpGet comes back.' },
    ],
  },
  {
    group: 'Composite input',
    items: [
      { sig: 'input.getNumber(index)', insert: 'input.getNumber(1)',
        doc: 'Number on composite channel 1-32.' },
      { sig: 'input.getBool(index)', insert: 'input.getBool(1)',
        doc: 'On/off on composite channel 1-32.' },
    ],
  },
  {
    group: 'Composite output',
    items: [
      { sig: 'output.setNumber(index, value)', insert: 'output.setNumber(1, 0)',
        doc: 'Write a number to composite channel 1-32.' },
      { sig: 'output.setBool(index, value)', insert: 'output.setBool(1, false)',
        doc: 'Write an on/off to composite channel 1-32.' },
    ],
  },
  {
    group: 'Properties',
    items: [
      { sig: 'property.getNumber(label)', insert: "property.getNumber('label')",
        doc: 'Value of a Property Number/Slider/Dropdown with this label.' },
      { sig: 'property.getBool(label)', insert: "property.getBool('label')",
        doc: 'Value of a Property Toggle with this label.' },
      { sig: 'property.getText(label)', insert: "property.getText('label')",
        doc: 'Value of a Property Text with this label.' },
    ],
  },
  {
    group: 'Screen — state',
    items: [
      { sig: 'screen.setColor(r, g, b [, a])', insert: 'screen.setColor(255, 255, 255)',
        doc: 'Draw colour, each channel 0-255. Alpha is optional.' },
      { sig: 'screen.getWidth()', insert: 'screen.getWidth()',
        doc: 'Monitor width in pixels.' },
      { sig: 'screen.getHeight()', insert: 'screen.getHeight()',
        doc: 'Monitor height in pixels.' },
    ],
  },
  {
    group: 'Screen — shapes',
    items: [
      { sig: 'screen.drawClear()', insert: 'screen.drawClear()',
        doc: 'Fill the whole screen with the current colour.' },
      { sig: 'screen.drawLine(x1, y1, x2, y2)', insert: 'screen.drawLine(0, 0, 32, 32)',
        doc: 'Line between two points.' },
      { sig: 'screen.drawRect(x, y, w, h)', insert: 'screen.drawRect(0, 0, 16, 16)',
        doc: 'Rectangle outline.' },
      { sig: 'screen.drawRectF(x, y, w, h)', insert: 'screen.drawRectF(0, 0, 16, 16)',
        doc: 'Filled rectangle.' },
      { sig: 'screen.drawCircle(x, y, r)', insert: 'screen.drawCircle(16, 16, 8)',
        doc: 'Circle outline.' },
      { sig: 'screen.drawCircleF(x, y, r)', insert: 'screen.drawCircleF(16, 16, 8)',
        doc: 'Filled circle.' },
      { sig: 'screen.drawTriangle(x1, y1, x2, y2, x3, y3)',
        insert: 'screen.drawTriangle(0, 0, 16, 0, 8, 12)',
        doc: 'Triangle outline.' },
      { sig: 'screen.drawTriangleF(x1, y1, x2, y2, x3, y3)',
        insert: 'screen.drawTriangleF(0, 0, 16, 0, 8, 12)',
        doc: 'Filled triangle.' },
    ],
  },
  {
    group: 'Screen — text',
    items: [
      { sig: 'screen.drawText(x, y, text)', insert: "screen.drawText(1, 1, 'text')",
        doc: 'Each glyph is 4px wide and 5px tall, so allow 5px per character.' },
      { sig: 'screen.drawTextBox(x, y, w, h, text, h_align, v_align)',
        insert: "screen.drawTextBox(1, 1, 30, 20, 'text', 0, 0)",
        doc: 'Word-wrapped text in a box. Alignment runs -1 (start), 0 (centre), '
           + '1 (end).' },
    ],
  },
  {
    group: 'Screen — map',
    items: [
      { sig: 'screen.drawMap(x, y, zoom)', insert: 'screen.drawMap(0, 0, 1)',
        doc: 'World map centred on world x,y. Zoom runs 0.1 to 50.' },
      { sig: 'screen.setMapColorOcean(r, g, b, a)',
        insert: 'screen.setMapColorOcean(0, 0, 60, 255)', doc: 'Ocean tint.' },
      { sig: 'screen.setMapColorShallows(r, g, b, a)',
        insert: 'screen.setMapColorShallows(0, 0, 90, 255)', doc: 'Shallow water tint.' },
      { sig: 'screen.setMapColorLand(r, g, b, a)',
        insert: 'screen.setMapColorLand(60, 60, 60, 255)', doc: 'Land tint.' },
      { sig: 'screen.setMapColorGrass(r, g, b, a)',
        insert: 'screen.setMapColorGrass(40, 70, 40, 255)', doc: 'Grass tint.' },
      { sig: 'screen.setMapColorSand(r, g, b, a)',
        insert: 'screen.setMapColorSand(90, 85, 60, 255)', doc: 'Sand tint.' },
      { sig: 'screen.setMapColorSnow(r, g, b, a)',
        insert: 'screen.setMapColorSnow(150, 150, 150, 255)', doc: 'Snow tint.' },
      { sig: 'screen.setMapColorRock(r, g, b, a)',
        insert: 'screen.setMapColorRock(70, 70, 70, 255)', doc: 'Rock tint.' },
      { sig: 'screen.setMapColorGravel(r, g, b, a)',
        insert: 'screen.setMapColorGravel(80, 80, 80, 255)', doc: 'Gravel tint.' },
    ],
  },
  {
    group: 'Map coordinates',
    items: [
      { sig: 'map.screenToMap(mapX, mapY, zoom, w, h, px, py)',
        insert: 'map.screenToMap(mapX, mapY, zoom, screen.getWidth(), screen.getHeight(), px, py)',
        doc: 'Pixel on the monitor to world coordinates. Returns worldX, worldY.' },
      { sig: 'map.mapToScreen(mapX, mapY, zoom, w, h, worldX, worldY)',
        insert: 'map.mapToScreen(mapX, mapY, zoom, screen.getWidth(), screen.getHeight(), worldX, worldY)',
        doc: 'World coordinates to a pixel on the monitor. Returns pixelX, pixelY.' },
    ],
  },
  {
    group: 'Async / debug',
    items: [
      { sig: 'async.httpGet(port, url)', insert: "async.httpGet(8080, '/')",
        doc: 'HTTP GET against localhost. One call per tick; the rest queue. '
           + 'The answer arrives in httpReply.' },
      { sig: 'debug.log(text)', insert: "debug.log('x')",
        doc: 'Writes to the Windows debug stream. Undocumented in game.' },
    ],
  },
];

/** Ready-made starting points. */
const LUA_SNIPPETS = [
  {
    name: 'Tick: add two inputs',
    body: 'function onTick()\n'
        + '\ta = input.getNumber(1)\n'
        + '\tb = input.getNumber(2)\n'
        + '\toutput.setNumber(1, a + b)\n'
        + 'end\n',
  },
  {
    name: 'Tick: short aliases (character golf)',
    body: 'i, o = input, output\n'
        + 'gn, gb, sn, sb = i.getNumber, i.getBool, o.setNumber, o.setBool\n\n'
        + 'function onTick()\n'
        + '\tsn(1, gn(1) + gn(2))\n'
        + 'end\n',
  },
  {
    name: 'Tick: rising-edge pulse',
    body: 'prev = false\n\n'
        + 'function onTick()\n'
        + '\tv = input.getBool(1)\n'
        + '\toutput.setBool(1, v and not prev)\n'
        + '\tprev = v\n'
        + 'end\n',
  },
  {
    name: 'Draw: clear and label',
    body: 'function onDraw()\n'
        + '\tw, h = screen.getWidth(), screen.getHeight()\n'
        + '\tscreen.setColor(0, 0, 0)\n'
        + '\tscreen.drawClear()\n'
        + '\tscreen.setColor(0, 255, 0)\n'
        + "\tscreen.drawTextBox(0, 0, w, h, 'hello', 0, 0)\n"
        + 'end\n',
  },
  {
    name: 'Draw: touchscreen input',
    body: '-- A monitor feeds its state in on composite:\n'
        + '-- numbers 1-2 resolution, 3-6 touch position; bools 1-2 touch state.\n'
        + 'function onTick()\n'
        + '\tw, h = input.getNumber(1), input.getNumber(2)\n'
        + '\ttx, ty = input.getNumber(3), input.getNumber(4)\n'
        + '\tpressed = input.getBool(1)\n'
        + 'end\n\n'
        + 'function onDraw()\n'
        + '\tif pressed then\n'
        + '\t\tscreen.setColor(255, 0, 0)\n'
        + '\t\tscreen.drawCircleF(tx, ty, 2)\n'
        + '\tend\n'
        + 'end\n',
  },
  {
    name: 'Properties',
    body: 'function onTick()\n'
        + "\tgain = property.getNumber('Gain')\n"
        + "\tenabled = property.getBool('Enabled')\n"
        + "\tlabel = property.getText('Label')\n"
        + '\toutput.setNumber(1, input.getNumber(1) * gain)\n'
        + 'end\n',
  },
];

/** Names the highlighter should treat as part of the game's API. */
const LUA_API_GLOBALS = ['input', 'output', 'property', 'screen', 'map', 'async', 'debug'];
const LUA_API_CALLBACKS = ['onTick', 'onDraw', 'httpReply'];

/* Members offered after a dot, for completion. Built from LUA_API above plus
 * the parts of the Lua standard library the game exposes. */
const LUA_MEMBERS = (() => {
  const out = {};
  for (const grp of LUA_API) {
    for (const it of grp.items) {
      const m = /^([A-Za-z_]\w*)\.(\w+)\s*\(([^)]*)\)/.exec(it.sig);
      if (!m) continue;
      (out[m[1]] = out[m[1]] || []).push({
        name: m[2], params: m[3], doc: it.doc, insert: it.insert,
      });
    }
  }
  return out;
})();

const LUA_STDLIB_MEMBERS = {
  math: [
    ['abs', 'x'], ['acos', 'x'], ['asin', 'x'], ['atan', 'x'],
    ['ceil', 'x'], ['cos', 'x'], ['exp', 'x'], ['floor', 'x'],
    ['fmod', 'x, y'], ['huge', ''], ['log', 'x'], ['max', 'x, ...'],
    ['min', 'x, ...'], ['pi', ''], ['random', 'm, n'], ['sin', 'x'],
    ['sqrt', 'x'], ['tan', 'x'],
  ],
  string: [
    ['byte', 's, i'], ['char', '...'], ['find', 's, pattern'],
    ['format', 'fmt, ...'], ['gmatch', 's, pattern'],
    ['gsub', 's, pattern, repl'], ['len', 's'], ['lower', 's'],
    ['match', 's, pattern'], ['rep', 's, n'], ['reverse', 's'],
    ['sub', 's, i, j'], ['upper', 's'],
  ],
  table: [
    ['concat', 't, sep'], ['insert', 't, value'], ['remove', 't, pos'],
    ['sort', 't, comp'], ['unpack', 't'],
  ],
};

for (const [obj, members] of Object.entries(LUA_STDLIB_MEMBERS)) {
  LUA_MEMBERS[obj] = members.map(([name, params]) => ({
    name, params, doc: 'Lua standard library',
    insert: obj + '.' + name + (params ? '(' + params + ')' : ''),
  }));
}
