/*
 * slots.js - validador ES5 del sidecar ASCLSLOT, sin dependencias. Espejo
 * exacto de tools/make_slots.py:validate: acepta y rechaza los mismos
 * archivos, byte a byte, en sus dos versiones:
 *
 *   v1 (INT-001 §7.1): glifos uniformes, campos de digitos.
 *     -> { glyphW, glyphH, nGlyphs, glyphTable, reservedRgb, slots, fields }
 *   v2 (INT-003, DISENO-PARCHES-GENERICOS §5): parches heterogeneos,
 *     reserva parametrica, slots con dimensiones propias, kind 0/1.
 *     -> { version: 2, palReserved, reservedRgb, patches, slots, fields }
 *
 * API: ASCL_parseSlots(u8, cols, rows, nFrames, expectedReservedRgb)
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
  var HEADER_SIZE_V2 = 22;
  var SLOT_SIZE_V2 = 17;
  var MAX_PATCHES = 512;
  var MAX_PATCH_AREA = 4096;
  var MAX_PATCH_DATA = 262144;
  var MAX_CHOICE_SPAN = 511;

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
    var i;
    if (!bytes || typeof bytes.length !== "number") fail("entrada invalida");
    if (bytes.length < 9) fail("sidecar truncado");
    for (i = 0; i < 8; i++) {
      if (bytes[i] !== MAGIC.charCodeAt(i)) fail("magic invalido");
    }
    if (bytes[8] === 2) {
      return parseV2(bytes, cols, rows, nFrames, expectedReservedRgb);
    }
    if (bytes[8] !== 1) fail("version no soportada");
    return parseV1(bytes, cols, rows, nFrames, expectedReservedRgb);
  }

  function parseV1(bytes, cols, rows, nFrames, expectedReservedRgb) {
    var i, k, a, b;
    if (bytes.length < HEADER_SIZE) fail("sidecar truncado");
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

  /* Espejo de make_slots._validate_v2: mismo orden de chequeos y los mismos
   * mensajes (sin el prefijo). DISENO-PARCHES-GENERICOS §5. */
  function parseV2(bytes, cols, rows, nFrames, expectedReservedRgb) {
    var i, k, a, b;
    if (bytes.length < HEADER_SIZE_V2) fail("sidecar truncado");
    if (bytes[9] !== 0) fail("byte reservado distinto de 0");
    var palReserved = bytes[10];
    if (palReserved < 10 || palReserved > 64) fail("pal_reserved fuera de 10..64");
    if (bytes[11] !== 0) fail("flags distinto de 0");
    var reservedFirst = 256 - palReserved;
    var nPatches = u16(bytes, 12);
    var nSlots = u16(bytes, 14);
    var nFields = u16(bytes, 16);
    if (crc32(bytes, HEADER_SIZE_V2) !== u32(bytes, 18)) fail("CRC32 invalido");
    var offset = HEADER_SIZE_V2;
    if (offset + 3 * palReserved > bytes.length) fail("sidecar truncado");
    var rgbStart = offset;
    offset += 3 * palReserved;
    if (expectedReservedRgb) {
      if (expectedReservedRgb.length !== 3 * palReserved) {
        fail("reserved_rgb no coincide con el bundle");
      }
      for (i = 0; i < 3 * palReserved; i++) {
        if (bytes[rgbStart + i] !== expectedReservedRgb[i]) {
          fail("reserved_rgb no coincide con el bundle");
        }
      }
    }
    if (!nPatches) fail("sin parches");
    if (nPatches > MAX_PATCHES) fail("n_patches supera 512");
    if (!nSlots) fail("sin slots");
    if (nSlots > MAX_SLOTS) fail("n_slots supera 1024");

    if (offset + nPatches * 4 > bytes.length) fail("tabla de parches truncada");
    var patchW = [], patchH = [], totalPatchData = 0;
    for (i = 0; i < nPatches; i++) {
      patchW[i] = u16(bytes, offset);
      patchH[i] = u16(bytes, offset + 2);
      offset += 4;
      if (!patchW[i] || !patchH[i] || patchW[i] * patchH[i] > MAX_PATCH_AREA) {
        fail("parche " + i + " con dimensiones invalidas");
      }
      totalPatchData += patchW[i] * patchH[i];
    }
    if (totalPatchData > MAX_PATCH_DATA) fail("datos de parches superan 256 KiB");
    if (offset + totalPatchData > bytes.length) fail("tabla de parches truncada");
    var patchStart = offset;
    for (i = 0; i < totalPatchData; i++) {
      if (bytes[offset + i] < reservedFirst) {
        fail("byte de parche fuera de la reserva");
      }
    }
    offset += totalPatchData;

    if (offset + nSlots * SLOT_SIZE_V2 > bytes.length) {
      fail("tabla de slots truncada");
    }
    var slotX = [], slotY = [], slotW = [], slotH = [];
    var slotStart = [], slotEnd = [], slotFlags = [];
    for (i = 0; i < nSlots; i++) {
      slotX[i] = u16(bytes, offset);
      slotY[i] = u16(bytes, offset + 2);
      slotW[i] = u16(bytes, offset + 4);
      slotH[i] = u16(bytes, offset + 6);
      slotStart[i] = u32(bytes, offset + 8);
      slotEnd[i] = u32(bytes, offset + 12);
      slotFlags[i] = bytes[offset + 16];
      offset += SLOT_SIZE_V2;
      if (!slotW[i] || !slotH[i]) {
        fail("slot " + i + " con dimensiones invalidas");
      }
      if (slotX[i] + slotW[i] > cols || slotY[i] + slotH[i] > rows) {
        fail("slot " + i + " fuera de la grilla");
      }
      if (slotEnd[i] < slotStart[i]) {
        fail("slot " + i + " con end_frame < start_frame");
      }
      if (nFrames !== undefined && nFrames !== null && slotEnd[i] >= nFrames) {
        fail("slot " + i + " activo mas alla del ultimo frame");
      }
    }
    /* solape espacial permitido SOLO con ventanas temporales disjuntas (D4) */
    for (a = 0; a < nSlots; a++) {
      for (b = a + 1; b < nSlots; b++) {
        if (slotX[a] < slotX[b] + slotW[b] && slotX[b] < slotX[a] + slotW[a] &&
            slotY[a] < slotY[b] + slotH[b] && slotY[b] < slotY[a] + slotH[a] &&
            slotStart[a] <= slotEnd[b] && slotStart[b] <= slotEnd[a]) {
          fail("slots " + a + " y " + b + " se solapan");
        }
      }
    }
    /* presupuesto POR FRAME (5%): barrido de eventos start/end+1 (§5.4) */
    var events = [], totalArea = 0, area;
    for (i = 0; i < nSlots; i++) {
      area = slotW[i] * slotH[i];
      totalArea += area;
      events.push([slotStart[i], area]);
      events.push([slotEnd[i] + 1, -area]);
    }
    events.sort(function (p, q) {
      return (p[0] - q[0]) || (p[1] - q[1]);
    });
    var active = 0;
    for (i = 0; i < events.length; i++) {
      active += events[i][1];
      if (active * 20 > cols * rows) {
        fail("area activa supera el 5% de la grilla");
      }
    }
    if (totalArea * 4 > cols * rows) {
      fail("area total de slots supera el 25% de la grilla");
    }

    var fields = [], usedIds = {};
    var fieldId, kind, count, slotIds, minimum, maximum, pad, patchBase;
    var span, firstSlot, powers = [1, 10, 100, 1000, 10000, 100000, 1000000,
      10000000, 100000000, 1000000000];
    for (i = 0; i < nFields; i++) {
      if (offset + 4 > bytes.length) fail("tabla de campos truncada");
      fieldId = u16(bytes, offset);
      kind = bytes[offset + 2];
      count = bytes[offset + 3];
      offset += 4;
      if (kind !== 0 && kind !== 1) {
        fail("campo " + fieldId + " con kind invalido");
      }
      if (!count) fail("campo " + i + " sin slots");
      if (offset + count * 2 + 11 > bytes.length) {
        fail("tabla de campos truncada");
      }
      slotIds = [];
      for (k = 0; k < count; k++) {
        slotIds[k] = u16(bytes, offset);
        offset += 2;
      }
      minimum = u32(bytes, offset);
      maximum = u32(bytes, offset + 4);
      pad = bytes[offset + 8];
      patchBase = u16(bytes, offset + 9);
      offset += 11;
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
      firstSlot = slotIds[0];
      for (k = 0; k < count; k++) {
        if (slotW[slotIds[k]] !== slotW[firstSlot] ||
            slotH[slotIds[k]] !== slotH[firstSlot]) {
          fail("campo " + fieldId + " con slots de dimensiones distintas");
        }
      }
      if (kind === 0) {
        if (pad !== 0 && pad !== 1) {
          fail("campo " + fieldId + " con pad invalido");
        }
        if (count < powers.length && maximum >= powers[count]) {
          fail("campo " + fieldId + " no puede representar max con " +
            count + " digitos");
        }
        span = 11; /* digitos 0..9 + vacio en patch_base+10 */
      } else {
        if (count !== 1) {
          fail("campo " + fieldId + " de eleccion debe tener un solo slot");
        }
        if (pad !== 0) {
          fail("campo " + fieldId + " de eleccion con pad distinto de 0");
        }
        if (maximum - minimum > MAX_CHOICE_SPAN) {
          fail("campo " + fieldId + " de eleccion supera 512 variantes");
        }
        span = maximum - minimum + 1;
      }
      if (patchBase + span > nPatches) {
        fail("campo " + fieldId + " referencia un parche inexistente");
      }
      for (k = patchBase; k < patchBase + span; k++) {
        if (patchW[k] !== slotW[firstSlot] || patchH[k] !== slotH[firstSlot]) {
          fail("campo " + fieldId +
            " con parches de dimensiones distintas al slot");
        }
      }
      fields.push({ fieldId: fieldId, kind: kind, slotIds: slotIds,
        min: minimum, max: maximum, pad: pad, patchBase: patchBase });
    }
    if (offset !== bytes.length) fail("bytes sobrantes al final del sidecar");

    var patches = [], cursor = patchStart, size;
    for (i = 0; i < nPatches; i++) {
      size = patchW[i] * patchH[i];
      var data = new Uint8Array(size);
      for (k = 0; k < size; k++) data[k] = bytes[cursor + k];
      cursor += size;
      patches.push({ w: patchW[i], h: patchH[i], data: data });
    }
    var slots = [];
    for (i = 0; i < nSlots; i++) {
      slots.push({ x: slotX[i], y: slotY[i], w: slotW[i], h: slotH[i],
        start: slotStart[i], end: slotEnd[i], flags: slotFlags[i] });
    }
    var reservedRgb = new Uint8Array(3 * palReserved);
    for (i = 0; i < 3 * palReserved; i++) {
      reservedRgb[i] = bytes[rgbStart + i];
    }
    return { version: 2, palReserved: palReserved, reservedRgb: reservedRgb,
      patches: patches, slots: slots, fields: fields };
  }

  root.ASCL_parseSlots = ASCL_parseSlots;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { ASCL_parseSlots: ASCL_parseSlots };
  }
})(typeof window !== "undefined" ? window : this);
