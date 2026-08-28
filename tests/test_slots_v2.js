/*
 * INT-003-C: frontend/slots.js (parser v2) debe emitir el MISMO veredicto
 * que tools/make_slots.py sobre el corpus generado por test_make_slots_v2.py
 * en tests/fixtures/slots-v2-generated/ (mismos bytes, mismo mensaje).
 * run_all.py corre Python antes que las suites JS, asi que aca ya existen.
 */
"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var SLOTS = require("../frontend/slots.js");

var DIR = path.join(__dirname, "fixtures", "slots-v2-generated");

if (!fs.existsSync(path.join(DIR, "corpus.txt"))) {
  console.log("SKIP slots-v2: fixtures no generados; " +
    "correr primero la suite Python (tests/run_all.py lo hace en orden)");
  process.exit(0);
}

var context = fs.readFileSync(path.join(DIR, "context.bin"));
var COLS = context.readUInt16LE(0);
var ROWS = context.readUInt16LE(2);
var FRAMES = context.readUInt32LE(4);
var RESERVED32 = new Uint8Array(context.subarray(8, 8 + 96));

function parse(bytes, nFrames, expected) {
  return SLOTS.ASCL_parseSlots(bytes, COLS, ROWS, nFrames, expected);
}

var lines = fs.readFileSync(path.join(DIR, "corpus.txt"), "utf8").split("\n");
var rejected = 0, accepted = 0, i, k;
for (i = 0; i < lines.length; i++) {
  if (!lines[i]) continue;
  var tab = lines[i].indexOf("\t");
  var name = lines[i].substring(0, tab);
  var message = lines[i].substring(tab + 1);
  var bytes = new Uint8Array(fs.readFileSync(path.join(DIR, name + ".slots")));
  if (!message) {
    parse(bytes, FRAMES, RESERVED32);
    accepted++;
  } else {
    var thrown = null;
    try {
      parse(bytes, FRAMES, RESERVED32);
    } catch (error) {
      thrown = error;
    }
    assert.ok(thrown, name + " deberia rechazarse");
    assert.ok(thrown.message.indexOf(message) !== -1,
      name + ": \"" + thrown.message + "\" no contiene \"" + message + "\"");
    rejected++;
  }
}
assert.ok(accepted >= 3, "faltan fixtures validos en el corpus");
assert.ok(rejected >= 25, "faltan fixtures negativos en el corpus");

/* estructura del resultado sobre el fixture valido */
var valid = new Uint8Array(fs.readFileSync(path.join(DIR, "valid.slots")));
var meta = parse(valid, FRAMES, RESERVED32);
assert.strictEqual(meta.version, 2);
assert.strictEqual(meta.palReserved, 32);
assert.strictEqual(meta.reservedRgb.length, 96);
for (i = 0; i < 96; i++) {
  assert.strictEqual(meta.reservedRgb[i], RESERVED32[i]);
}
assert.strictEqual(meta.patches.length, 14);
assert.strictEqual(meta.patches[11].w, 6);
assert.strictEqual(meta.patches[11].h, 5);
for (k = 0; k < 30; k++) {
  assert.strictEqual(meta.patches[11].data[k], 0xe1);
}
assert.strictEqual(meta.slots.length, 5);
assert.deepStrictEqual(meta.slots[3],
  { x: 30, y: 10, w: 6, h: 5, start: 5, end: 9, flags: 1 });
assert.strictEqual(meta.fields.length, 4);
assert.strictEqual(meta.fields[0].kind, 0);
assert.strictEqual(meta.fields[0].pad, 1);
assert.strictEqual(meta.fields[0].patchBase, 0);
assert.deepStrictEqual(meta.fields[1],
  { fieldId: 2, kind: 1, slotIds: [2], min: 5, max: 7, pad: 0,
    patchBase: 11 });

/* sin n_frames declarado, una ventana mas alla del clip se acepta (espejo) */
var frames = new Uint8Array(
  fs.readFileSync(path.join(DIR, "bad-slot-frames.slots")));
parse(frames, null, RESERVED32);
var thrownFrames = null;
try {
  parse(frames, FRAMES, RESERVED32);
} catch (error) {
  thrownFrames = error;
}
assert.ok(thrownFrames, "bad-slot-frames deberia rechazarse con n_frames");

/* sin expectedReservedRgb la verificacion cruzada no aplica */
parse(new Uint8Array(fs.readFileSync(path.join(DIR, "bad-rgb.slots"))),
  FRAMES, null);

/* un sidecar v1 sigue parseando por la rama vieja (dispatch por version) */
var V1DIR = path.join(__dirname, "fixtures", "slots-generated");
if (fs.existsSync(path.join(V1DIR, "valid.slots"))) {
  var v1ctx = fs.readFileSync(path.join(V1DIR, "context.bin"));
  var v1 = SLOTS.ASCL_parseSlots(
    new Uint8Array(fs.readFileSync(path.join(V1DIR, "valid.slots"))),
    v1ctx.readUInt16LE(0), v1ctx.readUInt16LE(2), v1ctx.readUInt32LE(4),
    new Uint8Array(v1ctx.subarray(8, 38)));
  assert.strictEqual(v1.version, undefined);
  assert.ok(v1.glyphTable.length > 0);
}

console.log("OK slots-v2: " + accepted + " validos y " + rejected +
  " negativos con el mismo veredicto que el validador Python");
