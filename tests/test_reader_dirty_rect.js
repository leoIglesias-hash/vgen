"use strict";
/* W-13: markRectDirty en ambos readers. La intervencion en vivo marca el rect
 * que escribio y el renderer repinta exactamente eso. */

var assert = require("assert");
var zlib = require("zlib");
var ASCL = require("../frontend/reader.js");
var ASCLV2 = require("../frontend/reader-v2.js");

var TAG_RAW = 0, TAG_MASK = 3, KEY_RAW = 4, DELTA_RAW = 6;
var SKIP = 0, SOLID = 1;

function b(value) { return Buffer.isBuffer(value) ? value : Buffer.from(value); }

function block(tag, palette, payload) {
  var pal = palette ? b(palette) : Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  b(payload).copy(body, 3 + pal.length);
  var result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function makeV1(frames, cols, rows) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i;
  header.write("ASCL", 0, "ascii");
  header[4] = 1;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(4, 12);
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  return Buffer.concat([header, table].concat(frames));
}

function makeV2(frames, cols, rows, palSize) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i, out;
  header.write("ASCL", 0, "ascii");
  header[4] = 2;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(palSize, 12);
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  header[26] = 16;
  header[27] = 1;
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  out = Buffer.concat([header, table].concat(frames));
  out.writeUInt32LE(ASCLV2.crc32v2(out), 28);
  return out;
}

function cellBit(reader, cell) {
  return (reader.dirtyCellBits[cell >>> 3] >>> (cell & 7)) & 1;
}

var paletteV1 = Buffer.from([0, 0, 0, 85, 85, 85, 170, 170, 170, 255, 255, 255]);

function paletteN(count) {
  var out = Buffer.alloc(count * 3), i;
  for (i = 0; i < count; i++) {
    out[i * 3] = i * 7;
    out[i * 3 + 1] = 255 - i * 5;
    out[i * 3 + 2] = i * 3;
  }
  return out;
}

/* ---------- ReaderV1 ---------- */
(function testV1MarkRectDirty() {
  var cols = 8, rows = 4, n = cols * rows, i;
  var key = Buffer.alloc(n);
  for (i = 0; i < n; i++) key[i] = i % 4;
  var frames = [
    block(TAG_RAW, paletteV1, key),
    block(TAG_MASK, null, zlib.deflateSync(Buffer.concat([
      Buffer.from([0x01, 0, 0, 0]), Buffer.from([1])])))
  ];
  var encoded = makeV1(frames, cols, rows);
  var reader = ASCL.parse(encoded.buffer, encoded.byteOffset, encoded.byteLength);

  reader.seek(0); /* consumir el keyframe para que seek(1) sea solo el delta */
  reader.seek(1);
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCellCount, 1);

  reader.markRectDirty(2, 1, 3, 2);
  assert.strictEqual(reader.dirtyCellCount, 7, "1 del delta + 6 del rect");
  var y, x;
  for (y = 1; y <= 2; y++) {
    for (x = 2; x <= 4; x++) {
      assert.strictEqual(cellBit(reader, y * cols + x), 1, "celda del rect marcada");
    }
  }
  assert.strictEqual(cellBit(reader, 1 * cols + 5), 0, "fuera del rect sin marcar");
  assert.strictEqual(reader.dirtyY0, 0);
  assert.strictEqual(reader.dirtyY1, 2);

  /* re-marcar el mismo rect no duplica el contador */
  reader.markRectDirty(2, 1, 3, 2);
  assert.strictEqual(reader.dirtyCellCount, 7);

  /* funcional: una escritura estilo overlay se repinta con fillRGBAChanged */
  reader.cells[1 * cols + 2] = 3;
  var out = new Uint8Array(n * 4);
  for (i = 0; i < out.length; i++) out[i] = 7;
  reader.fillRGBAChanged(out);
  var c = (1 * cols + 2) * 4;
  assert.deepStrictEqual([out[c], out[c + 1], out[c + 2], out[c + 3]],
    [255, 255, 255, 255], "celda del overlay repintada");
  c = (3 * cols + 7) * 4;
  assert.strictEqual(out[c], 7, "celda limpia intacta");

  [[-1, 0, 1, 1], [0, -1, 1, 1], [0, 0, 0, 1], [0, 0, 1, 0],
   [5, 0, 4, 1], [0, 3, 1, 2], [0.5, 0, 1, 1]].forEach(function (rect) {
    assert.throws(function () {
      reader.markRectDirty(rect[0], rect[1], rect[2], rect[3]);
    }, /rect dirty/);
  });

  /* con repintado completo pendiente es un no-op */
  var fresh = ASCL.parse(encoded.buffer, encoded.byteOffset, encoded.byteLength);
  fresh.seek(0);
  assert.strictEqual(fresh.dirtyFull, true);
  var countBefore = fresh.dirtyCellCount;
  fresh.markRectDirty(0, 0, 2, 2);
  assert.strictEqual(fresh.dirtyFull, true);
  assert.strictEqual(fresh.dirtyCellCount, countBefore);
}());

/* ---------- ReaderV2 ---------- */
(function testV2MarkRectDirty() {
  var cols = 32, rows = 32, i;
  var keyStream = Buffer.from([SOLID, 1, SOLID, 1, SOLID, 1, SOLID, 1]);
  var repeatStream = Buffer.from([SKIP, 4]);
  var encoded = makeV2([
    block(KEY_RAW, paletteN(32), keyStream),
    block(DELTA_RAW, null, repeatStream)
  ], cols, rows, 32);
  var reader = ASCLV2.parse(encoded.buffer, encoded.byteOffset, encoded.byteLength);

  reader.seek(0); /* consumir el keyframe para que seek(1) sea solo el delta */
  reader.seek(1);
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCount, 0);
  assert.strictEqual(reader.dirtyCellCount, 0);

  /* rect que cubre el tile 3 entero: se promueve a tile denso */
  reader.markRectDirty(16, 16, 16, 16);
  assert.strictEqual(reader.dirtyCount, 1);
  assert.strictEqual(reader.dirtyTiles[0], 3);
  assert.strictEqual(reader.dirtyCellCount, 0);
  assert.strictEqual(reader.dirtyY0, 16);
  assert.strictEqual(reader.dirtyY1, 31);

  /* rect parcial: celdas exactas */
  reader.markRectDirty(1, 1, 2, 2);
  assert.strictEqual(reader.dirtyCellCount, 4);
  assert.strictEqual(reader.dirtyCount, 1);
  assert.strictEqual(cellBit(reader, 1 * cols + 1), 1);
  assert.strictEqual(reader.dirtyY0, 1);

  /* dentro de un tile ya denso no se agregan bits exactos (disyuncion) */
  reader.markRectDirty(17, 17, 2, 2);
  assert.strictEqual(reader.dirtyCellCount, 4);
  assert.strictEqual(reader.dirtyCount, 1);

  /* promover el tile 0 limpia sus bits exactos previos */
  reader.markRectDirty(0, 0, 16, 16);
  assert.strictEqual(reader.dirtyCount, 2);
  assert.strictEqual(reader.dirtyCellCount, 0);
  assert.strictEqual(reader.dirtyY0, 0);

  /* rect que cruza tiles: exacto solo en el tile no denso */
  reader.markRectDirty(14, 0, 4, 1);
  assert.strictEqual(reader.dirtyCellCount, 2, "solo las celdas del tile 1");
  assert.strictEqual(cellBit(reader, 16), 1);
  assert.strictEqual(cellBit(reader, 17), 1);

  /* funcional: overlay + fillRGBAChanged repinta el tile denso y las exactas */
  reader.cells[16] = 5;
  reader.cells[17 * cols + 17] = 5;
  var out = new Uint8Array(cols * rows * 4);
  for (i = 0; i < out.length; i++) out[i] = 9;
  reader.fillRGBAChanged(out);
  var c = 16 * 4;
  assert.strictEqual(out[c], 35, "celda exacta repintada (5*7)");
  c = (17 * cols + 17) * 4;
  assert.strictEqual(out[c], 35, "celda del tile denso repintada");
  c = (5 * cols + 20) * 4; /* tile 1, sin marcar */
  assert.strictEqual(out[c], 9, "celda limpia intacta");

  [[-1, 0, 1, 1], [0, 0, 0, 1], [31, 0, 2, 1], [0, 31, 1, 2],
   [1.5, 0, 1, 1]].forEach(function (rect) {
    assert.throws(function () {
      reader.markRectDirty(rect[0], rect[1], rect[2], rect[3]);
    }, /rect dirty/);
  });

  /* con dirtyFull (keyframe recien decodificado) es un no-op */
  var fresh = ASCLV2.parse(encoded.buffer, encoded.byteOffset, encoded.byteLength);
  fresh.seek(0);
  assert.strictEqual(fresh.dirtyFull, true);
  fresh.markRectDirty(0, 0, 4, 4);
  assert.strictEqual(fresh.dirtyFull, true);
  assert.strictEqual(fresh.dirtyCellCount, 0);
  assert.strictEqual(fresh.dirtyCount, fresh.tileCount);
}());

console.log("OK test_reader_dirty_rect");
