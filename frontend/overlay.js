/*
 * overlay.js - F7: runtime de la intervencion matricial (INT-001 §9).
 *
 * Escribe glifos como INDICES de paleta reservados (246..255) sobre la misma
 * matriz de celdas del reader, y restaura las celdas base ANTES de cada
 * decodificacion para que ninguna cadena DELTA se calcule sobre pixeles
 * contaminados (INT-001 §9.2, paso 1 antes del paso 2).
 *
 * API (INT-001 §9.5):
 *   ASCILINEOverlay.attach(reader, meta) -> instancia o null si meta invalida
 *   overlay.beforeSeek()   paso 1: restaurar overlay.base sobre cells
 *   overlay.afterSeek()    pasos 3-5: guardar base, pintar glifos, marcar sucio
 *   overlay.setField(fieldId, value)  overlay.setValues(digitString)
 *   overlay.clearField(fieldId)       overlay.clear()      overlay.detach()
 *
 * `meta` es el resultado de ASCL_parseSlots (slots.js), ya validado contra el
 * sidecar; attach re-verifica lo que la seguridad del runtime necesita (glifos
 * en 246..255, slots dentro de la grilla del reader, paleta completa con los
 * RGB reservados del sidecar) y devuelve null ante cualquier incumplimiento.
 *
 * Sin allocaciones en el camino caliente: overlay.base y overlay.values se
 * reservan una sola vez en attach (INV-2); un fallo de datos nunca interrumpe
 * la reproduccion (INV-7): las mutadoras devuelven false y conservan el
 * ultimo estado valido.
 */
(function (root) {
  "use strict";

  var EMPTY_GLYPH = 10;
  var RESERVED_FIRST = 246;
  var TRANSPARENT_INDEX = 255;

  function isFunction(value) { return typeof value === "function"; }

  function Overlay(reader, meta) {
    var nSlots = meta.slots.length, area = meta.glyphW * meta.glyphH;
    var i, slot, field, total;
    this.reader = reader;
    this.glyphW = meta.glyphW;
    this.glyphH = meta.glyphH;
    this.nGlyphs = meta.nGlyphs;
    this.glyphTable = meta.glyphTable;
    this.nSlots = nSlots;
    this.fields = meta.fields;
    /* estado INT-001 §9.1 */
    this.active = true;
    this.restoreValid = false;
    this.base = new Uint8Array(nSlots * area);
    this.values = new Uint8Array(nSlots);
    this._area = area;
    this._saved = new Uint8Array(nSlots);    /* rects pintados el frame anterior */
    this._restored = new Uint8Array(nSlots); /* restaurados, pendientes de marcar */
    this._slotX = new Uint16Array(nSlots);
    this._slotY = new Uint16Array(nSlots);
    this._slotStart = new Uint32Array(nSlots);
    this._slotEnd = new Uint32Array(nSlots);
    this._slotOn = new Uint8Array(nSlots);
    for (i = 0; i < nSlots; i++) {
      slot = meta.slots[i];
      this._slotX[i] = slot.x;
      this._slotY[i] = slot.y;
      this._slotStart[i] = slot.start;
      this._slotEnd[i] = slot.end;
      this._slotOn[i] = slot.flags & 1;
      this.values[i] = EMPTY_GLYPH;
    }
    this._fieldIndex = {};
    this._fieldScratch = [];
    total = 0;
    for (i = 0; i < meta.fields.length; i++) {
      field = meta.fields[i];
      this._fieldIndex["f" + field.fieldId] = i;
      this._fieldScratch[i] = 0;
      total += field.slotIds.length;
    }
    this.digitCount = total;
  }

  /* Paso 1 de §9.2: devolver a cells las celdas base guardadas, ANTES de que
   * el reader decodifique. Marca los slots como restaurados para que
   * afterSeek() incluya sus rects en la union de celdas sucias (§9.4). */
  Overlay.prototype.beforeSeek = function () {
    var reader = this.reader;
    if (!reader || !this.restoreValid) return this;
    var cells = reader.cells, cols = reader.header.cols;
    var gw = this.glyphW, gh = this.glyphH, area = this._area;
    var i, gy, gx, rowBase, slotRow;
    for (i = 0; i < this.nSlots; i++) {
      if (!this._saved[i]) continue;
      for (gy = 0; gy < gh; gy++) {
        rowBase = (this._slotY[i] + gy) * cols + this._slotX[i];
        slotRow = i * area + gy * gw;
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

  /* Pasos 3-5 de §9.2, despues de reader.seek(): guardar la base de los slots
   * activos en el frame decodificado, pintar los glifos de overlay.values y
   * marcar sucia la union del rect anterior (restaurado) y el actual. */
  Overlay.prototype.afterSeek = function () {
    var reader = this.reader;
    if (!reader) return this;
    var frame = reader.decodedIndex;
    var cells = reader.cells, cols = reader.header.cols;
    var gw = this.glyphW, gh = this.glyphH, area = this._area;
    var i, gy, gx, rowBase, slotRow, glyph, glyphRow, value, anySaved = 0;
    if (this.active && frame >= 0) {
      for (i = 0; i < this.nSlots; i++) {
        if (!this._slotOn[i]) continue;
        if (frame < this._slotStart[i] || frame > this._slotEnd[i]) continue;
        glyph = this.values[i];
        if (glyph >= this.nGlyphs) glyph = EMPTY_GLYPH;
        for (gy = 0; gy < gh; gy++) {
          rowBase = (this._slotY[i] + gy) * cols + this._slotX[i];
          slotRow = i * area + gy * gw;
          glyphRow = glyph * area + gy * gw;
          for (gx = 0; gx < gw; gx++) {
            this.base[slotRow + gx] = cells[rowBase + gx];
            value = this.glyphTable[glyphRow + gx];
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
        reader.markRectDirty(this._slotX[i], this._slotY[i], gw, gh);
      }
      this._restored[i] = 0;
    }
    return this;
  };

  Overlay.prototype._applyField = function (field, value) {
    var ids = field.slotIds, k, digit, rest = value, wrote = false;
    for (k = ids.length - 1; k >= 0; k--) {
      if (!field.pad && wrote && rest === 0) {
        this.values[ids[k]] = EMPTY_GLYPH;
      } else {
        digit = rest % 10;
        this.values[ids[k]] = digit;
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

  /* Carga completa (§8.1): un caracter 0..9 por slot, en el orden de la tabla
   * de campos, mas significativo primero. Se valida TODO antes de aplicar
   * nada: longitud, caracteres y rango [min, max] de cada campo. */
  Overlay.prototype.setValues = function (digits) {
    if (!this.reader) return false;
    if (typeof digits !== "string" || digits.length !== this.digitCount) {
      return false;
    }
    var i, c, field, k, value, pos;
    for (i = 0; i < digits.length; i++) {
      c = digits.charCodeAt(i);
      if (c < 48 || c > 57) return false;
    }
    pos = 0;
    for (i = 0; i < this.fields.length; i++) {
      field = this.fields[i];
      value = 0;
      for (k = 0; k < field.slotIds.length; k++) {
        value = value * 10 + (digits.charCodeAt(pos + k) - 48);
      }
      if (value < field.min || value > field.max) return false;
      this._fieldScratch[i] = value;
      pos += field.slotIds.length;
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
    var ids = this.fields[index].slotIds, k;
    for (k = 0; k < ids.length; k++) this.values[ids[k]] = EMPTY_GLYPH;
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
            this.glyphW, this.glyphH);
        }
        this._restored[i] = 0;
      }
    } else {
      for (i = 0; i < this.nSlots; i++) this._restored[i] = 0;
    }
    for (i = 0; i < this.nSlots; i++) this.values[i] = EMPTY_GLYPH;
    this.active = false;
    this.restoreValid = false;
    return this;
  };

  Overlay.prototype.detach = function () {
    if (this.reader) this.clear();
    this.reader = null;
    return this;
  };

  /* Valida lo que la seguridad del runtime exige y devuelve la instancia, o
   * null si algo no cumple (contrato §9.5). No lanza: un sidecar viejo junto
   * a un video nuevo simplemente no activa el overlay (INT-001 §7.1). */
  function attach(reader, meta) {
    var i, k, cols, rows, area, glyphLen, slot, field, ids, pal;
    if (!reader || !reader.header || !reader.cells) return null;
    if (!isFunction(reader.seek) || !isFunction(reader.markRectDirty)) {
      return null;
    }
    if (!meta || !meta.slots || !meta.fields || !meta.glyphTable) return null;
    cols = reader.header.cols;
    rows = reader.header.rows;
    if (!(meta.glyphW >= 1) || !(meta.glyphH >= 1)) return null;
    area = meta.glyphW * meta.glyphH;
    /* el glifo 10 (vacio) es parte del contrato: clearField lo pinta */
    if (!(meta.nGlyphs >= EMPTY_GLYPH + 1)) return null;
    glyphLen = meta.nGlyphs * area;
    if (meta.glyphTable.length !== glyphLen) return null;
    for (i = 0; i < glyphLen; i++) {
      if (meta.glyphTable[i] < RESERVED_FIRST || meta.glyphTable[i] > 255) {
        return null;
      }
    }
    /* la reserva vive en 246..255: hace falta la paleta completa y que los
     * diez RGB del sidecar coincidan con los del bundle (INV-4) */
    if (reader.header.palSize !== 256) return null;
    pal = reader.palette;
    if (!pal || reader.paletteEntries !== 256) return null;
    if (!meta.reservedRgb || meta.reservedRgb.length !== 30) return null;
    for (i = 0; i < 30; i++) {
      if (pal[RESERVED_FIRST * 3 + i] !== meta.reservedRgb[i]) return null;
    }
    for (i = 0; i < meta.slots.length; i++) {
      slot = meta.slots[i];
      if (slot.x < 0 || slot.y < 0 || slot.x + meta.glyphW > cols ||
          slot.y + meta.glyphH > rows) return null;
      if (slot.end < slot.start) return null;
    }
    for (i = 0; i < meta.fields.length; i++) {
      field = meta.fields[i];
      ids = field.slotIds;
      if (!ids || !ids.length) return null;
      for (k = 0; k < ids.length; k++) {
        if (ids[k] < 0 || ids[k] >= meta.slots.length) return null;
      }
      if (field.max < field.min) return null;
    }
    return new Overlay(reader, meta);
  }

  root.ASCILINEOverlay = { attach: attach };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { attach: attach };
  }
})(typeof window !== "undefined" ? window : this);
