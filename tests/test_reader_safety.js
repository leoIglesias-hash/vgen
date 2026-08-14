"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var zlib = require("zlib");
var ASCL = require("../frontend/reader.js");
var inflate = require("../frontend/inflate.js");

var TAG_RAW = 0, TAG_ZLIB = 1, TAG_DELTA = 2, TAG_MASK = 3;

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
  var cols = options.cols || 5, rows = options.rows || 2;
  var paletteSize = options.paletteSize === undefined ? 4 : options.paletteSize;
  var dataOff = 32;
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = dataOff + table.length, i;
  header.write("ASCL", 0, "ascii");
  header[4] = options.version === undefined ? 1 : options.version;
  header[5] = options.mode === undefined ? 3 : options.mode;
  header[6] = options.flags === undefined ? 12 : options.flags; /* global + offsets */
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(paletteSize, 12);
  header.writeUInt32LE(frames.length, 14);
  header[18] = options.rampLen || 0;
  header[19] = options.cellFmt === undefined ? 3 : options.cellFmt;
  header.writeUInt32LE(options.dataOff === undefined ? dataOff : options.dataOff, 20);
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

function deltaPayload(offsets, values) {
  var raw = Buffer.alloc(offsets.length * 4 + values.length), i;
  for (i = 0; i < offsets.length; i++) raw.writeUInt32LE(offsets[i], i * 4);
  asBuffer(values).copy(raw, offsets.length * 4);
  return zlib.deflateSync(raw);
}

function expectError(fn, pattern) {
  assert.throws(fn, pattern);
}

(function testAllTagsSeekScratchAndRows() {
  var palette = Buffer.from([
    0, 0, 0, 80, 10, 20, 10, 160, 30, 240, 250, 255
  ]);
  var f0 = Buffer.from([0, 0, 1, 1, 2, 2, 3, 3, 0, 1]);
  var f1 = Buffer.from([1, 1, 1, 2, 2, 2, 3, 0, 0, 1]);
  var f2 = Buffer.from(f1); f2[1] = 3; f2[7] = 2;
  var f3 = Buffer.from(f2); f3[1] = 2; f3[9] = 3;
  var maskRaw = Buffer.from([2, 2, 2, 3]); /* bits 1 y 9, luego valores */
  var encoded = makeAscl([
    block(TAG_RAW, palette, f0),
    block(TAG_ZLIB, null, zlib.deflateSync(f1)),
    block(TAG_DELTA, null, deltaPayload([1, 7], [3, 2])),
    block(TAG_MASK, null, zlib.deflateSync(maskRaw))
  ]);
  var reader = parseBuffer(encoded), scratch, rgba, partial;

  assert.strictEqual(reader.offsets, undefined, "no debe materializar offsets");
  assert.strictEqual(reader.isKey, undefined, "no debe materializar booleanos por frame");
  assert(reader.keyBits instanceof Uint8Array);
  assert.strictEqual(reader.keyBits.length, 1);
  assert(reader.dirtyCellBits instanceof Uint8Array);
  assert.strictEqual(reader.dirtyCellBits.length, 2, "un bit persistente por celda");
  assert.strictEqual(reader.dirtyCells, undefined, "no debe existir una lista Uint32 por celda");
  assert.strictEqual(reader._scratch, null);

  reader.seek(0);
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f0));
  assert.strictEqual(reader._scratch, null, "RAW no necesita scratch");
  reader.seek(1);
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f1));
  scratch = reader._scratch;
  assert(scratch instanceof Uint8Array);
  assert.strictEqual(scratch.length, 10, "el bound DELTA no debe reservarse si no hace falta");
  reader.seek(2);
  assert.strictEqual(reader._scratch, scratch, "DELTA debe reutilizar scratch");
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f2));
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCellCount, 2);
  assert.strictEqual(reader.dirtyCellBits[0], 130); /* celdas 1 y 7 */
  reader.seek(3);
  assert.strictEqual(reader._scratch, scratch, "MASK debe reutilizar scratch");
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f3));

  reader.seek(2); /* seek hacia atras: keyframe 1 + DELTA */
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f2));
  reader.seek(1);
  rgba = new Uint8Array(40);
  reader.fillRGBA(rgba); /* backing persistente en el keyframe 1 */
  reader.seek(3); /* union: DELTA {1,7} + MASK {1,9} */
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), Array.prototype.slice.call(f3));
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCellCount, 3, "la union no debe contar dos veces la celda 1");
  assert.strictEqual(reader.dirtyCellBits[0], 130);
  assert.strictEqual(reader.dirtyCellBits[1], 2);

  reader.fillRGBAChanged(rgba);
  partial = new Uint8Array(40);
  reader.fillRGBA(partial);
  assert.deepStrictEqual(Array.prototype.slice.call(rgba), Array.prototype.slice.call(partial),
                         "actualizar solo bits debe igualar la conversion completa");

  reader.seek(3); /* ningun frame nuevo: mapa vacio */
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCellCount, 0);
  assert.strictEqual(reader.dirtyCellBits[0] | reader.dirtyCellBits[1], 0);
  var unchanged = Buffer.from(rgba);
  assert.strictEqual(reader.fillRGBAChanged(rgba), rgba);
  assert.deepStrictEqual(Buffer.from(rgba), unchanged);

  reader.seek(0);
  rgba = new Uint8Array(40);
  assert.strictEqual(reader.dirtyFull, true);
  assert.strictEqual(reader.dirtyCellCount, 10);
  reader.fillRGBAChanged(rgba); /* keyframe cae al camino full */
  partial = new Uint8Array(40);
  reader.fillRGBA(partial);
  assert.deepStrictEqual(Array.prototype.slice.call(rgba), Array.prototype.slice.call(partial));

  reader.fillRGBA(rgba);
  partial = new Uint8Array(40);
  partial.fill(99);
  reader.fillRGBARows(partial, 1, 1);
  assert.deepStrictEqual(Array.prototype.slice.call(partial, 0, 20), new Array(20).fill(99));
  assert.deepStrictEqual(Array.prototype.slice.call(partial, 20), Array.prototype.slice.call(rgba, 20));
  expectError(function () { reader.fillRGBARows(partial, -1, 0); }, /rango de filas/);
}());

(function testInflaterLegacyIntoAndBounds() {
  var text = Buffer.from(new Array(2001).join("abcdef"));
  var variants = [
    zlib.deflateSync(text),
    zlib.deflateSync(text, { level: 0 }),
    zlib.deflateSync(text, { strategy: zlib.constants.Z_FIXED })
  ];
  variants.forEach(function (compressed) {
    var legacy = inflate.ASCL_inflateZlib(compressed);
    var out = new Uint8Array(text.length), actual;
    assert.deepStrictEqual(Buffer.from(legacy), text);
    actual = inflate.ASCL_inflateZlibInto(compressed, out, out.length);
    assert.strictEqual(actual, text.length);
    assert.deepStrictEqual(Buffer.from(out), text);
  });
  var rawDeflate = zlib.deflateRawSync(text), rawOut = new Uint8Array(text.length);
  assert.deepStrictEqual(Buffer.from(inflate.ASCL_inflateRaw(rawDeflate)), text);
  assert.strictEqual(inflate.ASCL_inflateRawInto(rawDeflate, rawOut, rawOut.length), text.length);
  assert.deepStrictEqual(Buffer.from(rawOut), text);
  expectError(function () {
    inflate.ASCL_inflateZlibInto(variants[0], new Uint8Array(10), 10);
  }, /maxLength|insuficiente/);
  var badAdler = Buffer.from(variants[0]); badAdler[badAdler.length - 1] ^= 1;
  expectError(function () { inflate.ASCL_inflateZlib(badAdler); }, /Adler32/);
  var badHeader = Buffer.from(variants[0]); badHeader[0] = 0;
  expectError(function () { inflate.ASCL_inflateZlib(badHeader); }, /CMF/);
  expectError(function () { inflate.ASCL_inflateZlib(variants[0].subarray(0, 5)); }, /truncado|entrada/);
}());

(function testReaderGrowsScratchOnlyWhenRealOutputRequiresIt() {
  var palette = Buffer.from([0,0,0, 1,1,1, 2,2,2, 3,3,3]);
  var raw = Buffer.from([0,0,0,0,0,0,0,0,0,0]);
  var encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, null, deltaPayload([0, 1, 2], [1, 2, 3]))
  ]);
  var reader = parseBuffer(encoded);
  reader.seek(1);
  assert(reader._scratch.length >= 15 && reader._scratch.length < reader._scratchMax,
         "scratch debe crecer por salida real, no saltar al maximo teorico");
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells, 0, 4), [1, 2, 3, 0]);
}());

(function testEmptyDeltaLeavesPersistentRgbaUntouched() {
  var palette = Buffer.from([0,0,0, 1,1,1, 2,2,2, 3,3,3]);
  var raw = Buffer.from([0,1,2,3,0,1,2,3,0,1]);
  var encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, null, zlib.deflateSync(Buffer.alloc(0)))
  ]);
  var reader = parseBuffer(encoded), rgba = new Uint8Array(40), before;
  reader.seek(0); reader.fillRGBA(rgba); before = Buffer.from(rgba);
  reader.seek(1);
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCellCount, 0);
  assert.strictEqual(reader.dirtyCellBits[0] | reader.dirtyCellBits[1], 0);
  reader.fillRGBAChanged(rgba);
  assert.deepStrictEqual(Buffer.from(rgba), before);
}());

(function testHeaderAndStructureRejections() {
  var palette = Buffer.from([0,0,0, 1,1,1, 2,2,2, 3,3,3]);
  var raw = Buffer.from([0,1,2,3,0,1,2,3,0,1]);
  var base = makeAscl([block(TAG_RAW, palette, raw)]), bad;

  bad = Buffer.from(base); bad[4] = 2;
  expectError(function () { parseBuffer(bad); }, /version/);
  bad = Buffer.from(base); bad[5] = 9;
  expectError(function () { parseBuffer(bad); }, /modo/);
  bad = Buffer.from(base); bad.writeUInt32LE(31, 20);
  expectError(function () { parseBuffer(bad); }, /data_off/);
  bad = Buffer.from(base); bad.writeUInt32LE(0xffffffff, 32);
  expectError(function () { parseBuffer(bad); }, /offset/);
  bad = Buffer.from(base); bad[40] = 9; /* tag: table 32..35, block len 36..39 */
  expectError(function () { parseBuffer(bad); }, /tag/);
  bad = Buffer.from(base); bad.writeUInt16LE(5, 41);
  expectError(function () { parseBuffer(bad); }, /pal_count/);

  bad = makeAscl([block(TAG_RAW, palette, raw)], { cols: 65535, rows: 65535 });
  expectError(function () { parseBuffer(bad); }, /limite operativo/);
}());

(function testPayloadRejectionsBeforeMutation() {
  var palette = Buffer.from([0,0,0, 1,1,1, 2,2,2, 3,3,3]);
  var raw = Buffer.from([0,1,2,3,0,1,2,3,0,1]);
  var reader, encoded, before;

  encoded = makeAscl([block(TAG_RAW, palette, Buffer.from([0,1]))]);
  expectError(function () { parseBuffer(encoded); }, /RAW con longitud/);

  encoded = makeAscl([block(TAG_RAW, palette, Buffer.from([0,1,2,3,0,1,2,3,0,9]))]);
  reader = parseBuffer(encoded);
  expectError(function () { reader.seek(0); }, /indice de paleta/);

  encoded = makeAscl([block(TAG_ZLIB, palette, zlib.deflateSync(Buffer.alloc(9)))]);
  reader = parseBuffer(encoded);
  expectError(function () { reader.seek(0); }, /longitud descomprimida/);

  encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, null, zlib.deflateSync(Buffer.from([1])))
  ]);
  reader = parseBuffer(encoded); reader.seek(0);
  expectError(function () { reader.seek(1); }, /DELTA con longitud/);

  encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, null, deltaPayload([2, 10], [3, 1]))
  ]);
  reader = parseBuffer(encoded); reader.seek(0);
  before = Buffer.from(reader.cells);
  expectError(function () { reader.seek(1); }, /offset DELTA/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before,
    "todos los offsets deben validarse antes de la primera escritura");

  encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_MASK, null, zlib.deflateSync(Buffer.from([1, 0])))
  ]);
  reader = parseBuffer(encoded); reader.seek(0);
  expectError(function () { reader.seek(1); }, /DELTA_MASK con longitud/);

  encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_MASK, null, zlib.deflateSync(Buffer.from([0, 128])))
  ]);
  reader = parseBuffer(encoded); reader.seek(0);
  expectError(function () { reader.seek(1); }, /bits fuera/);

  encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, palette, deltaPayload([1], [2]))
  ]);
  expectError(function () { parseBuffer(encoded); }, /DELTA no puede cambiar paleta/);
}());

(function testUnorderedAndRepeatedDeltaOffsetsRemainV1Compatible() {
  var palette = Buffer.from([0,0,0, 1,1,1, 2,2,2, 3,3,3]);
  var raw = Buffer.from([0,1,2,3,0,1,2,3,0,1]);
  var expected = Buffer.from(raw);
  var encoded = makeAscl([
    block(TAG_RAW, palette, raw),
    block(TAG_DELTA, null, deltaPayload([7, 2, 7], [1, 3, 2]))
  ]);
  var reader = parseBuffer(encoded);
  expected[2] = 3;
  expected[7] = 2; /* un offset repetido conserva la ultima escritura */
  reader.seek(0);
  reader.seek(1);
  assert.deepStrictEqual(Buffer.from(reader.cells), expected);
  assert.strictEqual(reader.dirtyCellCount, 2, "los repetidos cuentan una sola celda dirty");
  assert.strictEqual(reader.dirtyCellBits[0], 132, "se marcan offsets 2 y 7");
  assert.strictEqual(reader.dirtyY0, 0);
  assert.strictEqual(reader.dirtyY1, 1);
}());

(function testCrcDetectsCachedBodyCorruption() {
  var source = fs.readFileSync(path.join(__dirname, "fixtures", "test_pixel.ascl"));
  var corrupt = Buffer.from(source);
  corrupt[corrupt.length - 1] ^= 1;
  expectError(function () { parseBuffer(corrupt); }, /CRC32/);
}());

(function testDistributedSourcesStayEs5AndAvoidFrameArrays() {
  var readerSource = fs.readFileSync(path.join(__dirname, "..", "frontend", "reader.js"), "utf8");
  var inflateSource = fs.readFileSync(path.join(__dirname, "..", "frontend", "inflate.js"), "utf8");
  [readerSource, inflateSource].forEach(function (source) {
    assert.strictEqual(/\b(?:const|let|class)\b|=>/.test(source), false);
    assert.doesNotThrow(function () { new Function(source); });
  });
  assert.strictEqual(/new Array\s*\(\s*h\.nFrames/.test(readerSource), false);
  assert.strictEqual(/new Uint32Array\s*\(\s*this\.n/.test(readerSource), false);
  assert.strictEqual(/\.dest\s*=\s*\[\]|\.dest\.push\s*\(/.test(inflateSource), false);
}());

console.log("reader safety tests: OK");
