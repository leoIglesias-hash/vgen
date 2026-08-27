/*
 * W-08: ReaderV2 acepta tile_size flexible (4..32).
 *
 * Construye archivos v2 sinteticos con los seis tamanos del barrido de E-09
 * sobre una grilla que no es multiplo de ninguno (37x29: tiles de borde en
 * ambos ejes), decodifica un keyframe SOLID por tile y verifica la matriz
 * celda a celda. Los tamanos fuera de rango se rechazan limpiamente.
 */
"use strict";

var assert = require("assert");
var ASCLV2 = require("../frontend/reader-v2.js");

var KEY_RAW = 4;
var SOLID = 1;

var COLS = 37, ROWS = 29, PAL_COUNT = 32;

function block(tag, palette, payload) {
  var pal = palette || Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  var result;
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  payload.copy(body, 3 + pal.length);
  result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function makeAscl(frames, tileSize) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i, out;
  header.write("ASCL", 0, "ascii");
  header[4] = 2;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(COLS, 8);
  header.writeUInt16LE(ROWS, 10);
  header.writeUInt16LE(PAL_COUNT, 12);
  header.writeUInt32LE(frames.length, 14);
  header[18] = 0;
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  header[26] = tileSize;
  header[27] = 1;
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  out = Buffer.concat([header, table].concat(frames));
  out.writeUInt32LE(ASCLV2.crc32v2(out), 28);
  return out;
}

function palette(count) {
  var out = Buffer.alloc(count * 3), i;
  for (i = 0; i < count; i++) {
    out[i * 3] = i * 7;
    out[i * 3 + 1] = 255 - i * 5;
    out[i * 3 + 2] = i * 3;
  }
  return out;
}

function solidKeyFixture(tileSize) {
  var tileCols = Math.ceil(COLS / tileSize);
  var tileRows = Math.ceil(ROWS / tileSize);
  var tileCount = tileCols * tileRows;
  var payload = Buffer.alloc(tileCount * 2);
  var expected = Buffer.alloc(COLS * ROWS);
  var t, tx, ty, x0, y0, x1, y1, x, y, value;
  for (t = 0; t < tileCount; t++) {
    value = t % PAL_COUNT;
    payload[t * 2] = SOLID;
    payload[t * 2 + 1] = value;
    tx = t % tileCols;
    ty = Math.floor(t / tileCols);
    x0 = tx * tileSize;
    y0 = ty * tileSize;
    x1 = Math.min(x0 + tileSize, COLS);
    y1 = Math.min(y0 + tileSize, ROWS);
    for (y = y0; y < y1; y++) {
      for (x = x0; x < x1; x++) expected[y * COLS + x] = value;
    }
  }
  return {
    encoded: makeAscl([block(KEY_RAW, palette(PAL_COUNT), payload)], tileSize),
    expected: expected,
    tileCount: tileCount
  };
}

function parse(buf) {
  return ASCLV2.parse(buf.buffer, buf.byteOffset, buf.byteLength);
}

var SIZES = [4, 8, 12, 16, 24, 32];
var i, fixture, reader;
for (i = 0; i < SIZES.length; i++) {
  fixture = solidKeyFixture(SIZES[i]);
  reader = parse(fixture.encoded);
  assert.strictEqual(reader.tileSize, SIZES[i]);
  assert.strictEqual(reader.tileCount, fixture.tileCount);
  reader.seek(0);
  assert.deepStrictEqual(Buffer.from(reader.cells), fixture.expected,
    "matriz incorrecta con tile_size " + SIZES[i]);
}

var BAD = [0, 1, 3, 33, 64, 255];
for (i = 0; i < BAD.length; i++) {
  fixture = solidKeyFixture(Math.max(4, Math.min(32, BAD[i])) || 4);
  /* mismo contenido, header adulterado al tamano invalido + CRC recalculado */
  fixture.encoded[26] = BAD[i];
  fixture.encoded.writeUInt32LE(ASCLV2.crc32v2(fixture.encoded), 28);
  assert.throws(function () { parse(fixture.encoded); }, /tile_size/,
    "tile_size " + BAD[i] + " deberia rechazarse");
}

console.log("OK reader-v2 tile_size: 6 tamanos abren y decodifican; " +
  BAD.length + " invalidos rechazados");
