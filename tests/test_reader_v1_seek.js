"use strict";
/* W-02 / W-03: atajo a keyframe hacia adelante y rollback transaccional
 * en ReaderV1, portados de ReaderV2. */

var assert = require("assert");
var zlib = require("zlib");
var ASCL = require("../frontend/reader.js");

var TAG_RAW = 0, TAG_ZLIB = 1, TAG_MASK = 3;

function asBuffer(value) {
  return Buffer.isBuffer(value) ? value : Buffer.from(value);
}

function block(tag, palette, payload) {
  var pal = palette ? asBuffer(palette) : Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  asBuffer(payload).copy(body, 3 + pal.length);
  var result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function makeAscl(frames, options) {
  options = options || {};
  var cols = options.cols || 4, rows = options.rows || 1;
  var dataOff = 32;
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = dataOff + table.length, i;
  header.write("ASCL", 0, "ascii");
  header[4] = 1;
  header[5] = 3;
  header[6] = 12; /* global + offsets */
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(4, 12);
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;
  header.writeUInt32LE(dataOff, 20);
  header.writeUInt16LE(1000, 24);
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  return Buffer.concat([header, table].concat(frames));
}

function parseBuffer(buf) {
  return ASCL.parse(buf.buffer, buf.byteOffset, buf.byteLength);
}

function maskPayload(maskBytes, values) {
  return zlib.deflateSync(Buffer.concat([asBuffer(maskBytes), asBuffer(values)]));
}

var palette = Buffer.from([0, 0, 0, 85, 85, 85, 170, 170, 170, 255, 255, 255]);

/* 8 frames, 4 celdas: keyframes en 0 y 4, deltas en el resto.
 * Cada MASK cambia la celda 0 al valor (i % 4). */
function buildClip(decodeLog) {
  var frames = [], i;
  for (i = 0; i < 8; i++) {
    if (i === 0) {
      frames.push(block(TAG_RAW, palette, Buffer.from([0, 1, 2, 3])));
    } else if (i === 4) {
      frames.push(block(TAG_ZLIB, null,
        zlib.deflateSync(Buffer.from([3, 2, 1, 0]))));
    } else {
      frames.push(block(TAG_MASK, null,
        maskPayload([0x01], [i % 4])));
    }
  }
  var reader = parseBuffer(makeAscl(frames));
  if (decodeLog) {
    var original = reader._decodeOne;
    reader._decodeOne = function (index) {
      decodeLog.push(index);
      return original.call(this, index);
    };
  }
  return reader;
}

(function testForwardKeyframeShortcut() {
  var log = [];
  var reader = buildClip(log);
  reader.seek(1);
  log.length = 0;
  reader.seek(7);
  /* Sin el atajo: decodifica 2..7 (6 frames). Con el atajo: 4..7 (4 frames). */
  assert.deepStrictEqual(log, [4, 5, 6, 7],
    "el seek hacia adelante debe reanudar en el keyframe 4, decodifico " + log.join(","));
  assert.strictEqual(reader.cells[0], 3 % 4);
  assert.strictEqual(reader.cells[1], 2);
  console.log("v1 forward keyframe shortcut: OK");
})();

(function testShortcutMatchesSlowPath() {
  /* La matriz final por el atajo debe ser identica a decodificar todo. */
  var fast = buildClip(null);
  fast.seek(1);
  fast.seek(7);
  var slow = buildClip(null);
  var i;
  for (i = 0; i <= 7; i++) slow.seek(i);
  for (i = 0; i < 4; i++) {
    assert.strictEqual(fast.cells[i], slow.cells[i], "celda " + i);
  }
  console.log("v1 shortcut equals slow path: OK");
})();

(function testSeekRollbackOnCorruptFrame() {
  /* Frame 6 corrupto: valor fuera de paleta. El seek(6) debe fallar y dejar
   * el reader en estado inicial consistente; un seek(1) posterior funciona. */
  var frames = [], i;
  for (i = 0; i < 8; i++) {
    if (i === 0) {
      frames.push(block(TAG_RAW, palette, Buffer.from([0, 1, 2, 3])));
    } else if (i === 6) {
      frames.push(block(TAG_MASK, null, maskPayload([0x01], [9])));
    } else {
      frames.push(block(TAG_MASK, null, maskPayload([0x01], [i % 4])));
    }
  }
  var reader = parseBuffer(makeAscl(frames));
  reader.seek(2);
  assert.throws(function () { reader.seek(6); });
  assert.strictEqual(reader.decodedIndex, -1,
    "el rollback debe invalidar decodedIndex");
  assert.strictEqual(reader.dirtyFull, false);
  reader.seek(1);
  assert.strictEqual(reader.cells[0], 1);
  assert.strictEqual(reader.decodedIndex, 1);
  console.log("v1 seek rollback: OK");
})();

console.log("reader v1 seek tests: OK");
