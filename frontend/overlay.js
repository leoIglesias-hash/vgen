/*
 * overlay.js - F7/INT-003: runtime de la intervencion matricial (INT-001 §9,
 * DISENO-PARCHES-GENERICOS §7).
 *
 * Escribe parches como INDICES de paleta reservados sobre la misma matriz de
 * celdas del reader, y restaura las celdas base ANTES de cada decodificacion
 * para que ninguna cadena DELTA se calcule sobre pixeles contaminados
 * (INT-001 §9.2, paso 1 antes del paso 2).
 *
 * Acepta las dos versiones del sidecar (resultado de ASCL_parseSlots):
 *   v1: glifos uniformes 246..255, campos de digitos. Comportamiento
 *       byte-identico al runtime F7 original.
 *   v2: parches heterogeneos, reserva parametrica (256-N..255), campos de
 *       digitos (kind 0) y de eleccion (kind 1). Un slot sin valor (NONE)
 *       no se pinta, no guarda base y no marca sucio.
 *
 * API (INT-001 §9.5):
 *   ASCILINEOverlay.attach(reader, meta) -> instancia o null si meta invalida
 *   overlay.beforeSeek()   paso 1: restaurar overlay.base sobre cells
 *   overlay.afterSeek()    pasos 3-5: guardar base, pintar, marcar sucio
 *   overlay.setField(fieldId, value)  overlay.setValues(payload)
 *   overlay.clearField(fieldId)       overlay.clear()      overlay.detach()
 *
 * El payload de setValues es todo-numerico (INT-003 §6): los campos de
 * digitos viajan como en v1; los de eleccion como presencia(1) + valor(W)
 * con W = ancho decimal de max (presencia 0 exige valor 0: canonico).
 *
 * Sin allocaciones en el camino caliente: los buffers se reservan una sola
 * vez en attach (INV-2); un fallo de datos nunca interrumpe la reproduccion
 * (INV-7): las mutadoras devuelven false y conservan el ultimo estado valido.
 */
(function (root) {
  "use strict";

  var EMPTY_GLYPH = 10;
  var TRANSPARENT_INDEX = 255;
  var NONE = 65535;
  var KIND_DIGITS = 0;
  var KIND_CHOICE = 1;

  function isFunction(value) { return typeof value === "function"; }

  /* norm: metadata normalizada por attach (misma forma para v1 y v2). */
  function Overlay(reader, norm) {
    var nSlots = norm.slots.length, nPatches = norm.patchW.length;
    var i, k, slot, field, wire, offset;
    this.reader = reader;
    this.nSlots = nSlots;
    this.nPatches = nPatches;
    this.fields = norm.fields;
    this.reservedFirst = norm.reservedFirst;
    /* compat v1: propiedades historicas del runtime F7 */
    if (norm.isV1) {
      this.glyphW = norm.patchW[0];
      this.glyphH = norm.patchH[0];
      this.nGlyphs = nPatches;
      this.glyphTable = norm.patchData;
    }
    this.patchData = norm.patchData;
    this._patchW = norm.patchW;
    this._patchH = norm.patchH;
    this._patchOff = new Uint32Array(nPatches);
    offset = 0;
    for (i = 0; i < nPatches; i++) {
      this._patchOff[i] = offset;
      offset += norm.patchW[i] * norm.patchH[i];
    }
    /* estado INT-001 §9.1 */
    this.active = true;
    this.restoreValid = false;
    this._slotX = new Uint16Array(nSlots);
    this._slotY = new Uint16Array(nSlots);
    this._slotW = new Uint16Array(nSlots);
    this._slotH = new Uint16Array(nSlots);
    this._slotStart = new Uint32Array(nSlots);
    this._slotEnd = new Uint32Array(nSlots);
    this._slotOn = new Uint8Array(nSlots);
    this._baseOff = new Uint32Array(nSlots);
    this._saved = new Uint8Array(nSlots);    /* pintados el frame anterior */
    this._restored = new Uint8Array(nSlots); /* pendientes de marcar */
    offset = 0;
    for (i = 0; i < nSlots; i++) {
      slot = norm.slots[i];
      this._slotX[i] = slot.x;
      this._slotY[i] = slot.y;
      this._slotW[i] = slot.w;
      this._slotH[i] = slot.h;
      this._slotStart[i] = slot.start;
      this._slotEnd[i] = slot.end;
      this._slotOn[i] = slot.flags & 1;
      this._baseOff[i] = offset;
      offset += slot.w * slot.h;
    }
    this.base = new Uint8Array(offset);
    /* valores por defecto: digitos -> parche vacio (patchBase+10);
     * eleccion y slots sin campo -> NONE (v1: todos vacios, como F7) */
    this._defaults = new Uint16Array(nSlots);
    for (i = 0; i < nSlots; i++) {
      this._defaults[i] = norm.isV1 ? EMPTY_GLYPH : NONE;
    }
    this._fieldIndex = {};
    this._fieldScratch = [];
    wire = 0;
    for (i = 0; i < norm.fields.length; i++) {
      field = norm.fields[i];
      this._fieldIndex["f" + field.fieldId] = i;
      this._fieldScratch[i] = 0;
      wire += field.wire;
      if (field.kind === KIND_DIGITS) {
        for (k = 0; k < field.slotIds.length; k++) {
          this._defaults[field.slotIds[k]] = field.patchBase + EMPTY_GLYPH;
        }
      }
    }
    this.digitCount = wire;
    this.values = new Uint16Array(nSlots);
    for (i = 0; i < nSlots; i++) this.values[i] = this._defaults[i];
  }

  /* Paso 1 de §9.2: devolver a cells las celdas base guardadas, ANTES de que
   * el reader decodifique. Marca los slots como restaurados para que
   * afterSeek() incluya sus rects en la union de celdas sucias (§9.4). */
  Overlay.prototype.beforeSeek = function () {
    var reader = this.reader;
    if (!reader || !this.restoreValid) return this;
    var cells = reader.cells, cols = reader.header.cols;
    var i, gy, gx, gw, gh, rowBase, slotRow;
    for (i = 0; i < this.nSlots; i++) {
      if (!this._saved[i]) continue;
      gw = this._slotW[i];
      gh = this._slotH[i];
      for (gy = 0; gy < gh; gy++) {
        rowBase = (this._slotY[i] + gy) * cols + this._slotX[i];
        slotRow = this._baseOff[i] + gy * gw;
        for (gx = 0; gx < gw; gx++) {
          cells[rowBase + gx] = this.base[slotRow + gx];
        }
      }
      this._saved[i] = 0;
      this._restored[i] = 1;
    }
    this.restoreValid = false;
    return this;
  };

  /* Pasos 3-5 de §9.2, despues de reader.seek(): guardar la base de los
   * slots activos con valor, pintar los parches de overlay.values y marcar
   * sucia la union del rect anterior (restaurado) y el actual. */
  Overlay.prototype.afterSeek = function () {
    var reader = this.reader;
    if (!reader) return this;
    var frame = reader.decodedIndex;
    var cells = reader.cells, cols = reader.header.cols;
    var i, gy, gx, gw, gh, rowBase, slotRow, patchRow, patch, value;
    var anySaved = 0;
    if (this.active && frame >= 0) {
      for (i = 0; i < this.nSlots; i++) {
        if (!this._slotOn[i]) continue;
        if (frame < this._slotStart[i] || frame > this._slotEnd[i]) continue;
        patch = this.values[i];
        if (patch >= this.nPatches) continue; /* NONE o valor defensivo */
        gw = this._slotW[i];
        gh = this._slotH[i];
        if (this._patchW[patch] !== gw || this._patchH[patch] !== gh) {
          continue;
        }
        for (gy = 0; gy < gh; gy++) {
          rowBase = (this._slotY[i] + gy) * cols + this._slotX[i];
          slotRow = this._baseOff[i] + gy * gw;
          patchRow = this._patchOff[patch] + gy * gw;
          for (gx = 0; gx < gw; gx++) {
            this.base[slotRow + gx] = cells[rowBase + gx];
            value = this.patchData[patchRow + gx];
            if (value !== TRANSPARENT_INDEX) cells[rowBase + gx] = value;
          }
        }
        this._saved[i] = 1;
        anySaved = 1;
      }
    }
    this.restoreValid = anySaved === 1;
    for (i = 0; i < this.nSlots; i++) {
      if (this._restored[i] || this._saved[i]) {
        reader.markRectDirty(this._slotX[i], this._slotY[i],
          this._slotW[i], this._slotH[i]);
      }
      this._restored[i] = 0;
    }
    return this;
  };

  Overlay.prototype._applyField = function (field, value) {
    var ids = field.slotIds, k, digit, rest, wrote;
    if (field.kind === KIND_CHOICE) {
      if (value < 0) {
        this.values[ids[0]] = NONE;
      } else {
        this.values[ids[0]] = field.patchBase + (value - field.min);
      }
      return;
    }
    rest = value;
    wrote = false;
    for (k = ids.length - 1; k >= 0; k--) {
      if (!field.pad && wrote && rest === 0) {
        this.values[ids[k]] = field.patchBase + EMPTY_GLYPH;
      } else {
        digit = rest % 10;
        this.values[ids[k]] = field.patchBase + digit;
        rest = (rest - digit) / 10;
        wrote = true;
      }
    }
  };

  Overlay.prototype.setField = function (fieldId, value) {
    if (!this.reader) return false;
    var index = this._fieldIndex["f" + fieldId];
    if (index === undefined) return false;
    var field = this.fields[index];
    value = Number(value);
    if (value !== value || value !== Math.floor(value)) return false;
    if (value < field.min || value > field.max) return false;
    this._applyField(field, value);
    this.active = true;
    return true;
  };

  /* Carga completa (§8.1 / INT-003 §6): payload todo-numerico en el orden de
   * la tabla de campos. Se valida TODO antes de aplicar nada: longitud,
   * caracteres, canonicidad de presencia y rango [min, max] de cada campo. */
  Overlay.prototype.setValues = function (digits) {
    if (!this.reader) return false;
    if (typeof digits !== "string" || digits.length !== this.digitCount) {
      return false;
    }
    var i, c, field, k, value, pos, presence;
    for (i = 0; i < digits.length; i++) {
      c = digits.charCodeAt(i);
      if (c < 48 || c > 57) return false;
    }
    pos = 0;
    for (i = 0; i < this.fields.length; i++) {
      field = this.fields[i];
      if (field.kind === KIND_CHOICE) {
        presence = digits.charCodeAt(pos) - 48;
        if (presence > 1) return false;
        value = 0;
        for (k = 1; k < field.wire; k++) {
          value = value * 10 + (digits.charCodeAt(pos + k) - 48);
        }
        if (presence === 0) {
          if (value !== 0) return false; /* canonico: sin valor -> ceros */
          this._fieldScratch[i] = -1;
        } else {
          if (value < field.min || value > field.max) return false;
          this._fieldScratch[i] = value;
        }
      } else {
        value = 0;
        for (k = 0; k < field.wire; k++) {
          value = value * 10 + (digits.charCodeAt(pos + k) - 48);
        }
        if (value < field.min || value > field.max) return false;
        this._fieldScratch[i] = value;
      }
      pos += field.wire;
    }
    for (i = 0; i < this.fields.length; i++) {
      this._applyField(this.fields[i], this._fieldScratch[i]);
    }
    this.active = true;
    return true;
  };

  Overlay.prototype.clearField = function (fieldId) {
    if (!this.reader) return false;
    var index = this._fieldIndex["f" + fieldId];
    if (index === undefined) return false;
    var field = this.fields[index], ids = field.slotIds, k;
    for (k = 0; k < ids.length; k++) {
      this.values[ids[k]] = this._defaults[ids[k]];
    }
    return true;
  };

  /* Restaura y desactiva: cells queda byte-identico a la reproduccion sin
   * overlay y los rects restaurados quedan marcados para el proximo draw. */
  Overlay.prototype.clear = function () {
    var reader = this.reader, i;
    if (reader && this.restoreValid) {
      this.beforeSeek();
      for (i = 0; i < this.nSlots; i++) {
        if (this._restored[i]) {
          reader.markRectDirty(this._slotX[i], this._slotY[i],
            this._slotW[i], this._slotH[i]);
        }
        this._restored[i] = 0;
      }
    } else {
      for (i = 0; i < this.nSlots; i++) this._restored[i] = 0;
    }
    for (i = 0; i < this.nSlots; i++) this.values[i] = this._defaults[i];
    this.active = false;
    this.restoreValid = false;
    return this;
  };

  Overlay.prototype.detach = function () {
    if (this.reader) this.clear();
    this.reader = null;
    return this;
  };

  function wireWidth(maximum) {
    var width = 1, threshold = 10;
    while (maximum >= threshold && width < 10) {
      width++;
      threshold *= 10;
    }
    return width;
  }

  /* Normaliza un meta v1 (glifos uniformes) a la forma interna, verificando
   * lo que la seguridad del runtime exige (mismos chequeos que F7). */
  function normalizeV1(reader, meta) {
    var i, k, cols, rows, area, glyphLen, slot, slots, field, fields, ids;
    if (!meta.slots || !meta.fields || !meta.glyphTable) return null;
    cols = reader.header.cols;
    rows = reader.header.rows;
    if (!(meta.glyphW >= 1) || !(meta.glyphH >= 1)) return null;
    area = meta.glyphW * meta.glyphH;
    /* el glifo 10 (vacio) es parte del contrato: clearField lo pinta */
    if (!(meta.nGlyphs >= EMPTY_GLYPH + 1)) return null;
    glyphLen = meta.nGlyphs * area;
    if (meta.glyphTable.length !== glyphLen) return null;
    for (i = 0; i < glyphLen; i++) {
      if (meta.glyphTable[i] < 246 || meta.glyphTable[i] > 255) return null;
    }
    if (!checkPaletteTail(reader, meta.reservedRgb, 10)) return null;
    slots = [];
    for (i = 0; i < meta.slots.length; i++) {
      slot = meta.slots[i];
      if (slot.x < 0 || slot.y < 0 || slot.x + meta.glyphW > cols ||
          slot.y + meta.glyphH > rows) return null;
      if (slot.end < slot.start) return null;
      slots.push({ x: slot.x, y: slot.y, w: meta.glyphW, h: meta.glyphH,
        start: slot.start, end: slot.end, flags: slot.flags });
    }
    fields = [];
    for (i = 0; i < meta.fields.length; i++) {
      field = meta.fields[i];
      ids = field.slotIds;
      if (!ids || !ids.length) return null;
      for (k = 0; k < ids.length; k++) {
        if (ids[k] < 0 || ids[k] >= meta.slots.length) return null;
      }
      if (field.max < field.min) return null;
      fields.push({ fieldId: field.fieldId, kind: KIND_DIGITS,
        slotIds: ids, min: field.min, max: field.max, pad: field.pad,
        patchBase: 0, wire: ids.length });
    }
    var patchW = new Uint16Array(meta.nGlyphs);
    var patchH = new Uint16Array(meta.nGlyphs);
    for (i = 0; i < meta.nGlyphs; i++) {
      patchW[i] = meta.glyphW;
      patchH[i] = meta.glyphH;
    }
    return { isV1: true, reservedFirst: 246, patchW: patchW, patchH: patchH,
      patchData: meta.glyphTable, slots: slots, fields: fields };
  }

  /* Normaliza un meta v2 (parches heterogeneos, kind 0/1). */
  function normalizeV2(reader, meta) {
    var i, k, cols, rows, reservedFirst, patch, slot, slots, field, fields;
    var span, first, total, offset, ids;
    if (!meta.patches || !meta.slots || !meta.fields) return null;
    if (!(meta.palReserved >= 10) || !(meta.palReserved <= 64)) return null;
    reservedFirst = 256 - meta.palReserved;
    cols = reader.header.cols;
    rows = reader.header.rows;
    if (!meta.patches.length) return null;
    total = 0;
    for (i = 0; i < meta.patches.length; i++) {
      patch = meta.patches[i];
      if (!(patch.w >= 1) || !(patch.h >= 1)) return null;
      if (!patch.data || patch.data.length !== patch.w * patch.h) return null;
      for (k = 0; k < patch.data.length; k++) {
        if (patch.data[k] < reservedFirst || patch.data[k] > 255) return null;
      }
      total += patch.data.length;
    }
    if (!checkPaletteTail(reader, meta.reservedRgb, meta.palReserved)) {
      return null;
    }
    slots = [];
    for (i = 0; i < meta.slots.length; i++) {
      slot = meta.slots[i];
      if (!(slot.w >= 1) || !(slot.h >= 1)) return null;
      if (slot.x < 0 || slot.y < 0 || slot.x + slot.w > cols ||
          slot.y + slot.h > rows) return null;
      if (slot.end < slot.start) return null;
      slots.push({ x: slot.x, y: slot.y, w: slot.w, h: slot.h,
        start: slot.start, end: slot.end, flags: slot.flags });
    }
    fields = [];
    for (i = 0; i < meta.fields.length; i++) {
      field = meta.fields[i];
      ids = field.slotIds;
      if (!ids || !ids.length) return null;
      for (k = 0; k < ids.length; k++) {
        if (ids[k] < 0 || ids[k] >= meta.slots.length) return null;
      }
      if (field.max < field.min) return null;
      if (field.kind === KIND_DIGITS) {
        span = EMPTY_GLYPH + 1;
      } else if (field.kind === KIND_CHOICE) {
        if (ids.length !== 1) return null;
        span = field.max - field.min + 1;
      } else {
        return null;
      }
      if (field.patchBase + span > meta.patches.length) return null;
      first = slots[ids[0]];
      for (k = 0; k < ids.length; k++) {
        if (slots[ids[k]].w !== first.w || slots[ids[k]].h !== first.h) {
          return null;
        }
      }
      for (k = field.patchBase; k < field.patchBase + span; k++) {
        if (meta.patches[k].w !== first.w || meta.patches[k].h !== first.h) {
          return null;
        }
      }
      fields.push({ fieldId: field.fieldId, kind: field.kind,
        slotIds: ids, min: field.min, max: field.max, pad: field.pad,
        patchBase: field.patchBase,
        wire: field.kind === KIND_CHOICE ?
          1 + wireWidth(field.max) : ids.length });
    }
    var patchW = new Uint16Array(meta.patches.length);
    var patchH = new Uint16Array(meta.patches.length);
    var patchData = new Uint8Array(total);
    offset = 0;
    for (i = 0; i < meta.patches.length; i++) {
      patch = meta.patches[i];
      patchW[i] = patch.w;
      patchH[i] = patch.h;
      for (k = 0; k < patch.data.length; k++) {
        patchData[offset + k] = patch.data[k];
      }
      offset += patch.data.length;
    }
    return { isV1: false, reservedFirst: reservedFirst, patchW: patchW,
      patchH: patchH, patchData: patchData, slots: slots, fields: fields };
  }

  /* La reserva exige la paleta completa y que los RGB del sidecar coincidan
   * con la cola de la paleta del bundle (INV-4). */
  function checkPaletteTail(reader, reservedRgb, palReserved) {
    var i, pal;
    if (reader.header.palSize !== 256) return false;
    pal = reader.palette;
    if (!pal || reader.paletteEntries !== 256) return false;
    if (!reservedRgb || reservedRgb.length !== 3 * palReserved) return false;
    for (i = 0; i < 3 * palReserved; i++) {
      if (pal[(256 - palReserved) * 3 + i] !== reservedRgb[i]) return false;
    }
    return true;
  }

  /* Valida lo que la seguridad del runtime exige y devuelve la instancia, o
   * null si algo no cumple (contrato §9.5). No lanza: un sidecar viejo junto
   * a un video nuevo simplemente no activa el overlay (INT-001 §7.1). */
  function attach(reader, meta) {
    var norm;
    if (!reader || !reader.header || !reader.cells) return null;
    if (!isFunction(reader.seek) || !isFunction(reader.markRectDirty)) {
      return null;
    }
    if (!meta) return null;
    norm = meta.version === 2 ? normalizeV2(reader, meta)
      : normalizeV1(reader, meta);
    if (!norm) return null;
    return new Overlay(reader, norm);
  }

  root.ASCILINEOverlay = { attach: attach };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { attach: attach };
  }
})(typeof window !== "undefined" ? window : this);
