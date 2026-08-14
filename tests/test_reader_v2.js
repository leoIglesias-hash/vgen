"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var zlib = require("zlib");
var ASCLV2 = require("../frontend/reader-v2.js");

var TAG_RAW = 0, TAG_ZLIB = 1, TAG_DELTA = 2, TAG_MASK = 3;
var KEY_RAW = 4, KEY_ZLIB = 5, DELTA_RAW = 6, DELTA_ZLIB = 7;
var PREDICT_KEY_ZLIB = 8, PREDICT_DELTA_ZLIB = 9;
var PRED_LEFT = 0, PRED_TOP = 1, PRED_GRADIENT = 2;
var PRED_PREVIOUS_SUB = 3, PRED_PREVIOUS_XOR = 4;
var SKIP = 0, SOLID = 1, SPARSE = 2, MASK = 3;
var PACK1 = 4, PACK2 = 5, PAL4 = 6, PAL8 = 7;

function b(value) { return Buffer.isBuffer(value) ? value : Buffer.from(value); }

function uvar(value) {
  var out = [];
  do {
    var part = value % 128;
    value = Math.floor(value / 128);
    out.push(part | (value ? 128 : 0));
  } while (value);
  return Buffer.from(out);
}

function packed(codes, bits) {
  var out = Buffer.alloc(Math.ceil(codes.length * bits / 8)), i;
  for (i = 0; i < codes.length; i++) {
    out[Math.floor(i * bits / 8)] |= codes[i] << ((i * bits) & 7);
  }
  return out;
}

function commandSkip(run) { return Buffer.concat([Buffer.from([SKIP]), uvar(run)]); }
function commandSolid(value) { return Buffer.from([SOLID, value]); }
function commandSparse(entries) {
  var parts = [Buffer.from([SPARSE]), uvar(entries.length)], i;
  for (i = 0; i < entries.length; i++) {
    parts.push(uvar(entries[i][0]));
    parts.push(Buffer.from([entries[i][1]]));
  }
  return Buffer.concat(parts);
}
function commandMask(npix, offsets, values) {
  var mask = Buffer.alloc(Math.ceil(npix / 8)), i;
  for (i = 0; i < offsets.length; i++) mask[offsets[i] >>> 3] |= 1 << (offsets[i] & 7);
  return Buffer.concat([Buffer.from([MASK]), mask, Buffer.from(values)]);
}
function commandPack1(map, codes) {
  return Buffer.concat([Buffer.from([PACK1, map[0], map[1]]), packed(codes, 1)]);
}
function commandPack(opcode, map, codes, bits) {
  return Buffer.concat([Buffer.from([opcode, map.length]), Buffer.from(map), packed(codes, bits)]);
}
function commandPal8(values) { return Buffer.concat([Buffer.from([PAL8]), Buffer.from(values)]); }

function predictorResidual(cells, previous, cols, predictor) {
  var out = Buffer.alloc(cells.length), i, x, y, predicted, left, top, topLeft;
  for (i = 0; i < cells.length; i++) {
    x = i % cols;
    y = Math.floor(i / cols);
    if (predictor === PRED_LEFT) {
      predicted = x ? cells[i - 1] : 0;
      out[i] = (cells[i] - predicted) & 255;
    } else if (predictor === PRED_TOP) {
      predicted = y ? cells[i - cols] : 0;
      out[i] = (cells[i] - predicted) & 255;
    } else if (predictor === PRED_GRADIENT) {
      left = x ? cells[i - 1] : 0;
      top = y ? cells[i - cols] : 0;
      topLeft = x && y ? cells[i - cols - 1] : 0;
      predicted = (left + top - topLeft) & 255;
      out[i] = (cells[i] - predicted) & 255;
    } else if (predictor === PRED_PREVIOUS_SUB) {
      out[i] = (cells[i] - previous[i]) & 255;
    } else if (predictor === PRED_PREVIOUS_XOR) {
      out[i] = cells[i] ^ previous[i];
    } else {
      throw new Error("predictor de test desconocido");
    }
  }
  return out;
}

function predictorPayload(cells, previous, cols, predictor) {
  return Buffer.concat([
    Buffer.from([predictor]),
    zlib.deflateSync(predictorResidual(cells, previous, cols, predictor))
  ]);
}

function block(tag, palette, payload) {
  var pal = palette ? b(palette) : Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  var result;
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  b(payload).copy(body, 3 + pal.length);
  result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function makeAscl(frames, options) {
  options = options || {};
  var cols = options.cols || 17, rows = options.rows || 17;
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i, out;
  header.write("ASCL", 0, "ascii");
  header[4] = 2;
  header[5] = 3;
  header[6] = options.flags === undefined ? 12 : options.flags;
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(options.paletteSize || 32, 12);
  header.writeUInt32LE(frames.length, 14);
  header[18] = 0;
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  header[26] = options.tileSize === undefined ? 16 : options.tileSize;
  header[27] = options.codecFlags === undefined ? 1 : options.codecFlags;
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  out = Buffer.concat([header, table].concat(frames));
  out.writeUInt32LE(ASCLV2.crc32v2(out), 28);
  return out;
}

function parse(buf) { return ASCLV2.parse(buf.buffer, buf.byteOffset, buf.byteLength); }

function palette(count) {
  var out = Buffer.alloc(count * 3), i;
  for (i = 0; i < count; i++) {
    out[i * 3] = i * 7;
    out[i * 3 + 1] = 255 - i * 5;
    out[i * 3 + 2] = i * 3;
  }
  return out;
}

function tileValues(cells, cols, tileX, tileY, width, height, values) {
  var q = 0, x, y;
  for (y = 0; y < height; y++) {
    for (x = 0; x < width; x++) cells[(tileY + y) * cols + tileX + x] = values[q++];
  }
}

function readTile(cells, cols, tileX, tileY, width, height) {
  var out = [], x, y;
  for (y = 0; y < height; y++) {
    for (x = 0; x < width; x++) out.push(cells[(tileY + y) * cols + tileX + x]);
  }
  return out;
}

function dirtyCellIndices(reader) {
  var out = [], i;
  for (i = 0; i < reader.n; i++) {
    if ((reader.dirtyCellBits[i >>> 3] >>> (i & 7)) & 1) out.push(i);
  }
  return out;
}

function fixtureRegional() {
  var codes256 = [], codes16a = [], codes16b = [], values16 = [];
  var keyCells = Buffer.alloc(17 * 17), deltaCells, finalCells = Buffer.alloc(17 * 17);
  var i, key, delta, finalKey, pal = palette(32);
  for (i = 0; i < 256; i++) codes256.push(i & 1);
  for (i = 0; i < 16; i++) {
    codes16a.push(i % 3);
    codes16b.push(i % 5);
    values16.push(15 + i);
  }
  key = Buffer.concat([
    commandPack1([0, 1], codes256),
    commandPack(PACK2, [2, 3, 4], codes16a, 2),
    commandPack(PAL4, [5, 6, 7, 8, 9], codes16b, 4),
    commandSolid(10)
  ]);
  tileValues(keyCells, 17, 0, 0, 16, 16, codes256);
  tileValues(keyCells, 17, 16, 0, 1, 16, codes16a.map(function (v) { return v + 2; }));
  tileValues(keyCells, 17, 0, 16, 16, 1, codes16b.map(function (v) { return v + 5; }));
  keyCells[16 * 17 + 16] = 10;

  delta = Buffer.concat([
    commandSparse([[0, 11], [255, 12]]),
    commandMask(16, [0, 15], [13, 14]),
    commandPal8(values16),
    commandSkip(1)
  ]);
  deltaCells = Buffer.from(keyCells);
  deltaCells[0] = 11;
  deltaCells[15 * 17 + 15] = 12;
  deltaCells[16] = 13;
  deltaCells[15 * 17 + 16] = 14;
  tileValues(deltaCells, 17, 0, 16, 16, 1, values16);

  for (i = 0; i < finalCells.length; i++) finalCells[i] = i % 32;
  finalKey = Buffer.concat([
    commandPal8(readTile(finalCells, 17, 0, 0, 16, 16)),
    commandPal8(readTile(finalCells, 17, 16, 0, 1, 16)),
    commandPal8(readTile(finalCells, 17, 0, 16, 16, 1)),
    commandSolid(finalCells[288])
  ]);
  return {
    encoded: makeAscl([
      block(KEY_RAW, pal, key),
      block(DELTA_ZLIB, null, zlib.deflateSync(delta)),
      block(DELTA_RAW, null, commandSkip(4)),
      block(KEY_ZLIB, null, zlib.deflateSync(finalKey))
    ]),
    palette: pal,
    key: keyCells,
    delta: deltaCells,
    final: finalCells
  };
}

function fixturePredictors() {
  var cols = 17, rows = 17, n = cols * rows, pal = palette(32);
  var left = Buffer.alloc(n), afterSub, top = Buffer.alloc(n), afterXor;
  var gradient = Buffer.alloc(n), x, y, i;
  for (y = 0; y < rows; y++) {
    for (x = 0; x < cols; x++) {
      i = y * cols + x;
      left[i] = (x + y) % 16;
      top[i] = (y * 2 + (x & 1)) % 16;
      gradient[i] = (x * 3 + y * 5) % 31;
    }
  }
  afterSub = Buffer.from(left);
  afterSub[0] = 23;
  afterSub[n - 1] = 31;
  afterXor = Buffer.from(top);
  afterXor[16] = 20;
  afterXor[16 * cols] = 21;
  return {
    encoded: makeAscl([
      block(PREDICT_KEY_ZLIB, pal,
        predictorPayload(left, null, cols, PRED_LEFT)),
      block(PREDICT_DELTA_ZLIB, null,
        predictorPayload(afterSub, left, cols, PRED_PREVIOUS_SUB)),
      block(PREDICT_KEY_ZLIB, null,
        predictorPayload(top, null, cols, PRED_TOP)),
      block(PREDICT_DELTA_ZLIB, null,
        predictorPayload(afterXor, top, cols, PRED_PREVIOUS_XOR)),
      block(PREDICT_KEY_ZLIB, null,
        predictorPayload(gradient, null, cols, PRED_GRADIENT))
    ]),
    palette: pal,
    left: left,
    afterSub: afterSub,
    top: top,
    afterXor: afterXor,
    gradient: gradient
  };
}

(function testRegionalCommandsSeekDirtyAndRgba() {
  var f = fixtureRegional(), reader = parse(f.encoded), skipped;
  var rgba, expectedRgba, before;
  assert.strictEqual(reader.header.version, 2);
  assert.strictEqual(reader.tileSize, 16);
  assert.strictEqual(reader.tileCount, 4);
  assert.strictEqual(reader.cells.length, 289);
  assert.strictEqual(reader.dirtyTileBits.length, 1);
  assert.strictEqual(reader.dirtyTiles.length, 4);

  reader.seek(0);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.key);
  assert.strictEqual(reader.dirtyFull, true);
  assert.strictEqual(reader.dirtyCount, 4);
  rgba = new Uint8Array(reader.n * 4);
  reader.fillRGBA(rgba);

  reader.seek(1);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.delta);
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCount, 1);
  assert.strictEqual(reader.dirtyTiles[0], 2, "PAL8 denso queda como tile");
  assert.strictEqual(reader.dirtyTileBits[0], 4);
  assert.strictEqual(reader.dirtyCellCount, 4);
  assert.deepStrictEqual(dirtyCellIndices(reader), [0, 16, 270, 271],
    "SPARSE y MASK conservan celdas exactas");
  assert.strictEqual(reader.dirtyY0, 0);
  assert.strictEqual(reader.dirtyY1, 16);
  reader.fillRGBAChanged(rgba);
  expectedRgba = new Uint8Array(reader.n * 4);
  reader.fillRGBA(expectedRgba);
  assert.deepStrictEqual(Buffer.from(rgba), Buffer.from(expectedRgba));

  before = Buffer.from(reader.cells);
  reader.seek(2);
  assert.deepStrictEqual(Buffer.from(reader.cells), before);
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCount, 0);
  assert.strictEqual(reader.dirtyY0, 17);
  assert.strictEqual(reader.dirtyY1, -1);

  reader.seek(3);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.final);
  assert.strictEqual(reader.dirtyFull, true);
  assert(reader._scratch instanceof Uint8Array);
  var scratch = reader._scratch;
  reader.seek(1);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.delta, "seek inverso reconstruye key+delta");
  assert.strictEqual(reader._scratch, scratch, "scratch zlib se reutiliza");

  skipped = parse(f.encoded);
  skipped.seek(0);
  skipped.seek(2); /* salta delta + repeat y debe conservar la union dirty del delta. */
  assert.deepStrictEqual(Buffer.from(skipped.cells), f.delta);
  assert.strictEqual(skipped.dirtyFull, false);
  assert.deepStrictEqual(Array.prototype.slice.call(skipped.dirtyTiles, 0, skipped.dirtyCount),
    [2]);
  assert.deepStrictEqual(dirtyCellIndices(skipped), [0, 16, 270, 271]);
}());

(function testPredictorsRoundTripKeyMapSeekAndDirtyBands() {
  var f = fixturePredictors(), reader = parse(f.encoded), direct, rgba;
  assert.strictEqual(reader._isKey(0), true);
  assert.strictEqual(reader._isKey(1), false);
  assert.strictEqual(reader._isKey(2), true);
  assert.strictEqual(reader._isKey(3), false);
  assert.strictEqual(reader._isKey(4), true);

  reader.seek(0);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.left, "LEFT exacto");
  assert.strictEqual(reader.dirtyFull, true);
  reader.seek(1);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.afterSub, "PREVIOUS_SUB exacto");
  assert.strictEqual(reader.dirtyFull, false);
  assert.strictEqual(reader.dirtyCount, 0, "predictor disperso no expande a tiles");
  assert.strictEqual(reader.dirtyCellCount, 2);
  assert.deepStrictEqual(dirtyCellIndices(reader), [0, 288],
    "solo celdas con residual SUB no nulo");
  assert.strictEqual(reader.dirtyY0, 0);
  assert.strictEqual(reader.dirtyY1, 16);
  rgba = new Uint8Array(reader.n * 4);
  for (var ri = 0; ri < rgba.length; ri++) rgba[ri] = 77;
  reader.fillRGBAChanged(rgba);
  assert.strictEqual(rgba[3], 255);
  assert.strictEqual(rgba[288 * 4 + 3], 255);
  assert.strictEqual(rgba[1 * 4 + 3], 77, "RGBA no escribe el resto del tile");

  reader.seek(2);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.top, "TOP exacto");
  assert.strictEqual(reader.dirtyFull, true);
  reader.seek(3);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.afterXor, "PREVIOUS_XOR exacto");
  assert.strictEqual(reader.dirtyCount, 0);
  assert.strictEqual(reader.dirtyCellCount, 2);
  assert.deepStrictEqual(dirtyCellIndices(reader), [16, 272],
    "solo celdas con residual XOR no nulo");
  assert.strictEqual(reader.dirtyY0, 0);
  assert.strictEqual(reader.dirtyY1, 16);
  reader.seek(4);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.gradient, "GRADIENT exacto");
  assert.strictEqual(reader.dirtyFull, true);

  direct = parse(f.encoded);
  direct.seek(3);
  assert.deepStrictEqual(Buffer.from(direct.cells), f.afterXor,
    "seek directo usa key predictor mas cercano");
  direct.seek(1);
  assert.deepStrictEqual(Buffer.from(direct.cells), f.afterSub,
    "seek inverso recompone desde key predictor");
}());

(function testPredictorValidationIsTransactional() {
  var f = fixturePredictors(), n = 17 * 17, zero = Buffer.alloc(n);
  var first = block(PREDICT_KEY_ZLIB, f.palette,
    predictorPayload(f.left, null, 17, PRED_LEFT));
  var reader, before, badResidual, encoded;

  encoded = makeAscl([
    first,
    block(PREDICT_DELTA_ZLIB, null,
      Buffer.concat([Buffer.from([PRED_LEFT]), zlib.deflateSync(zero)]))
  ]);
  reader = parse(encoded);
  reader.seek(0);
  before = Buffer.from(reader.cells);
  assert.throws(function () { reader.seek(1); }, /predictor incompatible/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before, "ID key/delta no muta cells");
  assert.strictEqual(reader.decodedIndex, -1);

  badResidual = Buffer.alloc(n);
  badResidual[0] = 1; /* cambio valido temprano */
  badResidual[n - 1] = (250 - f.left[n - 1]) & 255; /* indice invalido tardio */
  encoded = makeAscl([
    first,
    block(PREDICT_DELTA_ZLIB, null,
      Buffer.concat([Buffer.from([PRED_PREVIOUS_SUB]), zlib.deflateSync(badResidual)]))
  ]);
  reader = parse(encoded);
  reader.seek(0);
  before = Buffer.from(reader.cells);
  assert.throws(function () { reader.seek(1); }, /indice de paleta fuera de rango/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before,
    "delta predictor valida todos los indices antes de aplicar el primero");

  encoded = makeAscl([
    first,
    block(PREDICT_DELTA_ZLIB, null, Buffer.concat([
      Buffer.from([PRED_PREVIOUS_XOR]), zlib.deflateSync(Buffer.alloc(n - 1))
    ]))
  ]);
  reader = parse(encoded);
  reader.seek(0);
  before = Buffer.from(reader.cells);
  assert.throws(function () { reader.seek(1); }, /longitud descomprimida incorrecta/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before, "inflate corto no muta cells");

  encoded = makeAscl([
    first,
    block(PREDICT_DELTA_ZLIB, null,
      Buffer.from([PRED_PREVIOUS_SUB, 0x78, 0x9c, 0xff]))
  ]);
  reader = parse(encoded);
  reader.seek(0);
  before = Buffer.from(reader.cells);
  assert.throws(function () { reader.seek(1); }, /inflate|zlib|truncad/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before, "zlib corrupto no muta cells");

  assert.throws(function () {
    parse(makeAscl([block(PREDICT_KEY_ZLIB, f.palette, Buffer.from([PRED_LEFT]))]));
  }, /payload predictor truncado/);
  assert.throws(function () {
    parse(makeAscl([block(10, f.palette, Buffer.from([1]))]));
  }, /tag desconocido/);
}());

(function testHybridDirtyUnionIsDisjoint() {
  var n = 17 * 17, pal = palette(8), base = Buffer.alloc(n);
  var one = Buffer.from(base), two, three, reader, rgba, i, x, y;
  one[0] = 1;
  two = Buffer.from(one);
  for (y = 0; y < 16; y++) {
    for (x = 0; x < 16; x++) two[y * 17 + x] = 2;
  }
  three = Buffer.from(two);
  three[n - 1] = 3;
  reader = parse(makeAscl([
    block(TAG_RAW, pal, base),
    block(PREDICT_DELTA_ZLIB, null,
      predictorPayload(one, base, 17, PRED_PREVIOUS_SUB)),
    block(DELTA_RAW, null, Buffer.concat([commandSolid(2), commandSkip(3)])),
    block(PREDICT_DELTA_ZLIB, null,
      predictorPayload(three, two, 17, PRED_PREVIOUS_SUB))
  ], { paletteSize: 8 }));
  reader.seek(0);
  reader.seek(3);
  assert.deepStrictEqual(Buffer.from(reader.cells), three);
  assert.strictEqual(reader.dirtyCount, 1);
  assert.strictEqual(reader.dirtyTiles[0], 0);
  assert.strictEqual(reader.dirtyCellCount, 1);
  assert.deepStrictEqual(dirtyCellIndices(reader), [n - 1],
    "el tile absorbe bits solapados y conserva la celda externa");
  rgba = new Uint8Array(n * 4);
  for (i = 0; i < rgba.length; i++) rgba[i] = 77;
  reader.fillRGBAChanged(rgba);
  assert.strictEqual(rgba[0 * 4 + 3], 255, "tile denso actualizado");
  assert.strictEqual(rgba[(n - 1) * 4 + 3], 255, "celda exacta actualizada");
  assert.strictEqual(rgba[16 * 4 + 3], 77, "union no expande a otro tile");
}());

(function testLegacyFallbackTagsRemainExactInsideV2() {
  var pal = palette(8), n = 17, raw0 = Buffer.alloc(n), raw3 = Buffer.alloc(n);
  var deltaRaw = Buffer.alloc(10), maskRaw = Buffer.alloc(Math.ceil(n / 8) + 2);
  var reader, encoded, i;
  for (i = 0; i < n; i++) { raw0[i] = i % 8; raw3[i] = (i + 3) % 8; }
  deltaRaw.writeUInt32LE(0, 0); deltaRaw.writeUInt32LE(16, 4);
  deltaRaw[8] = 7; deltaRaw[9] = 6;
  maskRaw[0] = 2; maskRaw[2] = 1; /* celdas 1 y 17? n=17, luego valores */
  maskRaw[3] = 5; maskRaw[4] = 4;
  encoded = makeAscl([
    block(TAG_RAW, pal, raw0),
    block(TAG_DELTA, null, zlib.deflateSync(deltaRaw)),
    block(TAG_MASK, null, zlib.deflateSync(maskRaw)),
    block(TAG_ZLIB, null, zlib.deflateSync(raw3))
  ], { cols: 17, rows: 1, paletteSize: 8 });
  reader = parse(encoded);
  reader.seek(0);
  reader.seek(1);
  assert.strictEqual(reader.cells[0], 7);
  assert.strictEqual(reader.cells[16], 6);
  assert.strictEqual(reader.dirtyCount, 0);
  assert.strictEqual(reader.dirtyCellCount, 2);
  assert.deepStrictEqual(dirtyCellIndices(reader), [0, 16],
    "DELTA legacy conserva dirty exacto");
  reader.seek(2);
  assert.strictEqual(reader.cells[1], 5);
  assert.strictEqual(reader.cells[16], 4);
  assert.strictEqual(reader.dirtyCount, 0);
  assert.deepStrictEqual(dirtyCellIndices(reader), [1, 16],
    "DELTA_MASK legacy conserva dirty exacto");
  reader.seek(3);
  assert.deepStrictEqual(Buffer.from(reader.cells), raw3);
  assert.strictEqual(reader.dirtyFull, true);
}());

(function testRegionalFrameIsValidatedBeforeMutation() {
  var f = fixtureRegional(), frames, badDelta, encoded, reader, before;
  /* Primer tile seria valido; el mapa descendente del segundo debe abortar antes de aplicarlo. */
  badDelta = Buffer.concat([
    commandSparse([[0, 11]]),
    Buffer.concat([Buffer.from([PACK1, 2, 1]), Buffer.alloc(2)]),
    commandSkip(2)
  ]);
  frames = [
    block(KEY_RAW, f.palette, f.encoded.subarray(0, 0)),
    block(DELTA_RAW, null, badDelta)
  ];
  /* Reusar el key regional real del fixture, extraido mediante una reconstruccion directa. */
  var fresh = fixtureRegional();
  var keyBlockOffset = fresh.encoded.readUInt32LE(32);
  var keyBlockLength = fresh.encoded.readUInt32LE(keyBlockOffset);
  frames[0] = Buffer.from(fresh.encoded.subarray(keyBlockOffset, keyBlockOffset + 4 + keyBlockLength));
  encoded = makeAscl(frames);
  reader = parse(encoded);
  reader.seek(0);
  before = Buffer.from(reader.cells);
  assert.throws(function () { reader.seek(1); }, /mapa packed no canonico/);
  assert.deepStrictEqual(Buffer.from(reader.cells), before,
    "ningun comando se aplica si otro comando del frame es invalido");
  assert.strictEqual(reader.decodedIndex, -1, "estado parcial queda marcado como no confiable");
}());

(function testCanonicalAndBoundsRejections() {
  var f = fixtureRegional(), keyBlockOffset = f.encoded.readUInt32LE(32);
  var keyBlockLength = f.encoded.readUInt32LE(keyBlockOffset);
  var keyBlock = Buffer.from(f.encoded.subarray(keyBlockOffset, keyBlockOffset + 4 + keyBlockLength));
  var cases = [
    { payload: Buffer.from([SKIP, 0x84, 0x00]), pattern: /uvarint no canonico/ },
    { payload: Buffer.from([SKIP, 3]), pattern: /no cubre/ },
    { payload: Buffer.from([SPARSE, 1, 0, 0, SKIP, 3]), pattern: /escritura identica/ },
    { payload: Buffer.concat([Buffer.from([MASK]), Buffer.alloc(32), commandSkip(3)]), pattern: /MASK vacio/ }
  ];
  cases.forEach(function (entry) {
    var encoded = makeAscl([keyBlock, block(DELTA_RAW, null, entry.payload)]);
    var reader = parse(encoded);
    reader.seek(0);
    assert.throws(function () { reader.seek(1); }, entry.pattern);
  });

  var badHeader = Buffer.from(f.encoded);
  badHeader[27] = 0;
  assert.throws(function () { parse(badHeader); }, /codec_flags|CRC32/);
  badHeader = Buffer.from(f.encoded);
  badHeader[7] ^= 1;
  assert.throws(function () { parse(badHeader); }, /CRC32/);
}());

(function testPalettePoliciesMatchV1AndReferenceDecoder() {
  var pal = palette(2), raw = Buffer.alloc(4), delta = Buffer.alloc(5);
  var perFrame, repeatedGlobal;
  delta.writeUInt32LE(0, 0);
  delta[4] = 1;
  perFrame = makeAscl([
    block(TAG_RAW, pal, raw),
    block(TAG_DELTA, null, zlib.deflateSync(delta))
  ], { cols: 2, rows: 2, paletteSize: 2, flags: 8 });
  assert.throws(function () { parse(perFrame); }, /paleta per-frame ausente/,
    "sin flags de paleta cada frame debe ser autonomo, igual que v1/Python");

  repeatedGlobal = makeAscl([
    block(TAG_RAW, pal, raw),
    block(TAG_RAW, pal, Buffer.from([1, 1, 1, 1]))
  ], { cols: 2, rows: 2, paletteSize: 2, flags: 12 });
  assert.throws(function () { parse(repeatedGlobal); }, /paleta global reemitida/,
    "PAL_GLOBAL solo permite emitir la paleta en frame 0");
}());

(function testBundleViewAndEs5Source() {
  var f = fixtureRegional(), outer = new ArrayBuffer(f.encoded.length + 23);
  var bytes = new Uint8Array(outer), reader, source;
  bytes.set(new Uint8Array(f.encoded.buffer, f.encoded.byteOffset, f.encoded.byteLength), 11);
  reader = ASCLV2.parse(outer, 11, f.encoded.length);
  assert.strictEqual(reader.bytes.buffer, outer);
  assert.strictEqual(reader.bytes.byteOffset, 11);
  reader.seek(1);
  assert.deepStrictEqual(Buffer.from(reader.cells), f.delta);

  source = fs.readFileSync(path.join(__dirname, "..", "frontend", "reader-v2.js"), "utf8");
  assert.strictEqual(/\b(?:const|let|class)\b|=>/.test(source), false);
  assert.doesNotThrow(function () { new Function(source); });
  assert.strictEqual(/new Array\s*\(\s*(?:h\.)?nFrames/.test(source), false);
}());

console.log("reader v2 tests: OK");
