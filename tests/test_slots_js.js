/*
 * E-07: frontend/slots.js debe aceptar y rechazar exactamente los mismos
 * archivos que tools/make_slots.py. Los fixtures (valido + 8 negativos) los
 * genera test_make_slots.py en tests/fixtures/slots-generated/; run_all.py
 * corre Python antes que las suites JS, asi que aca ya existen.
 */
"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var SLOTS = require("../frontend/slots.js");

var DIR = path.join(__dirname, "fixtures", "slots-generated");

if (!fs.existsSync(path.join(DIR, "context.bin"))) {
  console.log("SKIP slots-js: fixtures no generados; " +
    "correr primero la suite Python (tests/run_all.py lo hace en orden)");
  process.exit(0);
}

var context = fs.readFileSync(path.join(DIR, "context.bin"));
var COLS = context.readUInt16LE(0);
var ROWS = context.readUInt16LE(2);
var FRAMES = context.readUInt32LE(4);
var RESERVED_RGB = new Uint8Array(context.subarray(8, 38));

var EXPECTED = {
  "valid": null,
  "bad-fuera-de-grilla": /fuera de la grilla/,
  "bad-solape": /se solapan/,
  "bad-n-slots": /n_slots supera/,
  "bad-area": /area activa/,
  "bad-glifo": /fuera de 246/,
  "bad-slot-inexistente": /inexistente/,
  "bad-slot-duplicado": /dos campos/,
  "bad-reserved-rgb": /no coincide/
};

var names = Object.keys(EXPECTED);
var checked = 0;
for (var i = 0; i < names.length; i++) {
  var name = names[i];
  var file = path.join(DIR, name + ".slots");
  assert.ok(fs.existsSync(file), "falta fixture " + name);
  var bytes = new Uint8Array(fs.readFileSync(file));
  if (EXPECTED[name] === null) {
    var parsed = SLOTS.ASCL_parseSlots(bytes, COLS, ROWS, FRAMES, RESERVED_RGB);
    assert.strictEqual(parsed.slots.length, 4);
    assert.strictEqual(parsed.fields.length, 2);
    assert.strictEqual(parsed.glyphW, 8);
    assert.strictEqual(parsed.glyphH, 12);
    assert.strictEqual(parsed.fields[0].max, 99);
  } else {
    (function (regex, label, data) {
      assert.throws(function () {
        SLOTS.ASCL_parseSlots(data, COLS, ROWS, FRAMES, RESERVED_RGB);
      }, regex, label + " deberia rechazarse");
    })(EXPECTED[name], name, bytes);
  }
  checked++;
}

/* sin carga parcial: un archivo truncado o mutado sin CRC nuevo se rechaza */
var validBytes = new Uint8Array(fs.readFileSync(path.join(DIR, "valid.slots")));
assert.throws(function () {
  SLOTS.ASCL_parseSlots(validBytes.subarray(0, validBytes.length - 4),
    COLS, ROWS, FRAMES, RESERVED_RGB);
});
var tampered = new Uint8Array(validBytes);
tampered[54] ^= 1;
assert.throws(function () {
  SLOTS.ASCL_parseSlots(tampered, COLS, ROWS, FRAMES, RESERVED_RGB);
}, /CRC/);

console.log("OK slots-js: " + checked + " fixtures con el mismo veredicto " +
  "que el validador Python");
