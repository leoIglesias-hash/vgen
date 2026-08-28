"use strict";
/* F7-4 (gate de cierre de S-5): el runtime JavaScript del overlay produce,
 * frame a frame, exactamente los mismos bytes que la referencia Python
 * (backend/overlay_ref.py) sobre un clip REAL del encoder con reserved=10.
 * Los fixtures los genera test_overlay_ref.py en fixtures/overlay-generated/;
 * run_all.py corre Python antes que las suites JS. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var ASCL = require("../frontend/reader.js");
var SLOTS = require("../frontend/slots.js");
var OVERLAY = require("../frontend/overlay.js");

var DIR = path.join(__dirname, "fixtures", "overlay-generated");

if (!fs.existsSync(path.join(DIR, "context.bin"))) {
  console.log("SKIP overlay-cross: fixtures no generados; " +
    "correr primero la suite Python (tests/run_all.py lo hace en orden)");
  process.exit(0);
}

var context = fs.readFileSync(path.join(DIR, "context.bin"));
var COLS = context.readUInt16LE(0);
var ROWS = context.readUInt16LE(2);
var FRAMES = context.readUInt32LE(4);
var RESERVED_RGB = new Uint8Array(context.subarray(8, 38));
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
assert.strictEqual(reader.header.palSize, 256, "reserva en 246..255");

/* la cola reservada del bundle real coincide con la del sidecar (INV-4) */
var i;
for (i = 0; i < 30; i++) {
  assert.strictEqual(reader.palette[246 * 3 + i], RESERVED_RGB[i],
    "reserved_rgb del bundle en el byte " + i);
}

var meta = SLOTS.ASCL_parseSlots(sidecar, COLS, ROWS, FRAMES, RESERVED_RGB);
var overlay = OVERLAY.attach(reader, meta);
assert.ok(overlay, "attach sobre el clip real del encoder");

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

console.log("OK test_overlay_cross: " + FRAMES +
  " frames byte-identicos Python/JS");
