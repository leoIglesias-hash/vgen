"use strict";
/* F7-1/F7-2: runtime del overlay (frontend/overlay.js) sobre ambos readers.
 * Gates de INT-002 cubiertos aca: restauracion byte-identica (clear, seek
 * hacia atras, reinicio de loop), union de rects sucios, un field_id o digito
 * invalido no escribe fuera de su slot, sin allocaciones en el loop estable. */

var assert = require("assert");
var zlib = require("zlib");
var ASCL = require("../frontend/reader.js");
var ASCLV2 = require("../frontend/reader-v2.js");
var SLOTS = require("../frontend/slots.js");
var OVERLAY = require("../frontend/overlay.js");

var TAG_RAW = 0, TAG_ZLIB = 1, TAG_MASK = 3, KEY_RAW = 4, DELTA_RAW = 6;
var SKIP = 0, SOLID = 1;
var COLS = 64, ROWS = 32, N = COLS * ROWS, FRAMES = 5;
var GLYPH_W = 4, GLYPH_H = 5, GLYPH_AREA = GLYPH_W * GLYPH_H, N_GLYPHS = 11;
var EMPTY = 10;

/* ---------- helpers de armado (mismos que test_reader_dirty_rect) ---------- */
function b(value) { return Buffer.isBuffer(value) ? value : Buffer.from(value); }

function block(tag, palette, payload) {
  var pal = palette ? b(palette) : Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  b(payload).copy(body, 3 + pal.length);
  var result = Buffer.alloc(4 + body.length);
  result.writeUInt32LE(body.length, 0);
  body.copy(result, 4);
  return result;
}

function makeV1(frames, cols, rows, palSize) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i;
  header.write("ASCL", 0, "ascii");
  header[4] = 1;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(palSize, 12);
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  return Buffer.concat([header, table].concat(frames));
}

function makeV2(frames, cols, rows, palSize) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i, out;
  header.write("ASCL", 0, "ascii");
  header[4] = 2;
  header[5] = 3;
  header[6] = 12;
  header[7] = 15;
  header.writeUInt16LE(cols, 8);
  header.writeUInt16LE(rows, 10);
  header.writeUInt16LE(palSize, 12);
  header.writeUInt32LE(frames.length, 14);
  header[19] = 3;
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  header[26] = 16;
  header[27] = 1;
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  out = Buffer.concat([header, table].concat(frames));
  out.writeUInt32LE(ASCLV2.crc32v2(out), 28);
  return out;
}

function maskDelta(n, changes) {
  var maskLen = (n + 7) >> 3;
  var mask = Buffer.alloc(maskLen);
  var sorted = changes.slice().sort(function (x, y) { return x[0] - y[0]; });
  var values = Buffer.alloc(sorted.length), i, cell;
  for (i = 0; i < sorted.length; i++) {
    cell = sorted[i][0];
    mask[cell >> 3] |= 1 << (cell & 7);
    values[i] = sorted[i][1];
  }
  return block(TAG_MASK, null,
    zlib.deflateSync(Buffer.concat([mask, values])));
}

function cellBit(reader, cell) {
  return (reader.dirtyCellBits[cell >>> 3] >>> (cell & 7)) & 1;
}

/* ---------- paleta con cola reservada y tabla de glifos sintetica ---------- */
var RESERVED_RGB = new Uint8Array(30);
(function () {
  var k;
  for (k = 0; k < 10; k++) {
    RESERVED_RGB[k * 3] = 40 + k;
    RESERVED_RGB[k * 3 + 1] = 80 + k;
    RESERVED_RGB[k * 3 + 2] = 120 + k;
  }
}());

function palette256() {
  var out = Buffer.alloc(256 * 3), i;
  for (i = 0; i < 246; i++) {
    out[i * 3] = (i * 5) % 256;
    out[i * 3 + 1] = (i * 7) % 256;
    out[i * 3 + 2] = (i * 11) % 256;
  }
  for (i = 0; i < 30; i++) out[246 * 3 + i] = RESERVED_RGB[i];
  return out;
}

function glyphTable() {
  var out = new Uint8Array(N_GLYPHS * GLYPH_AREA), d, k;
  for (d = 0; d < 10; d++) {
    for (k = 0; k < GLYPH_AREA; k++) {
      out[d * GLYPH_AREA + k] = k === 0 ? 255 : 246 + ((d + k) % 10);
    }
  }
  for (k = 0; k < GLYPH_AREA; k++) out[EMPTY * GLYPH_AREA + k] = 255;
  return out;
}

/* ---------- sidecar ASCLSLOT real, parseado por slots.js ---------- */
var crcTable = null;
function crc32(bytes, start) {
  var crc = 0xffffffff, i, k, c;
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (i = 0; i < 256; i++) {
      c = i;
      for (k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      crcTable[i] = c >>> 0;
    }
  }
  for (i = start; i < bytes.length; i++) {
    crc = crcTable[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/* slots 4x5 en la fila 8; el slot 3 se desactiva despues del frame 1.
 * campo 7 = slots [0,1] (0..99, pad), campo 9 = slots [2,3] (0..42, sin pad) */
var SLOT_DEFS = [
  { x: 10, y: 8, start: 0, end: 4, flags: 1 },
  { x: 16, y: 8, start: 0, end: 4, flags: 1 },
  { x: 22, y: 8, start: 0, end: 4, flags: 1 },
  { x: 28, y: 8, start: 0, end: 1, flags: 1 }
];
var FIELD_DEFS = [
  { fieldId: 7, slotIds: [0, 1], min: 0, max: 99, pad: 1 },
  { fieldId: 9, slotIds: [2, 3], min: 0, max: 42, pad: 0 }
];

function buildSidecar(reservedRgb) {
  var glyphs = glyphTable();
  var bodyLen = glyphs.length + SLOT_DEFS.length * 13, i, k, f;
  for (i = 0; i < FIELD_DEFS.length; i++) {
    bodyLen += 3 + FIELD_DEFS[i].slotIds.length * 2 + 9;
  }
  var out = Buffer.alloc(54 + bodyLen);
  out.write("ASCLSLOT", 0, "ascii");
  out[8] = 1;
  out[9] = 0;
  out[10] = 10;
  out[11] = N_GLYPHS;
  out.writeUInt16LE(GLYPH_W, 12);
  out.writeUInt16LE(GLYPH_H, 14);
  out.writeUInt16LE(SLOT_DEFS.length, 16);
  out.writeUInt16LE(FIELD_DEFS.length, 18);
  for (i = 0; i < 30; i++) out[20 + i] = reservedRgb[i];
  var p = 54;
  for (i = 0; i < glyphs.length; i++) out[p + i] = glyphs[i];
  p += glyphs.length;
  for (i = 0; i < SLOT_DEFS.length; i++) {
    out.writeUInt16LE(SLOT_DEFS[i].x, p);
    out.writeUInt16LE(SLOT_DEFS[i].y, p + 2);
    out.writeUInt32LE(SLOT_DEFS[i].start, p + 4);
    out.writeUInt32LE(SLOT_DEFS[i].end, p + 8);
    out[p + 12] = SLOT_DEFS[i].flags;
    p += 13;
  }
  for (i = 0; i < FIELD_DEFS.length; i++) {
    f = FIELD_DEFS[i];
    out.writeUInt16LE(f.fieldId, p);
    out[p + 2] = f.slotIds.length;
    p += 3;
    for (k = 0; k < f.slotIds.length; k++) {
      out.writeUInt16LE(f.slotIds[k], p);
      p += 2;
    }
    out.writeUInt32LE(f.min, p);
    out.writeUInt32LE(f.max, p + 4);
    out[p + 8] = f.pad;
    p += 9;
  }
  out.writeUInt32LE(crc32(out, 54), 50);
  return out;
}

/* ---------- modelo de referencia: composicion esperada ---------- */
var GLYPHS = glyphTable();
function composeExpected(refCells, frame, slotValues) {
  var out = Buffer.from(refCells), i, gy, gx, v, s;
  for (i = 0; i < SLOT_DEFS.length; i++) {
    s = SLOT_DEFS[i];
    if (!(s.flags & 1) || frame < s.start || frame > s.end) continue;
    for (gy = 0; gy < GLYPH_H; gy++) {
      for (gx = 0; gx < GLYPH_W; gx++) {
        v = GLYPHS[slotValues[i] * GLYPH_AREA + gy * GLYPH_W + gx];
        if (v !== 255) out[(s.y + gy) * COLS + s.x + gx] = v;
      }
    }
  }
  return out;
}

function sameCells(reader, expected, label) {
  assert.strictEqual(Buffer.compare(Buffer.from(reader.cells), expected), 0,
    label);
}

function step(overlay, reader, frame) {
  overlay.beforeSeek();
  reader.seek(frame);
  overlay.afterSeek();
}

/* ---------- fixtures de video ---------- */
function makeClipV1() {
  var key = Buffer.alloc(N), key2 = Buffer.alloc(N), i;
  for (i = 0; i < N; i++) key[i] = i % 200;
  for (i = 0; i < N; i++) key2[i] = (i * 3) % 190;
  return makeV1([
    block(TAG_RAW, palette256(), key),
    /* dos celdas DENTRO del slot 0 cambian: la restauracion previa al seek
     * es lo que evita que el delta se aplique sobre glifos */
    maskDelta(N, [[8 * COLS + 10, 10], [8 * COLS + 11, 11], [0, 12], [100, 13]]),
    maskDelta(N, [[5, 50], [6, 51], [200, 52]]),
    /* keyframe intermedio SIN paleta: con paleta global el reader rechaza la
     * reemision, y la cola reservada 246..255 persiste igual (INV-4) */
    block(TAG_ZLIB, null, zlib.deflateSync(key2)),
    maskDelta(N, [[9 * COLS + 17, 70], [300, 71]])
  ], COLS, ROWS, 256);
}

var sidecar = buildSidecar(RESERVED_RGB);
var META = SLOTS.ASCL_parseSlots(new Uint8Array(sidecar), COLS, ROWS, FRAMES,
  RESERVED_RGB);

/* ---------- runtime completo sobre ReaderV1 ---------- */
(function testV1Runtime() {
  var clip = makeClipV1();
  var reader = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ref = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var overlay = OVERLAY.attach(reader, META);
  assert.ok(overlay, "attach valido devuelve instancia");
  assert.strictEqual(overlay.digitCount, 4);
  assert.strictEqual(overlay.base.length, 4 * GLYPH_AREA);

  /* API de valores: todo o nada, sin escribir fuera del slot */
  assert.strictEqual(overlay.setValues("0512"), true);
  assert.deepStrictEqual(Array.prototype.slice.call(overlay.values),
    [0, 5, 1, 2], "campo 7 con pad, campo 9 sin pad");
  assert.strictEqual(overlay.setValues("0599"), false, "campo 9 fuera de rango");
  assert.strictEqual(overlay.setValues("051"), false, "longitud incorrecta");
  assert.strictEqual(overlay.setValues("05a2"), false, "caracter invalido");
  assert.deepStrictEqual(Array.prototype.slice.call(overlay.values),
    [0, 5, 1, 2], "un dato invalido conserva el ultimo estado valido");
  assert.strictEqual(overlay.setField(9, 7), true);
  assert.deepStrictEqual(Array.prototype.slice.call(overlay.values),
    [0, 5, EMPTY, 7], "sin pad: cero a la izquierda queda vacio");
  assert.strictEqual(overlay.setField(9, 43), false, "sobre el max");
  assert.strictEqual(overlay.setField(8, 1), false, "campo inexistente");
  assert.strictEqual(overlay.setField(7, 3.5), false, "no entero");
  assert.strictEqual(overlay.setValues("0512"), true);

  var baseRef = overlay.base, valuesRef = overlay.values;
  var expectedVals = [0, 5, 1, 2];

  /* reproduccion hacia adelante con cambio de valor en vivo en el frame 3:
   * composicion exacta en cada frame */
  var f;
  for (f = 0; f < FRAMES; f++) {
    if (f === 3) {
      assert.strictEqual(overlay.setValues("9934"), true);
      expectedVals = [9, 9, 3, 4];
    }
    step(overlay, reader, f);
    ref.seek(f);
    sameCells(reader, composeExpected(ref.cells, f, expectedVals),
      "composicion exacta en frame " + f);
  }

  /* union de rects sucios en un frame delta (frame 2 no toca slots):
   * los slots pintados y el slot 3 recien desactivado (restaurado) quedan
   * marcados; una celda lejana no */
  var r2 = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ov2 = OVERLAY.attach(r2, META);
  ov2.setValues("0512");
  step(ov2, r2, 0);
  step(ov2, r2, 1);
  step(ov2, r2, 2);
  assert.strictEqual(r2.dirtyFull, false);
  assert.strictEqual(cellBit(r2, 8 * COLS + 10), 1, "slot 0 marcado");
  assert.strictEqual(cellBit(r2, 12 * COLS + 25), 1, "slot 2 marcado");
  assert.strictEqual(cellBit(r2, 8 * COLS + 28), 1,
    "slot 3 restaurado (desactivado) tambien marcado");
  assert.strictEqual(cellBit(r2, 30 * COLS + 60), 0, "celda lejana sin marcar");

  /* seek hacia atras y reinicio de loop con overlay activo */
  step(overlay, reader, 1);
  ref.seek(1);
  sameCells(reader, composeExpected(ref.cells, 1, expectedVals), "seek atras");
  step(overlay, reader, 4);
  step(overlay, reader, 0);
  ref.seek(0);
  sameCells(reader, composeExpected(ref.cells, 0, expectedVals),
    "reinicio de loop");

  /* clear(): cells byte-identico a la reproduccion sin overlay */
  step(overlay, reader, 2);
  ref.seek(2);
  overlay.clear();
  assert.strictEqual(overlay.active, false);
  assert.strictEqual(overlay.restoreValid, false);
  sameCells(reader, Buffer.from(ref.cells), "clear restaura byte-identico");
  step(overlay, reader, 3);
  ref.seek(3);
  sameCells(reader, Buffer.from(ref.cells), "inactivo no pinta");

  /* un nuevo dato reactiva el overlay */
  assert.strictEqual(overlay.setValues("0512"), true);
  expectedVals = [0, 5, 1, 2];
  step(overlay, reader, 4);
  ref.seek(4);
  sameCells(reader, composeExpected(ref.cells, 4, expectedVals), "reactivado");

  /* sin allocaciones en el loop estable: los buffers son los de attach */
  assert.strictEqual(overlay.base, baseRef);
  assert.strictEqual(overlay.values, valuesRef);

  /* detach deja el runtime inerte y el reader limpio */
  overlay.detach();
  sameCells(reader, Buffer.from(ref.cells), "detach restaura");
  assert.strictEqual(overlay.setValues("0512"), false);
  assert.strictEqual(overlay.setField(7, 1), false);
  overlay.beforeSeek();
  overlay.afterSeek();
}());

/* ---------- el orden §9.2 importa: saltear el paso 1 contamina ---------- */
(function testOrderViolationDetected() {
  var clip = makeClipV1();
  var reader = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ref = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var overlay = OVERLAY.attach(reader, META);
  overlay.setValues("0512");
  step(overlay, reader, 0);
  /* violacion deliberada: seek sin beforeSeek -> la "base" guardada despues
   * queda contaminada con glifos; al cambiar el valor, las celdas que el
   * glifo nuevo deja transparentes muestran la contaminacion */
  reader.seek(1);
  overlay.afterSeek();
  overlay.setValues("9934");
  step(overlay, reader, 2);
  ref.seek(2);
  assert.notStrictEqual(
    Buffer.compare(Buffer.from(reader.cells),
      composeExpected(ref.cells, 2, [9, 9, 3, 4])), 0,
    "sin el paso 1 la matriz diverge: el orden por frame es obligatorio");
}());

/* ---------- attach: null ante cualquier meta o bundle invalido ---------- */
(function testAttachRejections() {
  var clip = makeClipV1();
  var reader = ASCL.parse(clip.buffer, clip.byteOffset, clip.byteLength);

  /* glifo fuera del rango reservado */
  var bad = SLOTS.ASCL_parseSlots(new Uint8Array(sidecar), COLS, ROWS, FRAMES,
    RESERVED_RGB);
  bad.glyphTable[5] = 245;
  assert.strictEqual(OVERLAY.attach(reader, bad), null, "glifo < 246");

  /* sin glifo vacio */
  bad = SLOTS.ASCL_parseSlots(new Uint8Array(sidecar), COLS, ROWS, FRAMES,
    RESERVED_RGB);
  bad.nGlyphs = 10;
  bad.glyphTable = bad.glyphTable.subarray(0, 10 * GLYPH_AREA);
  assert.strictEqual(OVERLAY.attach(reader, bad), null, "faltan 11 glifos");

  /* sidecar de otro bundle: reserved_rgb no coincide con la paleta */
  var otherRgb = new Uint8Array(30), i;
  for (i = 0; i < 30; i++) otherRgb[i] = 200 + (i % 20);
  var mismatched = SLOTS.ASCL_parseSlots(
    new Uint8Array(buildSidecar(otherRgb)), COLS, ROWS, FRAMES, otherRgb);
  assert.strictEqual(OVERLAY.attach(reader, mismatched), null,
    "reserved_rgb ajeno no activa el overlay");

  /* clip sin paleta completa (sin reserva posible) */
  var small = makeV1([
    block(TAG_RAW, Buffer.from([0, 0, 0, 85, 85, 85, 170, 170, 170,
      255, 255, 255]), Buffer.alloc(N))
  ], COLS, ROWS, 4);
  var smallReader = ASCL.parse(small.buffer, small.byteOffset,
    small.byteLength);
  assert.strictEqual(OVERLAY.attach(smallReader, META), null,
    "pal_size != 256 no admite reserva");

  /* grilla mas chica que los slots */
  var tinyKey = Buffer.alloc(16 * 8);
  var tiny = makeV1([block(TAG_RAW, palette256(), tinyKey)], 16, 8, 256);
  var tinyReader = ASCL.parse(tiny.buffer, tiny.byteOffset, tiny.byteLength);
  assert.strictEqual(OVERLAY.attach(tinyReader, META), null,
    "slot fuera de la grilla del reader");
}());

/* ---------- mismo runtime sobre ReaderV2 ---------- */
(function testV2Runtime() {
  var keyStream = Buffer.alloc(16), i;
  for (i = 0; i < 8; i++) { keyStream[i * 2] = SOLID; keyStream[i * 2 + 1] = 1; }
  var clip = makeV2([
    block(KEY_RAW, palette256(), keyStream),
    block(DELTA_RAW, null, Buffer.from([SKIP, 8])),
    /* el tile 0 (contiene los slots 0 y 1) cambia a SOLID 2 */
    block(DELTA_RAW, null, Buffer.from([SOLID, 2, SKIP, 7]))
  ], COLS, ROWS, 256);
  var reader = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ref = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  /* clip de 3 frames: sin cota de nFrames en el parse (los slots declaran
   * end=4 para el clip v1 de 5 frames) */
  var meta = SLOTS.ASCL_parseSlots(new Uint8Array(sidecar), COLS, ROWS, null,
    RESERVED_RGB);
  var overlay = OVERLAY.attach(reader, meta);
  assert.ok(overlay, "attach sobre ReaderV2");
  overlay.setValues("0512");

  var f;
  for (f = 0; f < 3; f++) {
    step(overlay, reader, f);
    ref.seek(f);
    sameCells(reader, composeExpected(ref.cells, f, [0, 5, 1, 2]),
      "v2: composicion exacta en frame " + f);
  }

  /* frame 1 es SKIP puro: lo unico sucio son los rects del overlay */
  var r2 = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ov2 = OVERLAY.attach(r2, meta);
  ov2.setValues("0512");
  step(ov2, r2, 0);
  step(ov2, r2, 1);
  assert.strictEqual(r2.dirtyFull, false);
  assert.strictEqual(r2.dirtyCellCount, 4 * GLYPH_AREA,
    "v2: exactamente las celdas de los 4 slots");

  step(overlay, reader, 0);
  ref.seek(0);
  sameCells(reader, composeExpected(ref.cells, 0, [0, 5, 1, 2]),
    "v2: seek hacia atras");

  overlay.clear();
  sameCells(reader, Buffer.from(ref.cells), "v2: clear byte-identico");
  overlay.detach();
}());

/* W-22: el pre-decode adopta un reader que decodificó su keyframe por su
 * cuenta, así que sus celdas nunca vieron un parche. El intercambio es legal
 * sólo si el overlay se reapunta ENTRE beforeSeek y afterSeek. Lo que se exige
 * acá es que adoptar y no adoptar den exactamente las mismas celdas. */
(function testRebindTrasIntercambioDeReaders() {
  var keyA = Buffer.alloc(16), keyB = Buffer.alloc(16), i;
  for (i = 0; i < 8; i++) { keyA[i * 2] = SOLID; keyA[i * 2 + 1] = 1; }
  for (i = 0; i < 8; i++) { keyB[i * 2] = SOLID; keyB[i * 2 + 1] = 2; }
  /* frame 2 es keyframe: es lo único que el pre-decode adelanta. */
  var clip = makeV2([
    block(KEY_RAW, palette256(), keyA),
    block(DELTA_RAW, null, Buffer.from([SKIP, 8])),
    block(KEY_RAW, null, keyB)
  ], COLS, ROWS, 256);
  var shown = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var spare = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var ref = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var previous = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var plain = ASCLV2.parse(clip.buffer, clip.byteOffset, clip.byteLength);
  var meta = SLOTS.ASCL_parseSlots(new Uint8Array(sidecar), COLS, ROWS, null,
    RESERVED_RGB);
  var overlay = OVERLAY.attach(shown, meta);
  var plainOverlay = OVERLAY.attach(plain, meta);
  var f;
  assert.ok(overlay && plainOverlay, "attach sobre los dos ReaderV2");
  assert.strictEqual(shown._isKey(2), true);
  overlay.setValues("0512");
  plainOverlay.setValues("0512");

  step(overlay, shown, 0);
  step(overlay, shown, 1);

  /* El reader de repuesto adelanta el keyframe sin overlay: video limpio. */
  spare.seek(2);
  ref.seek(2);
  sameCells(spare, Buffer.from(ref.cells), "el adelantado trae el video limpio");

  /* La adopción, en el orden exacto de INT-001 §9.2 con el reapunte en medio. */
  overlay.beforeSeek();
  overlay.rebind(spare);
  overlay.afterSeek();
  sameCells(spare, composeExpected(ref.cells, 2, [0, 5, 1, 2]),
    "tras el intercambio el overlay pinta sobre el reader adoptado");

  /* El desplazado queda con su base devuelta: sin glifos pegados. */
  previous.seek(1);
  sameCells(shown, Buffer.from(previous.cells),
    "la restauración corrió antes del cambio: el reader que se va queda limpio");

  /* Y el gate que importa: el camino con pre-decode y el camino sin él tienen
   * que terminar en las MISMAS celdas. */
  for (f = 0; f < 3; f++) { step(plainOverlay, plain, f); }
  sameCells(spare, Buffer.from(plain.cells),
    "adoptar o no adoptar da exactamente las mismas celdas");
  overlay.detach();
  plainOverlay.detach();
}());

console.log("OK test_overlay_runtime");
