#!/usr/bin/env node
/*
 * bench_inflate.js — medicion de tiempo de una implementacion de inflate.js.
 *
 * Uso: node tools/bench_inflate.js <ruta-a-inflate.js> [repeticiones]
 *
 * Corpus determinista (semilla fija) con tres perfiles representativos del
 * payload ASCL: indices con rachas largas (SOLID/celdas repetidas), indices
 * con ruido moderado (gradientes + dither) y bytes poco compresibles.
 * Comprime con el zlib de Node (mismo stream que produce el encoder) y mide
 * ASCL_inflateZlibInto sobre un buffer preasignado, como hace el reader.
 *
 * Es herramienta offline de medicion: no corre en el TV ni en la regresion.
 */
"use strict";

var path = require("path");
var zlib = require("zlib");

function usage() {
  console.error("uso: node tools/bench_inflate.js <inflate.js> [repeticiones]");
  process.exit(2);
}

var target = process.argv[2];
if (!target) usage();
var repeats = parseInt(process.argv[3] || "300", 10);
if (!(repeats > 0)) usage();

var impl = require(path.resolve(target));
var inflateInto = impl.ASCL_inflateZlibInto;
if (typeof inflateInto !== "function") {
  console.error("el modulo no exporta ASCL_inflateZlibInto");
  process.exit(2);
}

/* PRNG determinista (xorshift32) para un corpus reproducible. */
function makeRng(seed) {
  var s = seed >>> 0;
  return function () {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s;
  };
}

function runsProfile(size) {
  var rng = makeRng(0xA5C11), out = new Uint8Array(size), i = 0, value, run;
  while (i < size) {
    value = rng() & 31;
    run = 4 + (rng() % 220);
    while (run-- && i < size) out[i++] = value;
  }
  return out;
}

function gradientProfile(size) {
  var rng = makeRng(0xBEEF1), out = new Uint8Array(size), i;
  for (i = 0; i < size; i++) {
    out[i] = ((i & 255) + (rng() % 7)) & 255;
  }
  return out;
}

function noiseProfile(size) {
  var rng = makeRng(0xC0FFE), out = new Uint8Array(size), i;
  for (i = 0; i < size; i++) out[i] = rng() & 255;
  return out;
}

var CASES = [
  { name: "rachas ", raw: runsProfile(253 * 1024) },
  { name: "gradien", raw: gradientProfile(253 * 1024) },
  { name: "ruido  ", raw: noiseProfile(64 * 1024) }
];

var i, c, compressed, out, k, n, t0, t1, ms, total = 0;
for (i = 0; i < CASES.length; i++) {
  c = CASES[i];
  compressed = new Uint8Array(zlib.deflateSync(Buffer.from(c.raw), { level: 9 }));
  out = new Uint8Array(c.raw.length);
  n = inflateInto(compressed, out, out.length);
  if (n !== c.raw.length) {
    console.error("longitud incorrecta en " + c.name);
    process.exit(1);
  }
  for (k = 0; k < c.raw.length; k += 1024) {
    if (out[k] !== c.raw[k]) {
      console.error("contenido incorrecto en " + c.name);
      process.exit(1);
    }
  }
  /* calentamiento */
  for (k = 0; k < 10; k++) inflateInto(compressed, out, out.length);
  t0 = process.hrtime();
  for (k = 0; k < repeats; k++) inflateInto(compressed, out, out.length);
  t1 = process.hrtime(t0);
  ms = t1[0] * 1000 + t1[1] / 1e6;
  total += ms;
  console.log(c.name + "  " + c.raw.length + " B  x" + repeats +
              "  " + ms.toFixed(1) + " ms  (" +
              ((c.raw.length * repeats / 1048576) / (ms / 1000)).toFixed(1) +
              " MB/s)");
}
console.log("total    " + total.toFixed(1) + " ms");
