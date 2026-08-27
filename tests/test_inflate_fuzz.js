"use strict";
/* W-05: fuzzing determinista permanente de inflate.js.
 *
 * Corpus: streams zlib validos mutados con un PRNG de semilla fija. El gate
 * exige: cero cuelgues, cero accesos fuera de rango y que todo rechazo sea
 * una excepcion tipada del propio inflate. Debe correr en CI, por eso el
 * numero de iteraciones esta acotado. */

var assert = require("assert");
var zlib = require("zlib");
var inflate = require("../frontend/inflate.js");

/* PRNG determinista (mulberry32): la corrida es identica en toda maquina. */
function makeRandom(seed) {
  var state = seed >>> 0;
  return function () {
    state = (state + 0x6D2B79F5) >>> 0;
    var t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function corpus() {
  var items = [], i;
  var a = Buffer.alloc(4096);
  for (i = 0; i < a.length; i++) a[i] = i & 255;          /* rampa periodica */
  var b = Buffer.alloc(2048);                              /* ceros */
  var c = Buffer.alloc(3000);
  for (i = 0; i < c.length; i++) c[i] = (i * 7919) & 255;  /* pseudoruido */
  var d = Buffer.from("ASCILINE ".repeat(300));            /* texto repetitivo */
  [a, b, c, d].forEach(function (raw) {
    items.push({ raw: raw, z: zlib.deflateSync(raw, { level: 9 }) });
    items.push({ raw: raw, z: zlib.deflateSync(raw, { level: 1 }) });
    items.push({ raw: raw, z: zlib.deflateSync(raw, { level: 0 }) }); /* stored */
  });
  return items;
}

var ITERATIONS = 4000;
var SLOW_MS = 500;

(function fuzz() {
  var random = makeRandom(0x5EED);
  var items = corpus();
  var accepted = 0, rejected = 0, slow = 0, i, item, mutated, pos, start;
  for (i = 0; i < ITERATIONS; i++) {
    item = items[i % items.length];
    mutated = Buffer.from(item.z);
    /* 1 a 4 mutaciones por iteracion: byte aleatorio, bitflip o truncado. */
    var edits = 1 + Math.floor(random() * 4), e, kind;
    for (e = 0; e < edits; e++) {
      kind = random();
      if (kind < 0.45) {
        pos = Math.floor(random() * mutated.length);
        mutated[pos] = Math.floor(random() * 256);
      } else if (kind < 0.9) {
        pos = Math.floor(random() * mutated.length);
        mutated[pos] ^= 1 << Math.floor(random() * 8);
      } else if (mutated.length > 8) {
        mutated = mutated.subarray(0, 8 + Math.floor(random() * (mutated.length - 8)));
      }
    }
    start = Date.now();
    try {
      var out = inflate.ASCL_inflateZlib(mutated, item.raw.length);
      accepted++;
      assert(out.length <= item.raw.length, "salida excede maxLength");
    } catch (error) {
      rejected++;
      assert(error instanceof Error, "rechazo sin Error tipado");
      assert(!(error instanceof RangeError), "RangeError = acceso fuera de rango");
      assert(!(error instanceof TypeError), "TypeError = estado interno roto");
    }
    if (Date.now() - start > SLOW_MS) slow++;
  }
  assert.strictEqual(slow, 0, slow + " iteraciones lentas (posible cuelgue)");
  console.log("fuzz: " + ITERATIONS + " mutaciones, " + accepted +
              " aceptadas, " + rejected + " rechazadas tipadas, 0 lentas");
}());

(function roundTripExact() {
  /* Sanidad: todo el corpus limpio decodifica byte-exacto. */
  corpus().forEach(function (item, index) {
    var out = inflate.ASCL_inflateZlib(item.z, item.raw.length);
    assert.strictEqual(out.length, item.raw.length, "longitud item " + index);
    for (var i = 0; i < out.length; i++) {
      if (out[i] !== item.raw[i]) assert.fail("byte " + i + " item " + index);
    }
  });
  console.log("round-trip exacto del corpus limpio: OK");
}());

(function bombBounded() {
  var bomb = zlib.deflateSync(Buffer.alloc(8 * 1024 * 1024), { level: 9 });
  var start = Date.now();
  assert.throws(function () { inflate.ASCL_inflateZlib(bomb, 1024); },
                /maxLength|salida/);
  assert(Date.now() - start < 1000, "la bomba tardo demasiado en rechazarse");
  console.log("bomba 8MB con maxLength=1024 rechazada en <1s: OK");
}());

(function structuralCases() {
  /* Casos dirigidos que el fuzzing aleatorio puede no tocar. */
  var good = zlib.deflateSync(Buffer.from([1, 2, 3, 4]));
  var cases = [
    { name: "vacio", data: Buffer.alloc(0) },
    { name: "solo CMF", data: Buffer.from([0x78]) },
    { name: "FDICT activo", data: (function () {
        var c = Buffer.from(good); c[1] |= 0x20;
        /* rehacer FCHECK para aislar el rechazo de FDICT */
        var v = (c[0] << 8) | (c[1] & 0xE0);
        c[1] = (c[1] & 0xE0) | (31 - (v % 31)) % 31;
        return c; }()) },
    { name: "CM invalido", data: (function () {
        var c = Buffer.from(good); c[0] = (c[0] & 0xF0) | 0x00; return c; }()) },
    { name: "adler roto", data: (function () {
        var c = Buffer.from(good); c[c.length - 1] ^= 0xFF; return c; }()) },
    { name: "bytes extra", data: Buffer.concat([good, Buffer.from([0])]) },
    { name: "truncado a mitad", data: good.subarray(0, good.length >> 1) }
  ];
  cases.forEach(function (item) {
    assert.throws(function () { inflate.ASCL_inflateZlib(item.data, 64); },
                  Error, "no rechazo: " + item.name);
  });
  console.log("casos estructurales dirigidos (" + cases.length + "): OK");
}());

console.log("inflate fuzz tests: OK");
