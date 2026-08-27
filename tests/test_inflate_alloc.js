/*
 * W-07: cero allocaciones tipadas por frame en el camino estable de inflate.
 *
 * Instrumenta los constructores TypedArray globales y subarray tras un frame
 * de calentamiento (arboles fijos + buffers compartidos ya creados) y decodifica
 * 50 frames zlib con bloques dinamicos: ninguna llamada debe crear un typed
 * array nuevo ni un subarray.
 */
"use strict";

var path = require("path");
var zlib = require("zlib");

var impl = require(path.join(__dirname, "..", "frontend", "inflate.js"));

function buildPayload(size) {
  var raw = Buffer.alloc(size);
  var value = 0;
  for (var i = 0; i < size; i++) {
    value = (value + 7 + ((i >> 5) & 3)) & 255;
    raw[i] = value;
  }
  return raw;
}

var raw = buildPayload(96 * 1024);
var compressed = new Uint8Array(zlib.deflateSync(raw, { level: 9 }));
var out = new Uint8Array(raw.length);

var n = impl.ASCL_inflateZlibInto(compressed, out, out.length);
if (n !== raw.length) {
  console.error("FAIL: longitud de calentamiento incorrecta");
  process.exit(1);
}
for (var v = 0; v < raw.length; v++) {
  if (out[v] !== raw[v]) {
    console.error("FAIL: contenido incorrecto en " + v);
    process.exit(1);
  }
}

var allocations = 0;
var RealU8 = global.Uint8Array;
var RealU16 = global.Uint16Array;
var RealU32 = global.Uint32Array;
var realSubarray = RealU8.prototype.subarray;

function wrapConstructor(Real) {
  var wrapped = function (a, b, c) {
    allocations++;
    if (c !== undefined) return new Real(a, b, c);
    if (b !== undefined) return new Real(a, b);
    return new Real(a);
  };
  wrapped.prototype = Real.prototype;
  return wrapped;
}

global.Uint8Array = wrapConstructor(RealU8);
global.Uint16Array = wrapConstructor(RealU16);
global.Uint32Array = wrapConstructor(RealU32);
RealU8.prototype.subarray = function () {
  allocations++;
  return realSubarray.apply(this, arguments);
};

var frames = 50;
var total = 0;
for (var k = 0; k < frames; k++) {
  total += impl.ASCL_inflateZlibInto(compressed, out, out.length);
}

global.Uint8Array = RealU8;
global.Uint16Array = RealU16;
global.Uint32Array = RealU32;
RealU8.prototype.subarray = realSubarray;

if (total !== frames * raw.length) {
  console.error("FAIL: longitudes incorrectas bajo instrumentacion");
  process.exit(1);
}
if (allocations !== 0) {
  console.error("FAIL: " + allocations +
    " allocaciones tipadas/subarrays en " + frames + " frames del camino estable");
  process.exit(1);
}
console.log("OK inflate alloc: 0 allocaciones tipadas en " + frames +
  " frames dinamicos");
