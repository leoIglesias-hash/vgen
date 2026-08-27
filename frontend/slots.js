/*
 * slots.js - validador ES5 del sidecar ASCLSLOT (INT-001 §7.1), sin
 * dependencias. Espejo exacto de tools/make_slots.py:validate: acepta y
 * rechaza los mismos archivos, byte a byte.
 *
 * API:
 *   ASCL_parseSlots(u8, cols, rows, nFrames, expectedReservedRgb)
 *     -> { glyphW, glyphH, nGlyphs, glyphTable, reservedRgb, slots, fields }
 *
 * Toda violacion lanza Error("slots: ...") sin devolver nada parcial:
 * primero se valida el archivo completo, recien despues se construye el
 * resultado (contrato C3 del proyecto).
 */
(function (root) {
  "use strict";

  var HEADER_SIZE = 54;
  var SLOT_SIZE = 13;
  var MAX_SLOTS = 1024;
  var MAX_GLYPH_AREA = 4096;
  var RESERVED_FIRST = 246;
  var MAGIC = "ASCLSLOT";

  function fail(message) { throw new Error("slots: " + message); }

  function u16(bytes, offset) {
    return bytes[offset] | (bytes[offset + 1] << 8);
  }

  function u32(bytes, offset) {
    return (bytes[offset] | (bytes[offset + 1] << 8) |
      (bytes[offset + 2] << 16) | (bytes[offset + 3] << 24)) >>> 0;
  }

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

  function ASCL_parseSlots(bytes, cols, rows, nFrames, expectedReservedRgb) {
    var i, k, a, b;
    if (!bytes || typeof bytes.length !== "number") fail("entrada invalida");
    if (bytes.length < HEADER_SIZE) fail("sidecar truncado");
    for (i = 0; i < 8; i++) {
      if (bytes[i] !== MAGIC.charCodeAt(i)) fail("magic invalido");
    }
    if (bytes[8] !== 1) fail("version no soportada");
    if (bytes[9] !== 0) fail("byte reservado distinto de 0");
    if (bytes[10] !== 10) fail("pal_reserved debe ser 10");
    var nGlyphs = bytes[11];
    var glyphW = u16(bytes, 12);
    var glyphH = u16(bytes, 14);
    var nSlots = u16(bytes, 16);
    var nFields = u16(bytes, 18);
    if (crc32(bytes, HEADER_SIZE) !== u32(bytes, 50)) fail("CRC32 invalido");
    if (expectedReservedRgb) {
      if (expectedReservedRgb.length !== 30) fail("reserved_rgb esperado invalido");
      for (i = 0; i < 30; i++) {
        if (bytes[20 + i] !== expectedReservedRgb[i]) {
          fail("reserved_rgb no coincide con el bundle");
        }
      }
    }
    if (!nGlyphs || !glyphW || !glyphH) fail("glifos vacios");
    if (glyphW * glyphH > MAX_GLYPH_AREA) fail("glyph_w * glyph_h supera 4096");
    if (nSlots > MAX_SLOTS) fail("n_slots supera 1024");

    var offset = HEADER_SIZE;
    var glyphLen = nGlyphs * glyphW * glyphH;
    if (offset + glyphLen > bytes.length) fail("tabla de glifos truncada");
    for (i = 0; i < glyphLen; i++) {
      if (bytes[offset + i] < RESERVED_FIRST) fail("byte de glifo fuera de 246..255");
    }
    var glyphStart = offset;
    offset += glyphLen;

    if (offset + nSlots * SLOT_SIZE > bytes.length) fail("tabla de slots truncada");
    var slotX = [], slotY = [], slotStart = [], slotEnd = [], slotFlags = [];
    for (i = 0; i < nSlots; i++) {
      slotX[i] = u16(bytes, offset);
      slotY[i] = u16(bytes, offset + 2);
      slotStart[i] = u32(bytes, offset + 4);
      slotEnd[i] = u32(bytes, offset + 8);
      slotFlags[i] = bytes[offset + 12];
      offset += SLOT_SIZE;
      if (slotX[i] + glyphW > cols || slotY[i] + glyphH > rows) {
        fail("slot " + i + " fuera de la grilla");
      }
      if (slotEnd[i] < slotStart[i]) {
        fail("slot " + i + " con end_frame < start_frame");
      }
      if (nFrames !== undefined && nFrames !== null && slotEnd[i] >= nFrames) {
        fail("slot " + i + " activo mas alla del ultimo frame");
      }
    }
    for (a = 0; a < nSlots; a++) {
      for (b = a + 1; b < nSlots; b++) {
        if (slotX[a] < slotX[b] + glyphW && slotX[b] < slotX[a] + glyphW &&
            slotY[a] < slotY[b] + glyphH && slotY[b] < slotY[a] + glyphH) {
          fail("slots " + a + " y " + b + " se solapan");
        }
      }
    }
    if (nSlots * glyphW * glyphH * 20 > cols * rows) {
      fail("area activa supera el 5% de la grilla");
    }

    var fields = [], usedIds = {}, fieldId, count, slotIds, minimum, maximum, pad;
    /* 10 entradas: con count >= 10 cualquier u32 es representable y el
     * chequeo no aplica (mismo comportamiento que el validador Python). */
    var powers = [1, 10, 100, 1000, 10000, 100000, 1000000, 10000000,
      100000000, 1000000000];
    for (i = 0; i < nFields; i++) {
      if (offset + 3 > bytes.length) fail("tabla de campos truncada");
      fieldId = u16(bytes, offset);
      count = bytes[offset + 2];
      offset += 3;
      if (!count) fail("campo " + i + " sin slots");
      if (offset + count * 2 + 9 > bytes.length) fail("tabla de campos truncada");
      slotIds = [];
      for (k = 0; k < count; k++) {
        slotIds[k] = u16(bytes, offset);
        offset += 2;
      }
      minimum = u32(bytes, offset);
      maximum = u32(bytes, offset + 4);
      pad = bytes[offset + 8];
      offset += 9;
      for (k = 0; k < count; k++) {
        if (slotIds[k] >= nSlots) {
          fail("campo " + fieldId + " referencia un slot inexistente");
        }
        if (usedIds[slotIds[k]] === 1) {
          fail("slot " + slotIds[k] + " aparece en dos campos");
        }
        usedIds[slotIds[k]] = 1;
      }
      if (maximum < minimum) fail("campo " + fieldId + " con max < min");
      if (count < powers.length && maximum >= powers[count]) {
        fail("campo " + fieldId + " no puede representar max con " +
          count + " digitos");
      }
      fields.push({ fieldId: fieldId, slotIds: slotIds, min: minimum,
        max: maximum, pad: pad });
    }
    if (offset !== bytes.length) fail("bytes sobrantes al final del sidecar");

    var slots = [];
    for (i = 0; i < nSlots; i++) {
      slots.push({ x: slotX[i], y: slotY[i], start: slotStart[i],
        end: slotEnd[i], flags: slotFlags[i] });
    }
    var glyphTable = new Uint8Array(glyphLen);
    for (i = 0; i < glyphLen; i++) glyphTable[i] = bytes[glyphStart + i];
    var reservedRgb = new Uint8Array(30);
    for (i = 0; i < 30; i++) reservedRgb[i] = bytes[20 + i];
    return { glyphW: glyphW, glyphH: glyphH, nGlyphs: nGlyphs,
      glyphTable: glyphTable, reservedRgb: reservedRgb,
      slots: slots, fields: fields };
  }

  root.ASCL_parseSlots = ASCL_parseSlots;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { ASCL_parseSlots: ASCL_parseSlots };
  }
})(typeof window !== "undefined" ? window : this);
