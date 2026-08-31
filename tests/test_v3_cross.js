"use strict";
/* F6-3 (gate de cierre de S-4): round-trip Python/JavaScript byte-exacto.
 * El ReaderV2 debe decodificar un ASCLVID3 REAL del transcodificador Python
 * (con SPARSE diferencial adentro) exactamente igual que el decoder de
 * referencia. Los fixtures los genera tests/test_ascl_v2.py en
 * fixtures/v3-generated/; run_all.py corre Python antes que las suites JS. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var factory = require("../frontend/reader-factory.js");

var DIR = path.join(__dirname, "fixtures", "v3-generated");

if (!fs.existsSync(path.join(DIR, "clip.asclv"))) {
  console.log("SKIP v3-cross: fixtures no generados; " +
    "correr primero la suite Python (tests/run_all.py lo hace en orden)");
  process.exit(0);
}

var bundle = fs.readFileSync(path.join(DIR, "clip.asclv"));
var context = fs.readFileSync(path.join(DIR, "context.bin"));
var expected = fs.readFileSync(path.join(DIR, "expected.bin"));
var metaFile = fs.readFileSync(path.join(DIR, "meta.bin"));
var cols = context.readUInt16LE(0);
var rows = context.readUInt16LE(2);
var frames = context.readUInt32LE(4);

/* Envelope ASCLVID3: header de 20 bytes con meta_len (F6-3). */
assert.strictEqual(bundle.subarray(0, 8).toString("ascii"), "ASCLVID3");
var asclLen = bundle.readUInt32LE(8);
var audioLen = bundle.readUInt32LE(12);
var metaLen = bundle.readUInt32LE(16);
assert.strictEqual(20 + asclLen + audioLen + metaLen, bundle.length,
  "las tres longitudes del header v3 deben cubrir el archivo exacto");
assert(audioLen > 0, "el fixture lleva audio para ejercitar el orden de cargas");
assert.strictEqual(metaLen, metaFile.length);
assert.deepStrictEqual(
  Buffer.from(bundle.subarray(20 + asclLen + audioLen, bundle.length)),
  metaFile,
  "la meta embebida debe ser byte-identica al sidecar de origen");

var reader = factory.parse(bundle.buffer, bundle.byteOffset + 20, asclLen);
assert.strictEqual(reader.header.version, 3,
  "el interior de un ASCLVID3 debe declarar ASCL v3");
assert.strictEqual(reader.header.cols, cols);
assert.strictEqual(reader.header.rows, rows);
assert.strictEqual(reader.header.nFrames, frames);

var n = cols * rows, i;
assert.strictEqual(expected.length, n * frames);
for (i = 0; i < frames; i++) {
  reader.seek(i);
  assert.deepStrictEqual(Buffer.from(reader.cells),
    Buffer.from(expected.subarray(i * n, (i + 1) * n)),
    "frame " + i + " debe ser byte-identico a la referencia Python");
}

/* Seek hacia atras: re-decodifica la cadena desde el keyframe, mismo byte. */
reader.seek(1);
assert.deepStrictEqual(Buffer.from(reader.cells),
  Buffer.from(expected.subarray(n, 2 * n)));

console.log("v3 cross tests: OK (" + frames + " frames byte-identicos)");
