"use strict";
/* INT-003-D (gate cruzado): el runtime JavaScript del overlay v2 produce,
 * frame a frame, exactamente los mismos bytes que la referencia Python
 * (backend/overlay_ref.py) sobre un clip REAL del encoder con reserved=32 y
 * un sidecar ASCLSLOT v2 (parches heterogeneos, campos de eleccion con
 * digitos de presencia, slots superpuestos con ventanas disjuntas).
 * Los fixtures los genera test_overlay_ref_v2.py en
 * fixtures/overlay-v2-generated/; run_all.py corre Python antes que JS. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var ASCL = require("../frontend/reader.js");
var SLOTS = require("../frontend/slots.js");
var OVERLAY = require("../frontend/overlay.js");

var DIR = path.join(__dirname, "fixtures", "overlay-v2-generated");

if (!fs.existsSync(path.join(DIR, "context.bin"))) {
  console.log("SKIP overlay-v2-cross: fixtures no generados; " +
    "correr primero la suite Python (tests/run_all.py lo hace en orden)");
  process.exit(0);
}

var context = fs.readFileSync(path.join(DIR, "context.bin"));
var COLS = context.readUInt16LE(0);
var ROWS = context.readUInt16LE(2);
var FRAMES = context.readUInt32LE(4);
var RESERVED32 = new Uint8Array(context.subarray(8, 8 + 96));
var clip = fs.readFileSync(path.join(DIR, "clip.ascl"));
var sidecar = new Uint8Array(fs.readFileSync(path.join(DIR, "valid.slots")));
var expected = fs.readFileSync(path.join(DIR, "expected.bin"));

var timeline = {};
fs.readFileSync(path.join(DIR, "timeline.txt"), "utf8").split("\n")
  .forEach(function (line) {
    if (!line) return;
    var parts = line.split(":");
    timeline[parseInt(parts[0], 10)] = parts[1];
  });

var reader = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
var ref = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
assert.strictEqual(reader.header.cols, COLS);
assert.strictEqual(reader.header.rows, ROWS);
assert.strictEqual(reader.header.nFrames, FRAMES);
assert.strictEqual(reader.header.palSize, 256, "reserva en 224..255");

/* la cola reservada de 32 del bundle real coincide con la del sidecar
 * (INV-4 parametrico) */
var i;
for (i = 0; i < 96; i++) {
  assert.strictEqual(reader.palette[224 * 3 + i], RESERVED32[i],
    "reserved_rgb del bundle en el byte " + i);
}

var meta = SLOTS.ASCL_parseSlots(sidecar, COLS, ROWS, FRAMES, RESERVED32);
assert.strictEqual(meta.version, 2);
var overlay = OVERLAY.attach(reader, meta);
assert.ok(overlay, "attach v2 sobre el clip real del encoder");
assert.strictEqual(overlay.digitCount, 8,
  "payload v2: 2 digitos + 3 campos de eleccion de 1+1");

var n = COLS * ROWS, f;
for (f = 0; f < FRAMES; f++) {
  if (timeline[f] !== undefined) {
    assert.strictEqual(overlay.setValues(timeline[f]), true,
      "carga del frame " + f);
  }
  overlay.beforeSeek();
  reader.seek(f);
  overlay.afterSeek();
  assert.strictEqual(
    Buffer.compare(Buffer.from(reader.cells),
      expected.subarray(f * n, (f + 1) * n)), 0,
    "frame " + f + " byte-identico a la referencia Python");
}

/* clear(): la matriz vuelve, byte a byte, a la reproduccion sin overlay */
overlay.clear();
ref.seek(FRAMES - 1);
assert.strictEqual(
  Buffer.compare(Buffer.from(reader.cells), Buffer.from(ref.cells)), 0,
  "clear byte-identico al video base");

console.log("OK test_overlay_v2_cross: " + FRAMES +
  " frames byte-identicos Python/JS (reserved=32, sidecar v2)");
