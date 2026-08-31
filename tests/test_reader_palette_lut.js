"use strict";

/* W-17: paridad de la LUT `Uint32` contra el camino de bytes.
 *
 * El criterio de cierre de W-17 es "salida byte-identica", y la unica forma de
 * verificarlo es hacer correr los DOS caminos sobre el mismo reader y el mismo
 * frame. El selector es el destino: un Uint8Array (o cualquier vista con
 * buffer alineado) toma el camino de palabra; un Array plano o una vista
 * desalineada caen al camino de bytes, que es el contrato con WebViews viejos.
 *
 * Cubre los dos readers y los tres perfiles: keyframe completo, delta con
 * celdas exactas (dirtyCellBits) y delta con tiles densos (dirtyTiles).
 */

var assert = require("assert");
var zlib = require("zlib");
var ASCLV2 = require("../frontend/reader-v2.js");
var ASCL = require("../frontend/reader.js");
var bench = require("../tools/bench_render.js");

function plainArray(length) {
  var out = [], i;
  for (i = 0; i < length; i++) out.push(0);
  return out;
}

function sameBytes(label, fast, slow, length) {
  var i;
  for (i = 0; i < length; i++) {
    if (fast[i] !== slow[i]) {
      assert.fail(label + ": byte " + i + " difiere (" + fast[i] + " vs " + slow[i] + ")");
    }
  }
}

/* --------------------------------------------------------------- ReaderV2 --- */

var kase = bench.buildCase(ASCLV2, { label: "128x80", cols: 128, rows: 80 });
var reader = kase.reader;
var total = reader.n * 4;
var fast = new Uint8Array(total);
var slow = plainArray(total);
var full = new Uint8Array(total);

reader.seek(0);
reader.fillRGBA(fast);
reader.fillRGBA(slow);
sameBytes("v2 keyframe", fast, slow, total);
assert.strictEqual(fast[3], 255, "el alfa debe quedar opaco");
assert.strictEqual(fast[total - 1], 255);

/* La LUT se construye por paleta, no por frame. */
assert.strictEqual(reader._paletteLut(), reader._paletteLut());

/* Una vista alineada con byteOffset distinto de cero sigue tomando el camino
 * de palabra; una desalineada tiene que caer al de bytes y dar lo mismo. */
var alignedHost = new ArrayBuffer(total + 8);
var aligned = new Uint8Array(alignedHost, 4, total);
var oddHost = new ArrayBuffer(total + 8);
var misaligned = new Uint8Array(oddHost, 1, total);
reader.fillRGBA(aligned);
reader.fillRGBA(misaligned);
sameBytes("v2 keyframe (offset 4)", aligned, slow, total);
sameBytes("v2 keyframe (offset 1)", misaligned, slow, total);

/* Delta disperso: celdas exactas. */
reader.seek(1);
assert(reader.dirtyCellCount > 0, "el perfil disperso debe marcar celdas exactas");
assert.strictEqual(reader.dirtyFull, false);
reader.fillRGBAChanged(fast);
reader.fillRGBAChanged(slow);
reader.fillRGBAChanged(misaligned);
reader.fillRGBA(full);
sameBytes("v2 sparse (palabra vs bytes)", fast, slow, total);
sameBytes("v2 sparse (desalineado)", misaligned, slow, total);
sameBytes("v2 sparse (incremental vs completo)", fast, full, total);

/* Delta de tiles densos: dirtyTiles. */
reader.seek(2);
assert(reader.dirtyCount > 0, "el perfil de tiles debe marcar tiles enteros");
reader.fillRGBAChanged(fast);
reader.fillRGBAChanged(slow);
reader.fillRGBA(full);
sameBytes("v2 tiles (palabra vs bytes)", fast, slow, total);
sameBytes("v2 tiles (incremental vs completo)", fast, full, total);

/* ---------------------------------------------------------------- ReaderV1 --- */

var TAG_RAW = 0, TAG_DELTA_MASK = 3;
var V1_COLS = 16, V1_ROWS = 4, V1_N = V1_COLS * V1_ROWS;

function v1Block(tag, palette, payload) {
  var pal = palette || Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length), out;
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  payload.copy(body, 3 + pal.length);
  out = Buffer.alloc(4 + body.length);
  out.writeUInt32LE(body.length, 0);
  body.copy(out, 4);
  return out;
}

function v1Ascl(frames) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i;
  header.write("ASCL", 0, "ascii");
  header[4] = 1;
  header[5] = 3;               /* modo PIXEL */
  header[6] = 12;              /* paleta global + tabla de offsets */
  header[7] = 15;              /* fps */
  header.writeUInt16LE(V1_COLS, 8);
  header.writeUInt16LE(V1_ROWS, 10);
  header.writeUInt16LE(4, 12); /* pal_size */
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;              /* cell_fmt PIXEL */
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  return Buffer.concat([header, table].concat(frames));
}

var v1Palette = Buffer.from([0, 0, 0, 85, 90, 95, 170, 12, 200, 255, 255, 255]);
var v1Cells = Buffer.alloc(V1_N), ci;
for (ci = 0; ci < V1_N; ci++) v1Cells[ci] = ci % 4;

/* Delta por mascara: celdas 5, 6 y 30 cambian. Los valores viajan en orden de
 * celda, uno por bit encendido. */
var v1Mask = Buffer.alloc(V1_N / 8);
v1Mask[0] = (1 << 5) | (1 << 6);
v1Mask[3] = 1 << 6;
var v1Delta = zlib.deflateSync(Buffer.concat([v1Mask, Buffer.from([1, 2, 3])]));

var v1File = v1Ascl([
  v1Block(TAG_RAW, v1Palette, v1Cells),
  v1Block(TAG_DELTA_MASK, null, v1Delta)
]);
var readerV1 = ASCL.parse(v1File.buffer, v1File.byteOffset, v1File.byteLength);
var totalV1 = readerV1.n * 4;
var fastV1 = new Uint8Array(totalV1);
var slowV1 = plainArray(totalV1);
var fullV1 = new Uint8Array(totalV1);

readerV1.seek(0);
readerV1.fillRGBA(fastV1);
readerV1.fillRGBA(slowV1);
sameBytes("v1 keyframe", fastV1, slowV1, totalV1);
assert.strictEqual(fastV1[4], 85, "la celda 1 debe tomar la segunda entrada de paleta");
assert.strictEqual(fastV1[5], 90);
assert.strictEqual(fastV1[6], 95);
assert.strictEqual(fastV1[7], 255);

readerV1.fillRGBARows(fastV1, 1, 2);
readerV1.fillRGBARows(slowV1, 1, 2);
sameBytes("v1 banda de filas", fastV1, slowV1, totalV1);

readerV1.seek(1);
assert.strictEqual(readerV1.dirtyFull, false, "un delta v1 no debe marcar el frame entero");
assert(readerV1.dirtyCellCount > 0);
readerV1.fillRGBAChanged(fastV1);
readerV1.fillRGBAChanged(slowV1);
readerV1.fillRGBA(fullV1);
sameBytes("v1 delta (palabra vs bytes)", fastV1, slowV1, totalV1);
sameBytes("v1 delta (incremental vs completo)", fastV1, fullV1, totalV1);

console.log("reader palette LUT tests: OK");
