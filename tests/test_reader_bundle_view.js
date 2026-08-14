"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var ASCL = require("../frontend/reader.js");

var source = fs.readFileSync(path.join(__dirname, "fixtures", "test_pixel.ascl"));
var bundle = new ArrayBuffer(16 + source.length);
var bytes = new Uint8Array(bundle);
var magic = "ASCLVID1";
var i;
for (i = 0; i < magic.length; i++) { bytes[i] = magic.charCodeAt(i); }
new DataView(bundle).setUint32(8, source.length, true);
new DataView(bundle).setUint32(12, 0, true);
bytes.set(new Uint8Array(source.buffer, source.byteOffset, source.byteLength), 16);

var reader = ASCL.parse(bundle, 16, source.length);
assert.strictEqual(reader.bytes.buffer, bundle);
assert.strictEqual(reader.bytes.byteOffset, 16);
reader.seek(0);
assert.strictEqual(reader.header.version, 1);
assert.strictEqual(reader.header.mode, ASCL.MODE_PIXEL);

console.log("reader bundle view test: OK");
