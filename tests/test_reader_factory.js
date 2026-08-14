"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var zlib = require("zlib");
var factory = require("../frontend/reader-factory.js");

function crcTable() {
  var table = new Uint32Array(256), i, c, k;
  for (i = 0; i < 256; i++) {
    c = i;
    for (k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    table[i] = c >>> 0;
  }
  return table;
}

function crcRange(bytes, crc, start, end, table) {
  var i;
  for (i = start; i < end; i++) crc = table[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
  return crc;
}

function crcV2(buffer) {
  var bytes = new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  var table = crcTable(), crc = 0xffffffff;
  crc = crcRange(bytes, crc, 0, 28, table);
  crc = crcRange(bytes, crc, 32, bytes.length, table);
  return (crc ^ 0xffffffff) >>> 0;
}

function block(tag, palette, payload) {
  var body = Buffer.alloc(3 + palette.length + payload.length);
  body[0] = tag;
  body.writeUInt16LE(palette.length / 3, 1);
  palette.copy(body, 3);
  payload.copy(body, 3 + palette.length);
  var out = Buffer.alloc(4 + body.length);
  out.writeUInt32LE(body.length, 0);
  body.copy(out, 4);
  return out;
}

function make(version) {
  var palette = Buffer.from([0, 0, 0, 255, 255, 255]);
  var payload = version === 1 ? Buffer.from([1, 1, 1, 1]) : Buffer.from([1, 1]);
  var frame = block(version === 1 ? 0 : 4, palette, payload);
  var header = Buffer.alloc(32), table = Buffer.alloc(4), result;
  header.write("ASCL", 0, "ascii");
  header[4] = version;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(2, 8);
  header.writeUInt16LE(2, 10);
  header.writeUInt16LE(2, 12);
  header.writeUInt32LE(1, 14);
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  if (version === 2) { header[26] = 16; header[27] = 1; }
  table.writeUInt32LE(36, 0);
  result = Buffer.concat([header, table, frame]);
  if (version === 1) result.writeUInt32LE(zlib.crc32 ? zlib.crc32(result.subarray(32)) : 0, 28);
  else result.writeUInt32LE(crcV2(result), 28);
  return result;
}

/* Node no ofrece zlib.crc32 en todas sus versiones; CRC v1 cero es legacy valido. */
(function dispatchesBothVersions() {
  var v1 = make(1), v2 = make(2), reader;
  reader = factory.parse(v1.buffer, v1.byteOffset, v1.byteLength);
  reader.seek(0);
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), [1, 1, 1, 1]);
  assert.strictEqual(reader.header.version, 1);
  reader = factory.parse(v2.buffer, v2.byteOffset, v2.byteLength);
  reader.seek(0);
  assert.deepStrictEqual(Array.prototype.slice.call(reader.cells), [1, 1, 1, 1]);
  assert.strictEqual(reader.header.version, 2);
}());

(function rejectsUnknownVersion() {
  var invalid = make(1);
  invalid[4] = 9;
  assert.throws(function () {
    factory.parse(invalid.buffer, invalid.byteOffset, invalid.byteLength);
  }, /version no soportada/);
}());

(function sourceRemainsLegacyCompatible() {
  var source = fs.readFileSync(
    path.join(__dirname, "..", "frontend", "reader-factory.js"), "utf8");
  assert.strictEqual(/\b(?:const|let|class)\b|=>|`/.test(source), false);
  assert.doesNotThrow(function () { new Function(source); });
}());

console.log("reader factory tests: OK");
