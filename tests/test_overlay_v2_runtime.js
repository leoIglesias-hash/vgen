"use strict";
/* INT-003-D: semantica v2 del runtime del overlay (frontend/overlay.js)
 * sobre un lector sintetico con emulacion de deltas:
 *  - campos de eleccion con digito de presencia (todo-o-nada, canonicidad);
 *  - NONE: un slot sin valor no se pinta, no guarda base y NO marca sucio;
 *  - ventanas disjuntas sobre posiciones distintas y transicion de ventana;
 *  - control negativo: saltear beforeSeek() con cadena delta diverge;
 *  - identidad de buffers (sin allocaciones en el camino caliente);
 *  - rechazos de attach especificos de v2;
 *  - datachannel sin cambios: la longitud del payload v2 sale de digitCount.
 * La equivalencia byte a byte con la referencia Python sobre un clip REAL
 * la cubre test_overlay_v2_cross.js. */

var assert = require("assert");
var OVERLAY = require("../frontend/overlay.js");
var DC = require("../frontend/datachannel.js");

var COLS = 40, ROWS = 20, FRAMES = 6, NONE = 65535;

/* ---- lector sintetico con deltas: seek(f) desde f-1 escribe SOLO las
 * celdas que cambian entre los frames pristinos (como una cadena DELTA);
 * cualquier otro seek copia completo (keyframe). ---- */
function pristineFrame(f) {
  var cells = new Uint8Array(COLS * ROWS), i;
  for (i = 0; i < cells.length; i++) {
    cells[i] = (i % 100) + ((f >= 3 && i % 2 === 0) ? 50 : 0);
  }
  return cells;
}

function MiniReader() {
  var i;
  this.header = { cols: COLS, rows: ROWS, palSize: 256, nFrames: FRAMES };
  this.cells = new Uint8Array(COLS * ROWS);
  this.palette = new Uint8Array(768);
  for (i = 0; i < 768; i++) this.palette[i] = (i * 7) % 256;
  this.paletteEntries = 256;
  this.decodedIndex = -1;
  this.frames = [];
  for (i = 0; i < FRAMES; i++) this.frames.push(pristineFrame(i));
  this.dirty = [];
}
MiniReader.prototype.seek = function (f) {
  var target = this.frames[f], i;
  if (this.decodedIndex >= 0 && f === this.decodedIndex + 1) {
    var previous = this.frames[this.decodedIndex];
    for (i = 0; i < target.length; i++) {
      if (target[i] !== previous[i]) this.cells[i] = target[i];
    }
  } else {
    for (i = 0; i < target.length; i++) this.cells[i] = target[i];
  }
  this.decodedIndex = f;
};
MiniReader.prototype.markRectDirty = function (x, y, w, h) {
  this.dirty.push(x + "," + y + "," + w + "," + h);
};

/* ---- metadata v2 sintetica (forma de ASCL_parseSlots v2) ---- */
function digitPatch(digit) {
  var data = new Uint8Array(12), k;
  for (k = 0; k < 12; k++) {
    data[k] = k === 0 ? 255 : 224 + ((digit + k) % 31);
  }
  return { w: 3, h: 4, data: data };
}

function choicePatch(variant) {
  var data = new Uint8Array(20), k;
  for (k = 0; k < 20; k++) data[k] = k === 0 ? 255 : 230 + variant;
  return { w: 5, h: 4, data: data };
}

function reservedTail(reader) {
  var rgb = new Uint8Array(96), i;
  for (i = 0; i < 96; i++) rgb[i] = reader.palette[672 + i];
  return rgb;
}

function makeMeta(reader) {
  var patches = [], d;
  for (d = 0; d < 10; d++) patches.push(digitPatch(d));
  var empty = new Uint8Array(12), k;
  for (k = 0; k < 12; k++) empty[k] = 255;
  patches.push({ w: 3, h: 4, data: empty });          /* 10: vacio */
  patches.push(choicePatch(0));                        /* 11 */
  patches.push(choicePatch(1));                        /* 12 */
  return {
    version: 2, palReserved: 32, reservedRgb: reservedTail(reader),
    patches: patches,
    slots: [
      { x: 2, y: 2, w: 3, h: 4, start: 0, end: 5, flags: 1 },
      { x: 10, y: 8, w: 5, h: 4, start: 0, end: 2, flags: 1 },
      { x: 20, y: 8, w: 5, h: 4, start: 3, end: 5, flags: 1 }
    ],
    fields: [
      { fieldId: 1, kind: 0, slotIds: [0], min: 0, max: 9, pad: 1,
        patchBase: 0 },
      { fieldId: 2, kind: 1, slotIds: [1], min: 0, max: 1, pad: 0,
        patchBase: 11 },
      { fieldId: 3, kind: 1, slotIds: [2], min: 0, max: 1, pad: 0,
        patchBase: 11 }
    ]
  };
}

function paint(cells, meta, slotIndex, patchIndex) {
  var slot = meta.slots[slotIndex], patch = meta.patches[patchIndex];
  var gy, gx, value;
  for (gy = 0; gy < slot.h; gy++) {
    for (gx = 0; gx < slot.w; gx++) {
      value = patch.data[gy * slot.w + gx];
      if (value !== 255) cells[(slot.y + gy) * COLS + slot.x + gx] = value;
    }
  }
}

function expectFrame(meta, frame, paints) {
  var cells = new Uint8Array(pristineFrame(frame)), i;
  for (i = 0; i < paints.length; i++) {
    paint(cells, meta, paints[i][0], paints[i][1]);
  }
  return cells;
}

function same(a, b) {
  return Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0;
}

function step(overlay, reader, frame) {
  overlay.beforeSeek();
  reader.seek(frame);
  overlay.afterSeek();
}

/* ================= flujo principal ================= */
var reader = new MiniReader();
var meta = makeMeta(reader);
var overlay = OVERLAY.attach(reader, meta);
assert.ok(overlay, "attach v2");
assert.strictEqual(overlay.digitCount, 5, "wire = 1 + (1+1) + (1+1)");
assert.strictEqual(overlay.values[0], 10, "digitos arrancan en vacio");
assert.strictEqual(overlay.values[1], NONE, "eleccion arranca en NONE");
assert.strictEqual(overlay.values[2], NONE);

var baseRef = overlay.base, valuesRef = overlay.values;

/* cargas: todo-o-nada con presencia y canonicidad */
assert.strictEqual(overlay.setValues("31100"), true);
assert.deepStrictEqual(Array.prototype.slice.call(overlay.values),
  [3, 12, NONE]);
assert.strictEqual(overlay.setValues("3110"), false, "longitud");
assert.strictEqual(overlay.setValues("32100"), false, "presencia > 1");
assert.strictEqual(overlay.setValues("31200"), false, "eleccion fuera de rango");
assert.strictEqual(overlay.setValues("31101"), false,
  "presencia 0 exige valor 0 (canonico)");
assert.deepStrictEqual(Array.prototype.slice.call(overlay.values),
  [3, 12, NONE], "dato invalido conserva el estado");

/* frames 0..2: digitos + eleccion presente, byte-exacto */
var f;
for (f = 0; f <= 2; f++) {
  step(overlay, reader, f);
  assert.ok(same(reader.cells, expectFrame(meta, f, [[0, 3], [1, 12]])),
    "frame " + f + " byte-exacto");
}

/* frame 3: el slot 1 sale de ventana (se restaura), el 2 esta en NONE:
 * la zona queda video base; NONE no guarda base ni marca sucio */
reader.dirty = [];
step(overlay, reader, 3);
assert.ok(same(reader.cells, expectFrame(meta, 3, [[0, 3]])),
  "frame 3: solo los digitos siguen pintados");
assert.ok(reader.dirty.indexOf("2,2,3,4") !== -1,
  "el rect de digitos se marca");
assert.ok(reader.dirty.indexOf("10,8,5,4") !== -1,
  "el rect restaurado se marca");
assert.ok(reader.dirty.indexOf("20,8,5,4") === -1,
  "un slot NONE no marca sucio");

/* setField sirve para eleccion; clearField vuelve al default */
assert.strictEqual(overlay.setField(3, 0), true);
assert.strictEqual(overlay.setField(3, 2), false, "max = 1");
assert.strictEqual(overlay.clearField(2), true);
assert.strictEqual(overlay.values[1], NONE);
step(overlay, reader, 4);
assert.ok(same(reader.cells, expectFrame(meta, 4, [[0, 3], [2, 11]])),
  "frame 4: eleccion pintada en el slot de la segunda ventana");

/* clear(): byte-identico al video base y desactiva */
overlay.clear();
assert.ok(same(reader.cells, pristineFrame(4)), "clear restaura la base");
step(overlay, reader, 5);
assert.ok(same(reader.cells, pristineFrame(5)), "desactivado no pinta");

/* identidad de buffers: cero allocaciones en el camino caliente */
assert.strictEqual(overlay.base, baseRef);
assert.strictEqual(overlay.values, valuesRef);

/* re-activacion por carga */
assert.strictEqual(overlay.setValues("90000"), true);
step(overlay, reader, 0);
assert.ok(same(reader.cells, expectFrame(meta, 0, [[0, 9]])),
  "re-activado pinta el digito nuevo");
overlay.detach();
assert.strictEqual(overlay.setValues("90000"), false, "detach corta la API");

/* ============ control negativo: saltear beforeSeek diverge ============ */
var reader2 = new MiniReader();
var overlay2 = OVERLAY.attach(reader2, makeMeta(reader2));
assert.ok(overlay2.setValues("31100"));
step(overlay2, reader2, 0);
step(overlay2, reader2, 1);
step(overlay2, reader2, 2);
/* VIOLACION: sin restaurar, la delta 2->3 no reescribe las celdas impares
 * y la contaminacion del slot 1 sobrevive */
reader2.seek(3);
overlay2.afterSeek();
var contaminated = (8 * COLS) + 11; /* celda impar dentro del slot 1 */
assert.strictEqual(reader2.cells[contaminated], 231,
  "sin beforeSeek, la celda pintada queda contaminada");
assert.ok(!same(reader2.cells, expectFrame(makeMeta(reader2), 3, [[0, 3]])),
  "la violacion del orden §9.2 diverge");

/* ================= rechazos de attach (v2) ================= */
function rejects(mutate, label) {
  var r = new MiniReader();
  var m = makeMeta(r);
  mutate(m, r);
  assert.strictEqual(OVERLAY.attach(r, m), null, label);
}
rejects(function (m) { m.palReserved = 9; }, "palReserved fuera de rango");
rejects(function (m) { m.patches[11].data[3] = 223; },
  "byte de parche bajo la reserva");
rejects(function (m) { m.reservedRgb[0] ^= 1; },
  "cola de paleta distinta del sidecar");
rejects(function (m) { m.reservedRgb = m.reservedRgb.subarray(0, 30); },
  "reserved_rgb corto");
rejects(function (m) { m.fields[1].kind = 2; }, "kind desconocido");
rejects(function (m) { m.fields[1].slotIds = [1, 2]; },
  "eleccion con dos slots");
rejects(function (m) { m.fields[1].patchBase = 12; },
  "parche inexistente (base+span)");
rejects(function (m) { m.fields[0].patchBase = 5; },
  "digitos sin los 11 parches");
rejects(function (m) { m.patches[12] = digitPatch(0); },
  "parche de eleccion con otras dimensiones");
rejects(function (m) { m.slots[2].x = COLS - 2; }, "slot fuera de la grilla");
rejects(function (m, r) { r.palette[672] ^= 1; },
  "paleta del bundle sin la reserva");
rejects(function (m, r) { r.header.palSize = 128; }, "paleta incompleta");

/* ============ datachannel intacto: longitud v2 via digitCount ============ */
var reader3 = new MiniReader();
var overlay3 = OVERLAY.attach(reader3, makeMeta(reader3));
var channel = DC.create("data.txt", overlay3, {
  intervalMs: 1000,
  createXhr: function () {
    return { open: function () {}, send: function () {},
      abort: function () {}, setRequestHeader: function () {} };
  },
  setTimer: function () { return 1; },
  clearTimer: function () {},
  now: function () { return 0; }
});
assert.ok(channel, "create con overlay v2");
channel._handleText("00000001|31100\n");
assert.deepStrictEqual(Array.prototype.slice.call(overlay3.values),
  [3, 12, NONE], "payload v2 aplicado por el canal");
channel._handleText("00000001|90000\n");
assert.strictEqual(overlay3.values[0], 3, "serial repetido no aplica");
channel._handleText("00000002|3110\n");
assert.strictEqual(overlay3.values[0], 3, "longitud invalida no aplica");
channel._handleText("00000002|90000\n");
assert.strictEqual(overlay3.values[0], 9,
  "contenido invalido no consume el serial");

console.log("OK test_overlay_v2_runtime: semantica v2 (presencia, NONE, " +
  "ventanas, violacion §9.2, rechazos de attach, canal intacto)");
