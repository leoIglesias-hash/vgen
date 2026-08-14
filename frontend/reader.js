/*
 * reader.js - Parser y decoder defensivo ASCL v1, ES5.
 *
 * Mantiene una vista del archivo, un bitset de keyframes y un unico scratch
 * reutilizable para inflate. No materializa offsets ni frames como Array JS.
 */
(function (root) {
  "use strict";

  var inflateModule = null;
  if (typeof require === "function") inflateModule = require("./inflate.js");
  var inflateZlib = (typeof root.ASCL_inflateZlib === "function")
    ? root.ASCL_inflateZlib : (inflateModule && inflateModule.ASCL_inflateZlib);
  var inflateZlibInto = (typeof root.ASCL_inflateZlibInto === "function")
    ? root.ASCL_inflateZlibInto : (inflateModule && inflateModule.ASCL_inflateZlibInto);

  var MODE_BW = 0, MODE_PAL = 1, MODE_RGB = 2, MODE_PIXEL = 3;
  var TAG_RAW = 0, TAG_ZLIB = 1, TAG_DELTA = 2, TAG_DELTA_MASK = 3;
  var FLAG_PAL_PER_SCENE = 2, FLAG_PAL_GLOBAL = 4, FLAG_OFFSET_TABLE = 8;
  var BPC = { 0: 1, 1: 2, 2: 4, 3: 1 };
  var CELL_FMT = { 0: 1, 1: 2, 2: 3, 3: 3 };
  var HEADER_SIZE = 32;
  var MAX_SCRATCH_BYTES = 64 * 1024 * 1024;
  var crcTable = null;
  var popCount = null;
  var lowBitIndex = null;
  var zeroBlock = new Uint8Array(4096);

  function fail(message) { throw new Error("ASCL: " + message); }

  function parseHeader(dv) {
    if (dv.byteLength < HEADER_SIZE) fail("header truncado");
    /* ASCLVID1 comparte los cuatro primeros bytes con ASCL. */
    if (dv.byteLength >= 8 && dv.getUint8(4) === 0x56 && dv.getUint8(5) === 0x49 &&
        dv.getUint8(6) === 0x44 && dv.getUint8(7) === 0x31 &&
        dv.getUint8(0) === 0x41 && dv.getUint8(1) === 0x53 &&
        dv.getUint8(2) === 0x43 && dv.getUint8(3) === 0x4c) {
      fail("es un .asclv (bundle), no un .ascl suelto");
    }
    if (dv.getUint8(0) !== 0x41 || dv.getUint8(1) !== 0x53 ||
        dv.getUint8(2) !== 0x43 || dv.getUint8(3) !== 0x4c) {
      fail("magic invalido");
    }
    return {
      version: dv.getUint8(4),
      mode: dv.getUint8(5),
      flags: dv.getUint8(6),
      fps: dv.getUint8(7),
      cols: dv.getUint16(8, true),
      rows: dv.getUint16(10, true),
      palSize: dv.getUint16(12, true),
      nFrames: dv.getUint32(14, true),
      rampLen: dv.getUint8(18),
      cellFmt: dv.getUint8(19),
      dataOff: dv.getUint32(20, true),
      charAspect: dv.getUint16(24, true) / 1000.0,
      crc32: dv.getUint32(28, true)
    };
  }

  function makeCrcTable() {
    var table = new Uint32Array(256), i, c, k;
    for (i = 0; i < 256; i++) {
      c = i;
      for (k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[i] = c >>> 0;
    }
    return table;
  }

  function crc32(bytes, start) {
    var crc = 0xffffffff, i;
    if (!crcTable) crcTable = makeCrcTable();
    for (i = start; i < bytes.length; i++) crc = crcTable[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function getPopCount(byte) {
    var i;
    if (!popCount) {
      popCount = new Uint8Array(256);
      for (i = 1; i < 256; i++) popCount[i] = popCount[i >>> 1] + (i & 1);
    }
    return popCount[byte];
  }

  function setKey(bits, index) { bits[index >>> 3] |= (1 << (index & 7)); }
  function hasKey(bits, index) { return (bits[index >>> 3] & (1 << (index & 7))) !== 0; }

  function clearBitset(bits) {
    var i = 0, remaining;
    while (i + zeroBlock.length <= bits.length) {
      bits.set(zeroBlock, i);
      i += zeroBlock.length;
    }
    remaining = bits.length - i;
    if (remaining) bits.set(zeroBlock.subarray(0, remaining), i);
  }

  function validateHeader(dv, h, byteLength) {
    var tableEnd, n, bpc, deltaMax;
    if (h.version !== 1) fail("version no soportada " + h.version);
    if (h.mode < MODE_BW || h.mode > MODE_PIXEL) fail("modo invalido " + h.mode);
    if ((h.flags & 0xe0) !== 0) fail("flags reservados activos");
    if ((h.flags & FLAG_OFFSET_TABLE) === 0) fail("falta tabla de offsets v1");
    if ((h.flags & FLAG_PAL_PER_SCENE) && (h.flags & FLAG_PAL_GLOBAL)) {
      fail("flags de paleta incompatibles");
    }
    if (h.fps === 0) fail("fps invalido");
    if (h.cols === 0 || h.rows === 0) fail("dimensiones vacias");
    if (h.nFrames === 0) fail("video sin frames");
    if (h.cellFmt !== CELL_FMT[h.mode]) fail("cell_fmt incompatible con modo");
    if (dv.getUint16(26, true) !== 0) fail("reserved debe ser cero");
    if (dv.getUint16(24, true) === 0) fail("char aspect invalido");
    if (h.dataOff !== HEADER_SIZE + h.rampLen) fail("data_off invalido");
    if (h.dataOff > byteLength) fail("rampa truncada");
    if (h.mode === MODE_PIXEL) {
      if (h.rampLen !== 0) fail("PIXEL no admite rampa");
    } else if (h.rampLen === 0) {
      fail("modo ASCII sin rampa");
    }
    if (h.mode === MODE_PIXEL || h.mode === MODE_PAL) {
      if (h.palSize < 1 || h.palSize > 256) fail("pal_size invalido");
    } else if (h.palSize !== 0) {
      fail("paleta presente en modo sin paleta");
    }
    tableEnd = h.dataOff + h.nFrames * 4;
    if (tableEnd > byteLength) fail("tabla de offsets truncada");
    n = h.cols * h.rows;
    bpc = BPC[h.mode];
    deltaMax = n * (4 + bpc);
    if (deltaMax > MAX_SCRATCH_BYTES) fail("dimensiones exceden limite operativo v1");
    return { tableEnd: tableEnd, n: n, bpc: bpc };
  }

  function validatePlanes(planes, mode, n, rampLen, paletteEntries) {
    var i;
    if (mode === MODE_PIXEL) {
      if (!paletteEntries) fail("frame PIXEL sin paleta");
      if (paletteEntries < 256) {
        for (i = 0; i < n; i++) if (planes[i] >= paletteEntries) fail("indice de paleta fuera de rango");
      }
    } else if (mode === MODE_BW) {
      for (i = 0; i < n; i++) if (planes[i] >= rampLen) fail("indice de rampa fuera de rango");
    } else if (mode === MODE_PAL) {
      if (!paletteEntries) fail("frame ASCII_PAL sin paleta");
      for (i = 0; i < n; i++) {
        if (planes[i] >= rampLen) fail("indice de rampa fuera de rango");
        if (planes[n + i] >= paletteEntries) fail("indice de paleta fuera de rango");
      }
    } else {
      for (i = 0; i < n; i++) if (planes[i] >= rampLen) fail("indice de rampa fuera de rango");
    }
  }

  function planesToCells(planes, mode, n, cells) {
    var i, b;
    if (mode === MODE_PIXEL || mode === MODE_BW) {
      cells.set(planes.subarray(0, n));
    } else if (mode === MODE_PAL) {
      for (i = 0; i < n; i++) {
        cells[i * 2] = planes[i];
        cells[i * 2 + 1] = planes[n + i];
      }
    } else {
      for (i = 0; i < n; i++) {
        b = n + i * 3;
        cells[i * 4] = planes[i];
        cells[i * 4 + 1] = planes[b];
        cells[i * 4 + 2] = planes[b + 1];
        cells[i * 4 + 3] = planes[b + 2];
      }
    }
  }

  function Reader(buffer, byteOffset, byteLength) {
    var parsed, h, r, i, o, blockLen, blockEnd, p, tag, palCount, palBytes;
    var expected, currentPaletteCount = 0, firstPalette = null, firstPaletteCount = 0;
    if (!buffer || typeof buffer.byteLength !== "number") fail("ArrayBuffer invalido");
    byteOffset = byteOffset === undefined ? 0 : Number(byteOffset);
    byteLength = byteLength === undefined ? buffer.byteLength - byteOffset : Number(byteLength);
    if (byteOffset < 0 || byteLength < HEADER_SIZE ||
        byteOffset !== Math.floor(byteOffset) || byteLength !== Math.floor(byteLength) ||
        byteOffset + byteLength > buffer.byteLength) fail("rango .ascl invalido");

    /* Vista directa dentro del .asclv: no duplica el video completo. */
    this.bytes = new Uint8Array(buffer, byteOffset, byteLength);
    this.dv = new DataView(buffer, byteOffset, byteLength);
    this.header = parseHeader(this.dv);
    h = this.header;
    parsed = validateHeader(this.dv, h, byteLength);
    this.bpc = parsed.bpc;
    this.n = parsed.n;
    this._tableEnd = parsed.tableEnd;
    this._fullLength = this.n * this.bpc;
    this._deltaMax = this.n * (4 + this.bpc);
    this._maskLength = Math.floor((this.n + 7) / 8);
    this._maskMax = this._maskLength + this.n * this.bpc;
    /* Se ajusta durante el scan al mayor tag realmente presente en el archivo. */
    this._scratchMax = 0;
    this._scratch = null;
    this.actualLength = 0;

    if (h.crc32 && crc32(this.bytes, HEADER_SIZE) !== h.crc32) fail("CRC32 invalido");

    this.ramp = "";
    for (r = 0; r < h.rampLen; r++) this.ramp += String.fromCharCode(this.bytes[HEADER_SIZE + r]);
    this.keyBits = new Uint8Array(Math.floor((h.nFrames + 7) / 8));

    /* Scan estructural: valida todos los bloques sin materializar metadatos por frame. */
    expected = parsed.tableEnd;
    for (i = 0; i < h.nFrames; i++) {
      o = this._offset(i);
      if (o !== expected) fail("offset no contiguo en frame " + i);
      if (o > byteLength - 7) fail("frame truncado " + i);
      blockLen = this.dv.getUint32(o, true);
      if (blockLen < 3) fail("block_len invalido en frame " + i);
      blockEnd = o + 4 + blockLen;
      if (blockEnd > byteLength) fail("block fuera de rango en frame " + i);
      p = o + 4;
      tag = this.bytes[p++];
      if (tag > TAG_DELTA_MASK) fail("tag desconocido " + tag);
      if (tag === TAG_ZLIB && this._fullLength > this._scratchMax) this._scratchMax = this._fullLength;
      else if (tag === TAG_DELTA && this._deltaMax > this._scratchMax) this._scratchMax = this._deltaMax;
      else if (tag === TAG_DELTA_MASK && this._maskMax > this._scratchMax) this._scratchMax = this._maskMax;
      palCount = this.dv.getUint16(p, true); p += 2;
      if (palCount > h.palSize || palCount > 256) fail("pal_count fuera de rango");
      if (h.mode !== MODE_PIXEL && h.mode !== MODE_PAL && palCount !== 0) fail("paleta en modo incompatible");
      if ((tag === TAG_DELTA || tag === TAG_DELTA_MASK) && palCount !== 0) fail("DELTA no puede cambiar paleta");
      palBytes = palCount * 3;
      if (p + palBytes > blockEnd) fail("paleta truncada en frame " + i);
      if (palCount) {
        currentPaletteCount = palCount;
        if (firstPalette === null) {
          firstPalette = this.bytes.subarray(p, p + palBytes);
          firstPaletteCount = palCount;
        }
      }
      p += palBytes;
      if (tag === TAG_RAW || tag === TAG_ZLIB) setKey(this.keyBits, i);
      else if (i === 0) fail("primer frame no es keyframe");
      if (tag === TAG_RAW && blockEnd - p !== this._fullLength) fail("RAW con longitud incorrecta");
      if (tag !== TAG_RAW && blockEnd === p) fail("payload comprimido vacio");
      if ((h.mode === MODE_PIXEL || h.mode === MODE_PAL) && !currentPaletteCount) fail("frame sin paleta activa");
      if ((h.flags & FLAG_PAL_GLOBAL) && i === 0 && !palCount) fail("paleta global ausente");
      if ((h.flags & FLAG_PAL_GLOBAL) && i > 0 && palCount) fail("paleta global reemitida");
      if ((h.flags & FLAG_PAL_PER_SCENE) && (tag === TAG_RAW || tag === TAG_ZLIB) && !palCount) {
        fail("keyframe temporal sin paleta");
      }
      if (!(h.flags & (FLAG_PAL_GLOBAL | FLAG_PAL_PER_SCENE)) &&
          (h.mode === MODE_PIXEL || h.mode === MODE_PAL) && !palCount) {
        fail("paleta per-frame ausente");
      }
      expected = blockEnd;
    }
    if (expected !== byteLength) fail("bytes extra al final");

    this._initialPalette = firstPalette;
    this._initialPaletteEntries = firstPaletteCount;
    this.palette = firstPalette;
    this.paletteEntries = firstPaletteCount;
    this.cells = new Uint8Array(this._fullLength);
    /* Bitset persistente: 1 bit por celda, unido durante cada seek. */
    this.dirtyCellBits = new Uint8Array(this._maskLength);
    this.dirtyCellCount = 0;
    this.decodedIndex = -1;
    this.dirtyFull = false;
    this.dirtyY0 = h.rows;
    this.dirtyY1 = -1;
  }

  Reader.prototype._offset = function (index) {
    return this.dv.getUint32(this.header.dataOff + index * 4, true);
  };

  Reader.prototype._isKey = function (index) { return hasKey(this.keyBits, index); };

  Reader.prototype._inflate = function (payload, maxLength) {
    var raw, capacity, next;
    if (!inflateZlib) fail("inflate zlib no disponible");
    if (!this._scratch) {
      capacity = Math.min(maxLength, this._fullLength);
      this._scratch = new Uint8Array(capacity);
    }
    if (inflateZlibInto) {
      while (1) {
        try {
          this.actualLength = inflateZlibInto(payload, this._scratch, maxLength);
          break;
        } catch (error) {
          if (!error || error.code !== "ASCL_OUTPUT_BUFFER") throw error;
          next = Math.min(maxLength, Math.max(error.required || 0, this._scratch.length * 2));
          if (next <= this._scratch.length) throw error;
          this._scratch = new Uint8Array(next);
        }
      }
    } else {
      /* Compatibilidad si reader nuevo se carga accidentalmente con inflate legacy. */
      raw = inflateZlib(payload, maxLength);
      if (raw.length > maxLength) fail("inflate supera limite");
      if (raw.length > this._scratch.length) this._scratch = new Uint8Array(raw.length);
      this._scratch.set(raw);
      this.actualLength = raw.length;
    }
    return this._scratch;
  };

  Reader.prototype._validateChangedValues = function (raw, start, count) {
    var mode = this.header.mode, bpc = this.bpc, rampLen = this.header.rampLen;
    var paletteEntries = this.paletteEntries, i, p;
    if (mode === MODE_PIXEL) {
      if (!paletteEntries) fail("DELTA sin paleta");
      if (paletteEntries < 256) {
        for (i = 0; i < count; i++) if (raw[start + i] >= paletteEntries) fail("indice de paleta fuera de rango");
      }
    } else if (mode === MODE_BW) {
      for (i = 0; i < count; i++) if (raw[start + i] >= rampLen) fail("indice de rampa fuera de rango");
    } else if (mode === MODE_PAL) {
      if (!paletteEntries) fail("DELTA sin paleta");
      for (i = 0; i < count; i++) {
        p = start + i * bpc;
        if (raw[p] >= rampLen || raw[p + 1] >= paletteEntries) fail("celda DELTA fuera de rango");
      }
    } else {
      for (i = 0; i < count; i++) if (raw[start + i * bpc] >= rampLen) fail("indice de rampa fuera de rango");
    }
  };

  Reader.prototype._decodeOne = function (index) {
    var o = this._offset(index), blockLen = this.dv.getUint32(o, true), blockEnd = o + 4 + blockLen;
    var p = o + 4, tag = this.bytes[p++], palCount = this.dv.getUint16(p, true), palBytes = palCount * 3;
    var payload, raw, actual, mode = this.header.mode, n = this.n, bpc = this.bpc;
    var k, rdv, valueOffset, j, m, off, base, vb, maskLen, changed, vp, byte, validBits;
    var dirtyByte, dirtyMask, newBits;
    var lo = -1, hi = -1, full = false, cells = this.cells;
    var nextPalette = this.palette, nextPaletteEntries = this.paletteEntries;

    p += 2;
    if (blockEnd > this.bytes.length || p + palBytes > blockEnd || tag > TAG_DELTA_MASK) fail("frame mutado o corrupto");
    if (palCount > this.header.palSize || palCount > 256) fail("pal_count fuera de rango");
    if ((tag === TAG_DELTA || tag === TAG_DELTA_MASK) && palCount) fail("DELTA no puede cambiar paleta");
    if (palCount) {
      nextPalette = this.bytes.subarray(p, p + palBytes);
      nextPaletteEntries = palCount;
      p += palBytes;
    }
    payload = this.bytes.subarray(p, blockEnd);

    if (tag === TAG_RAW) {
      if (payload.length !== this._fullLength) fail("RAW con longitud incorrecta");
      validatePlanes(payload, mode, n, this.header.rampLen, nextPaletteEntries);
      planesToCells(payload, mode, n, cells);
      full = true;
    } else if (tag === TAG_ZLIB) {
      raw = this._inflate(payload, this._fullLength);
      actual = this.actualLength;
      if (actual !== this._fullLength) fail("ZLIB con longitud descomprimida incorrecta");
      validatePlanes(raw, mode, n, this.header.rampLen, nextPaletteEntries);
      planesToCells(raw, mode, n, cells);
      full = true;
    } else if (tag === TAG_DELTA) {
      raw = this._inflate(payload, this._deltaMax);
      actual = this.actualLength;
      if (actual % (4 + bpc) !== 0) fail("DELTA con longitud invalida");
      k = actual / (4 + bpc);
      if (k > n) fail("DELTA excede cantidad de celdas");
      rdv = new DataView(raw.buffer, raw.byteOffset, actual);
      valueOffset = k * 4;
      for (j = 0; j < k; j++) {
        off = rdv.getUint32(j * 4, true);
        if (off >= n) fail("offset DELTA fuera de rango");
      }
      this._validateChangedValues(raw, valueOffset, k);
      for (j = 0; j < k; j++) {
        off = rdv.getUint32(j * 4, true);
        if (lo < 0 || off < lo) lo = off;
        if (off > hi) hi = off;
        if (!this._dFull) {
          dirtyByte = off >>> 3;
          dirtyMask = 1 << (off & 7);
          if ((this.dirtyCellBits[dirtyByte] & dirtyMask) === 0) {
            this.dirtyCellBits[dirtyByte] |= dirtyMask;
            this._dCellCount++;
          }
        }
        base = off * bpc;
        vb = valueOffset + j * bpc;
        for (m = 0; m < bpc; m++) cells[base + m] = raw[vb + m];
      }
    } else if (tag === TAG_DELTA_MASK) {
      raw = this._inflate(payload, this._maskMax);
      actual = this.actualLength;
      maskLen = this._maskLength;
      if (actual < maskLen) fail("DELTA_MASK truncado");
      if ((n & 7) !== 0) {
        validBits = (1 << (n & 7)) - 1;
        if (raw[maskLen - 1] & (~validBits & 255)) fail("DELTA_MASK con bits fuera de grilla");
      }
      changed = 0;
      for (j = 0; j < maskLen; j++) changed += getPopCount(raw[j]);
      if (actual !== maskLen + changed * bpc) fail("DELTA_MASK con longitud invalida");
      this._validateChangedValues(raw, maskLen, changed);
      if (!this._dFull) {
        if (this._dCellCount === 0) {
          this.dirtyCellBits.set(raw.subarray(0, maskLen));
          this._dCellCount = changed;
        } else {
          for (j = 0; j < maskLen; j++) {
            byte = raw[j];
            newBits = byte & (~this.dirtyCellBits[j] & 255);
            if (newBits) {
              this.dirtyCellBits[j] |= byte;
              this._dCellCount += getPopCount(newBits);
            }
          }
        }
      }
      vp = maskLen;
      for (j = 0; j < n; j++) {
        byte = raw[j >>> 3];
        if ((byte >>> (j & 7)) & 1) {
          if (lo < 0) lo = j;
          hi = j;
          base = j * bpc;
          for (m = 0; m < bpc; m++) cells[base + m] = raw[vp++];
        }
      }
    } else {
      fail("tag desconocido " + tag);
    }

    if (palCount) {
      this.palette = nextPalette;
      this.paletteEntries = nextPaletteEntries;
    }

    if (full) {
      this._dFull = true;
      this._dCellCount = this.n;
    }
    else if (lo >= 0) {
      var row0 = Math.floor(lo / this.header.cols), row1 = Math.floor(hi / this.header.cols);
      if (row0 < this._dY0) this._dY0 = row0;
      if (row1 > this._dY1) this._dY1 = row1;
    }
  };

  /* Deja reader.cells en target decodificando la cadena minima. */
  Reader.prototype.seek = function (target) {
    var start, key, i;
    target = Number(target);
    if (target !== target) fail("frame target invalido");
    target = Math.floor(target);
    if (target < 0) target = 0;
    if (target >= this.header.nFrames) target = this.header.nFrames - 1;
    this._dFull = false;
    this._dY0 = this.header.rows;
    this._dY1 = -1;
    this._dCellCount = 0;
    clearBitset(this.dirtyCellBits);
    if (this.decodedIndex >= 0 && this.decodedIndex <= target) {
      start = this.decodedIndex + 1;
    } else {
      key = target;
      while (key > 0 && !this._isKey(key)) key--;
      if (!this._isKey(key)) fail("cadena sin keyframe");
      start = key;
      this.palette = this._initialPalette;
      this.paletteEntries = this._initialPaletteEntries;
    }
    for (i = start; i <= target; i++) this._decodeOne(i);
    this.decodedIndex = target;
    this.dirtyFull = this._dFull;
    this.dirtyY0 = this._dY0;
    this.dirtyY1 = this._dY1;
    this.dirtyCellCount = this._dCellCount;
    return this;
  };

  /* Escribe filas inclusivas en offsets absolutos del RGBA de frame completo. */
  Reader.prototype.fillRGBARows = function (out, y0, y1) {
    var mode = this.header.mode, cols = this.header.cols, cells = this.cells, pal = this.palette;
    var start, end, i, c, pi, g, denom;
    if (!out || typeof out.length !== "number" || out.length < this.n * 4) fail("buffer RGBA insuficiente");
    y0 = Number(y0); y1 = Number(y1);
    if (y0 !== Math.floor(y0) || y1 !== Math.floor(y1) || y0 < 0 || y1 < y0 || y1 >= this.header.rows) {
      fail("rango de filas RGBA invalido");
    }
    start = y0 * cols;
    end = (y1 + 1) * cols;
    if ((mode === MODE_PIXEL || mode === MODE_PAL) && !pal) fail("RGBA sin paleta");
    if (mode === MODE_PIXEL) {
      for (i = start; i < end; i++) {
        pi = cells[i] * 3; c = i * 4;
        out[c] = pal[pi]; out[c + 1] = pal[pi + 1]; out[c + 2] = pal[pi + 2]; out[c + 3] = 255;
      }
    } else if (mode === MODE_PAL) {
      for (i = start; i < end; i++) {
        pi = cells[i * 2 + 1] * 3; c = i * 4;
        out[c] = pal[pi]; out[c + 1] = pal[pi + 1]; out[c + 2] = pal[pi + 2]; out[c + 3] = 255;
      }
    } else if (mode === MODE_RGB) {
      for (i = start; i < end; i++) {
        c = i * 4;
        out[c] = cells[c + 1]; out[c + 1] = cells[c + 2]; out[c + 2] = cells[c + 3]; out[c + 3] = 255;
      }
    } else {
      denom = Math.max(1, this.header.rampLen - 1);
      for (i = start; i < end; i++) {
        g = Math.round(cells[i] / denom * 255); c = i * 4;
        out[c] = g; out[c + 1] = g; out[c + 2] = g; out[c + 3] = 255;
      }
    }
    return out;
  };

  Reader.prototype.fillRGBA = function (out) {
    return this.fillRGBARows(out, 0, this.header.rows - 1);
  };

  /*
   * Actualiza un RGBA persistente unicamente en las celdas unidas por el seek.
   * En keyframes conserva la semantica segura y cae al llenado completo.
   */
  Reader.prototype.fillRGBAChanged = function (out) {
    var mode = this.header.mode, cells = this.cells, pal = this.palette, bits = this.dirtyCellBits;
    var byteIndex, byte, bit, mask, i, c, pi, g, denom, bitIndex;
    if (this.dirtyFull) return this.fillRGBA(out);
    if (!out || typeof out.length !== "number" || out.length < this.n * 4) fail("buffer RGBA insuficiente");
    if (!this.dirtyCellCount) return out;
    if ((mode === MODE_PIXEL || mode === MODE_PAL) && !pal) fail("RGBA sin paleta");
    if (!lowBitIndex) {
      lowBitIndex = new Uint8Array(256);
      for (bit = 0; bit < 8; bit++) lowBitIndex[1 << bit] = bit;
    }
    bitIndex = lowBitIndex;

    if (mode === MODE_PIXEL) {
      for (byteIndex = 0; byteIndex < bits.length; byteIndex++) {
        byte = bits[byteIndex];
        while (byte) {
          mask = byte & -byte; bit = bitIndex[mask];
          i = (byteIndex << 3) + bit; pi = cells[i] * 3; c = i * 4;
          out[c] = pal[pi]; out[c + 1] = pal[pi + 1]; out[c + 2] = pal[pi + 2]; out[c + 3] = 255;
          byte ^= mask;
        }
      }
    } else if (mode === MODE_PAL) {
      for (byteIndex = 0; byteIndex < bits.length; byteIndex++) {
        byte = bits[byteIndex];
        while (byte) {
          mask = byte & -byte; bit = bitIndex[mask];
          i = (byteIndex << 3) + bit; pi = cells[i * 2 + 1] * 3; c = i * 4;
          out[c] = pal[pi]; out[c + 1] = pal[pi + 1]; out[c + 2] = pal[pi + 2]; out[c + 3] = 255;
          byte ^= mask;
        }
      }
    } else if (mode === MODE_RGB) {
      for (byteIndex = 0; byteIndex < bits.length; byteIndex++) {
        byte = bits[byteIndex];
        while (byte) {
          mask = byte & -byte; bit = bitIndex[mask];
          i = (byteIndex << 3) + bit; c = i * 4;
          out[c] = cells[c + 1]; out[c + 1] = cells[c + 2]; out[c + 2] = cells[c + 3]; out[c + 3] = 255;
          byte ^= mask;
        }
      }
    } else {
      denom = Math.max(1, this.header.rampLen - 1);
      for (byteIndex = 0; byteIndex < bits.length; byteIndex++) {
        byte = bits[byteIndex];
        while (byte) {
          mask = byte & -byte; bit = bitIndex[mask];
          i = (byteIndex << 3) + bit; g = Math.round(cells[i] / denom * 255); c = i * 4;
          out[c] = g; out[c + 1] = g; out[c + 2] = g; out[c + 3] = 255;
          byte ^= mask;
        }
      }
    }
    return out;
  };

  root.ASCL = {
    parse: function (buffer, byteOffset, byteLength) { return new Reader(buffer, byteOffset, byteLength); },
    MODE_BW: MODE_BW,
    MODE_PAL: MODE_PAL,
    MODE_RGB: MODE_RGB,
    MODE_PIXEL: MODE_PIXEL
  };
  if (typeof module !== "undefined" && module.exports) module.exports = root.ASCL;
})(typeof window !== "undefined" ? window : this);
