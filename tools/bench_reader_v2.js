#!/usr/bin/env node
/*
 * bench_reader_v2.js — medicion de _walkRegional (W-09) de un reader-v2.js.
 *
 * Uso: node tools/bench_reader_v2.js <ruta-a-reader-v2.js> [repeticiones]
 *
 * Construye un archivo ASCL v2 sintetico determinista (224x224, tiles 16x16,
 * paleta global de 32) y mide las dos pasadas reales del decoder (validacion +
 * aplicacion) sobre tres perfiles de stream regional: keyframe mixto
 * (PAL8/PACK1/PACK2/PAL4/SOLID), delta SPARSE+SKIP y delta MASK+SKIP.
 * Los deltas alternan dos streams A/B para que ninguna repeticion produzca
 * escrituras identicas (que el validador rechaza).
 *
 * Es herramienta offline de medicion: no corre en el TV ni en la regresion.
 */
"use strict";

var path = require("path");

function usage() {
  console.error("uso: node tools/bench_reader_v2.js <reader-v2.js> [repeticiones]");
  process.exit(2);
}

var target = process.argv[2];
if (!target) usage();
var repeats = parseInt(process.argv[3] || "400", 10);
if (!(repeats > 0)) usage();

var ASCLV2 = require(path.resolve(target));
if (typeof ASCLV2.parse !== "function" || typeof ASCLV2.crc32v2 !== "function") {
  console.error("el modulo no exporta parse/crc32v2");
  process.exit(2);
}

var COLS = 224, ROWS = 224, TILE = 16;
var TILE_COLS = COLS / TILE, TILE_COUNT = TILE_COLS * (ROWS / TILE);
var NPIX = TILE * TILE;
var PAL_ENTRIES = 32;

var SKIP = 0, SOLID = 1, SPARSE = 2, MASK = 3, PACK1 = 4, PACK2 = 5, PAL4 = 6, PAL8 = 7;

function makeRng(seed) {
  var s = seed >>> 0;
  return function () {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s;
  };
}

function uvar(value, out) {
  do {
    var part = value % 128;
    value = Math.floor(value / 128);
    out.push(part | (value ? 128 : 0));
  } while (value);
}

/* Keyframe mixto: cicla PAL8, PACK1, PACK2, PAL4 y SOLID por tile. */
function buildKeyStream() {
  var rng = makeRng(0xA5C11), out = [], t, i, kind, byteAcc, bitPos, code;
  for (t = 0; t < TILE_COUNT; t++) {
    kind = t % 5;
    if (kind === 0) {
      out.push(PAL8);
      for (i = 0; i < NPIX; i++) out.push(rng() % 16);
    } else if (kind === 1) {
      out.push(PACK1, 0, 1);
      byteAcc = 0; bitPos = 0;
      for (i = 0; i < NPIX; i++) {
        byteAcc |= (rng() & 1) << bitPos;
        bitPos++;
        if (bitPos === 8) { out.push(byteAcc); byteAcc = 0; bitPos = 0; }
      }
      if (bitPos) out.push(byteAcc);
    } else if (kind === 2) {
      out.push(PACK2, 4, 2, 3, 5, 7);
      byteAcc = 0; bitPos = 0;
      for (i = 0; i < NPIX; i++) {
        code = rng() & 3;
        byteAcc |= code << bitPos;
        bitPos += 2;
        if (bitPos === 8) { out.push(byteAcc); byteAcc = 0; bitPos = 0; }
      }
      if (bitPos) out.push(byteAcc);
    } else if (kind === 3) {
      out.push(PAL4, 8, 1, 2, 3, 4, 6, 8, 10, 12);
      byteAcc = 0; bitPos = 0;
      for (i = 0; i < NPIX; i++) {
        code = rng() % 8;
        byteAcc |= code << bitPos;
        bitPos += 4;
        if (bitPos === 8) { out.push(byteAcc); byteAcc = 0; bitPos = 0; }
      }
      if (bitPos) out.push(byteAcc);
    } else {
      out.push(SOLID, 9);
    }
  }
  return new Uint8Array(out);
}

/* Delta: tiles pares con el comando pedido, impares saltados en runs. */
function buildSparseStream(value) {
  var out = [], t, i;
  for (t = 0; t < TILE_COUNT; t++) {
    if (t % 2) { out.push(SKIP); uvar(1, out); continue; }
    out.push(SPARSE);
    uvar(32, out);
    for (i = 0; i < 32; i++) {
      uvar(i * 8, out);
      out.push(value);
    }
  }
  return new Uint8Array(out);
}

function buildMaskStream(value) {
  var out = [], t, i;
  for (t = 0; t < TILE_COUNT; t++) {
    if (t % 2) { out.push(SKIP); uvar(1, out); continue; }
    out.push(MASK);
    for (i = 0; i < NPIX / 8; i++) out.push(i % 2 ? 0x11 : 0x44);
    for (i = 0; i < 64; i++) out.push(value);
  }
  return new Uint8Array(out);
}

function blockBytes(tag, palette, payload) {
  var palLen = palette ? palette.length : 0;
  var body = new Uint8Array(3 + palLen + payload.length);
  var out = new Uint8Array(4 + body.length);
  var view = new DataView(out.buffer);
  body[0] = tag;
  body[1] = (palLen / 3) & 255;
  body[2] = (palLen / 3) >>> 8;
  if (palette) body.set(palette, 3);
  body.set(payload, 3 + palLen);
  view.setUint32(0, body.length, true);
  out.set(body, 4);
  return out;
}

function makeV2(frames) {
  var header = new Uint8Array(32), i, total = 32 + frames.length * 4, offset;
  var view, out, cursor;
  for (i = 0; i < frames.length; i++) total += frames[i].length;
  out = new Uint8Array(total);
  view = new DataView(out.buffer);
  header[0] = 65; header[1] = 83; header[2] = 67; header[3] = 76; /* ASCL */
  header[4] = 2;   /* version v2 */
  header[5] = 3;   /* modo pixel */
  header[6] = 12;  /* offset table + paleta global */
  header[7] = 15;
  header[26] = TILE;
  header[27] = 1;  /* codec regional */
  out.set(header, 0);
  view.setUint16(8, COLS, true);
  view.setUint16(10, ROWS, true);
  view.setUint16(12, PAL_ENTRIES, true);
  view.setUint32(14, frames.length, true);
  out[18] = 0; out[19] = 3;
  view.setUint32(20, 32, true);
  view.setUint16(24, 1000, true);
  offset = 32 + frames.length * 4;
  for (i = 0; i < frames.length; i++) {
    view.setUint32(32 + i * 4, offset, true);
    offset += frames[i].length;
  }
  cursor = 32 + frames.length * 4;
  for (i = 0; i < frames.length; i++) {
    out.set(frames[i], cursor);
    cursor += frames[i].length;
  }
  view.setUint32(28, ASCLV2.crc32v2(out), true);
  return out;
}

var palette = new Uint8Array(PAL_ENTRIES * 3);
for (var pi = 0; pi < PAL_ENTRIES; pi++) {
  palette[pi * 3] = pi * 7; palette[pi * 3 + 1] = 255 - pi * 5; palette[pi * 3 + 2] = pi * 3;
}

var keyStream = buildKeyStream();
var encoded = makeV2([blockBytes(4 /* KEY_RAW */, palette, keyStream)]);
var reader = ASCLV2.parse(encoded.buffer, encoded.byteOffset, encoded.byteLength);
reader.seek(0);

var CASES = [
  { name: "key mix ", keyframe: true, streams: [keyStream] },
  { name: "sparse  ", keyframe: false, streams: [buildSparseStream(20), buildSparseStream(21)] },
  { name: "mask    ", keyframe: false, streams: [buildMaskStream(24), buildMaskStream(25)] }
];

var ci, c, k, s, t0, t1, ms, total = 0;
for (ci = 0; ci < CASES.length; ci++) {
  c = CASES[ci];
  /* calentamiento + verificacion de que ambas pasadas aceptan el stream */
  for (k = 0; k < 6; k++) {
    s = c.streams[k % c.streams.length];
    reader._walkRegional(s, s.length, c.keyframe, PAL_ENTRIES, false);
    reader._walkRegional(s, s.length, c.keyframe, PAL_ENTRIES, true);
  }
  t0 = process.hrtime();
  for (k = 0; k < repeats; k++) {
    s = c.streams[k % c.streams.length];
    reader._walkRegional(s, s.length, c.keyframe, PAL_ENTRIES, false);
    reader._walkRegional(s, s.length, c.keyframe, PAL_ENTRIES, true);
  }
  t1 = process.hrtime(t0);
  ms = t1[0] * 1000 + t1[1] / 1e6;
  total += ms;
  console.log(c.name + " " + c.streams[0].length + " B  x" + repeats + "  " +
              ms.toFixed(1) + " ms  (" + (ms / repeats * 1000).toFixed(1) +
              " us/frame)");
}
console.log("total    " + total.toFixed(1) + " ms");
