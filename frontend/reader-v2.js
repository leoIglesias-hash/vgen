/*
 * reader-v2.js - Reader ASCL v2 PIXEL regional/predictivo, ES5.
 *
 * Convive con reader.js y reader-factory.js despacha por version. Conserva el
 * header ASCL de 32 bytes y los tags 0..3 de v1. Los tags regionales son:
 *   4 KEY_RAW, 5 KEY_ZLIB, 6 DELTA_RAW, 7 DELTA_ZLIB.
 * Los predictores reversibles zlib son 8 KEY y 9 DELTA. Su payload es
 * predictor_id u8 + residual zlib de exactamente cols*rows bytes.
 *
 * Stream regional (cursor de tile implicito, row-major):
 *   0 SKIP_RUN + uvarint; 1 SOLID + u8; 2 SPARSE; 3 MASK;
 *   4 PACK1; 5 PACK2; 6 PAL4; 7 PAL8.
 * Todo entero variable es LEB128 uint32 canonico y todo packing es LSB-first.
 * Cada stream cubre exactamente la grilla. La validacion completa ocurre antes
 * de la primera escritura sobre la unica matriz logica persistente `cells`.
 */
(function (root) {
  "use strict";

  var inflateModule = null;
  if (typeof require === "function") inflateModule = require("./inflate.js");
  var inflateZlib = (typeof root.ASCL_inflateZlib === "function")
    ? root.ASCL_inflateZlib : (inflateModule && inflateModule.ASCL_inflateZlib);
  var inflateZlibInto = (typeof root.ASCL_inflateZlibInto === "function")
    ? root.ASCL_inflateZlibInto : (inflateModule && inflateModule.ASCL_inflateZlibInto);

  var HEADER_SIZE = 32;
  var MODE_PIXEL = 3;
  var FLAG_PAL_PER_SCENE = 2;
  var FLAG_PAL_GLOBAL = 4;
  var FLAG_OFFSET_TABLE = 8;
  var TAG_RAW = 0;
  var TAG_ZLIB = 1;
  var TAG_DELTA = 2;
  var TAG_DELTA_MASK = 3;
  var TAG_REGIONAL_KEY_RAW = 4;
  var TAG_REGIONAL_KEY_ZLIB = 5;
  var TAG_REGIONAL_DELTA_RAW = 6;
  var TAG_REGIONAL_DELTA_ZLIB = 7;
  var TAG_PREDICT_KEY_ZLIB = 8;
  var TAG_PREDICT_DELTA_ZLIB = 9;
  var PRED_LEFT = 0;
  var PRED_TOP = 1;
  var PRED_GRADIENT = 2;
  var PRED_PREVIOUS_SUB = 3;
  var PRED_PREVIOUS_XOR = 4;
  var OP_SKIP_RUN = 0;
  var OP_SOLID = 1;
  var OP_SPARSE = 2;
  var OP_MASK = 3;
  var OP_PACK1 = 4;
  var OP_PACK2 = 5;
  var OP_PAL4 = 6;
  var OP_PAL8 = 7;
  var MAX_STATE_BYTES = 64 * 1024 * 1024;
  var crcTable = null;
  var popCount = null;
  var lowBitIndex = null;

  function fail(message) { throw new Error("ASCLv2: " + message); }

  function makeCrcTable() {
    var table = new Uint32Array(256), i, c, k;
    for (i = 0; i < 256; i++) {
      c = i;
      for (k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[i] = c >>> 0;
    }
    return table;
  }

  function crcRange(bytes, crc, start, end) {
    var i;
    if (!crcTable) crcTable = makeCrcTable();
    for (i = start; i < end; i++) crc = crcTable[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
    return crc;
  }

  /* CRC v2: metadata 0..27 y cuerpo 32..EOF; excluye el propio campo CRC. */
  function crc32v2(bytes) {
    var crc = 0xffffffff;
    crc = crcRange(bytes, crc, 0, 28);
    crc = crcRange(bytes, crc, 32, bytes.length);
    return (crc ^ 0xffffffff) >>> 0;
  }

  function getPopCount(value) {
    var i;
    if (!popCount) {
      popCount = new Uint8Array(256);
      for (i = 1; i < 256; i++) popCount[i] = popCount[i >>> 1] + (i & 1);
    }
    return popCount[value];
  }

  function setBit(bits, index) { bits[index >>> 3] |= (1 << (index & 7)); }
  function hasBit(bits, index) { return (bits[index >>> 3] & (1 << (index & 7))) !== 0; }

  function clearBytes(bytes) {
    var i;
    for (i = 0; i < bytes.length; i++) bytes[i] = 0;
  }

  function sameBytes(a, b) {
    var i;
    if (!a || !b || a.length !== b.length) return false;
    for (i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
    return true;
  }

  function isKeyTag(tag) {
    return tag === TAG_RAW || tag === TAG_ZLIB ||
      tag === TAG_REGIONAL_KEY_RAW || tag === TAG_REGIONAL_KEY_ZLIB ||
      tag === TAG_PREDICT_KEY_ZLIB;
  }

  function isDeltaTag(tag) {
    return tag === TAG_DELTA || tag === TAG_DELTA_MASK ||
      tag === TAG_REGIONAL_DELTA_RAW || tag === TAG_REGIONAL_DELTA_ZLIB ||
      tag === TAG_PREDICT_DELTA_ZLIB;
  }

  function parseHeader(dv) {
    if (dv.byteLength < HEADER_SIZE) fail("header truncado");
    if (dv.getUint8(0) !== 0x41 || dv.getUint8(1) !== 0x53 ||
        dv.getUint8(2) !== 0x43 || dv.getUint8(3) !== 0x4c) fail("magic invalido");
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
      tileSize: dv.getUint8(26),
      codecFlags: dv.getUint8(27),
      crc32: dv.getUint32(28, true)
    };
  }

  function ReaderV2(buffer, byteOffset, byteLength) {
    var h, tableEnd, expected, currentPalette = null, currentPaletteCount = 0;
    var i, o, blockLen, blockEnd, p, tag, palCount, palBytes, payloadLength;
    var firstPalette = null, firstPaletteCount = 0, tileCols, tileRows, n;
    if (!buffer || typeof buffer.byteLength !== "number") fail("ArrayBuffer invalido");
    byteOffset = byteOffset === undefined ? 0 : Number(byteOffset);
    byteLength = byteLength === undefined ? buffer.byteLength - byteOffset : Number(byteLength);
    if (byteOffset !== Math.floor(byteOffset) || byteLength !== Math.floor(byteLength) ||
        byteOffset < 0 || byteLength < HEADER_SIZE || byteOffset + byteLength > buffer.byteLength) {
      fail("rango .ascl invalido");
    }

    this.bytes = new Uint8Array(buffer, byteOffset, byteLength);
    this.dv = new DataView(buffer, byteOffset, byteLength);
    this.header = parseHeader(this.dv);
    h = this.header;
    if (h.version !== 2) fail("version no soportada " + h.version);
    if (h.mode !== MODE_PIXEL) fail("v2 regional requiere modo PIXEL");
    if ((h.flags & 0xe0) !== 0) fail("flags reservados activos");
    if ((h.flags & FLAG_OFFSET_TABLE) === 0) fail("falta tabla de offsets");
    if ((h.flags & FLAG_PAL_PER_SCENE) && (h.flags & FLAG_PAL_GLOBAL)) {
      fail("flags de paleta incompatibles");
    }
    if (!h.fps) fail("fps invalido");
    if (!h.cols || !h.rows || !h.nFrames) fail("dimensiones o frames vacios");
    if (h.palSize < 1 || h.palSize > 256) fail("pal_size invalido");
    if (h.rampLen !== 0) fail("PIXEL no admite rampa");
    if (h.cellFmt !== 3) fail("cell_fmt invalido");
    if (h.dataOff !== HEADER_SIZE) fail("data_off invalido");
    if (!h.charAspect) fail("char aspect invalido");
    if (h.tileSize !== 16) fail("el prototipo requiere tile_size 16");
    if (h.codecFlags !== 1) fail("codec_flags no soportados");
    n = h.cols * h.rows;
    if (n > MAX_STATE_BYTES) fail("dimensiones exceden limite operativo");
    tileCols = Math.ceil(h.cols / h.tileSize);
    tileRows = Math.ceil(h.rows / h.tileSize);
    if (tileCols * tileRows > 65535) fail("demasiados tiles para IDs uint16");
    tableEnd = h.dataOff + h.nFrames * 4;
    if (tableEnd > byteLength) fail("tabla de offsets truncada");
    /* En v2 el CRC es obligatorio y también protege la metadata del header. */
    if (crc32v2(this.bytes) !== h.crc32) fail("CRC32 invalido");

    this.n = n;
    this.tileSize = h.tileSize;
    this.tileCols = tileCols;
    this.tileRows = tileRows;
    this.tileCount = tileCols * tileRows;
    this._tableEnd = tableEnd;
    this._maskLength = Math.ceil(n / 8);
    this._legacyDeltaMax = n * 5;
    this._legacyMaskMax = this._maskLength + n;
    /* Igual al bound de referencia Python: acepta todo stream valido, no solo
     * los comandos cortos que suele elegir el encoder canonico. */
    this._regionalMax = n * 7 + this.tileCount * 8;
    if (this._legacyDeltaMax > MAX_STATE_BYTES || this._regionalMax > MAX_STATE_BYTES) {
      fail("scratch teorico excede limite operativo");
    }
    this.keyBits = new Uint8Array(Math.ceil(h.nFrames / 8));

    expected = tableEnd;
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
      if (tag > TAG_PREDICT_DELTA_ZLIB) fail("tag desconocido " + tag);
      palCount = this.dv.getUint16(p, true); p += 2;
      if (palCount > h.palSize || palCount > 256) fail("pal_count fuera de rango");
      if (isDeltaTag(tag) && palCount) fail("delta no puede cambiar paleta");
      palBytes = palCount * 3;
      if (p + palBytes > blockEnd) fail("paleta truncada en frame " + i);
      if (palCount) {
        currentPalette = this.bytes.subarray(p, p + palBytes);
        currentPaletteCount = palCount;
        if (!firstPalette) {
          firstPalette = currentPalette;
          firstPaletteCount = palCount;
        } else if ((h.flags & FLAG_PAL_GLOBAL) && !sameBytes(firstPalette, currentPalette)) {
          fail("paleta global modificada");
        }
      }
      p += palBytes;
      payloadLength = blockEnd - p;
      if (isKeyTag(tag)) setBit(this.keyBits, i);
      else if (i === 0) fail("primer frame no es keyframe");
      if (!currentPaletteCount) fail("frame sin paleta activa");
      if (h.flags & FLAG_PAL_GLOBAL) {
        if (i === 0 && !palCount) fail("paleta global ausente");
        if (i > 0 && palCount) fail("paleta global reemitida");
      } else if (h.flags & FLAG_PAL_PER_SCENE) {
        if (isKeyTag(tag) && !palCount) fail("keyframe sin paleta autonoma");
      } else if (!palCount) {
        fail("paleta per-frame ausente");
      }
      if (tag === TAG_RAW && payloadLength !== n) fail("RAW con longitud incorrecta");
      if (tag !== TAG_RAW && payloadLength === 0) fail("payload vacio");
      if ((tag === TAG_PREDICT_KEY_ZLIB || tag === TAG_PREDICT_DELTA_ZLIB) &&
          payloadLength < 2) fail("payload predictor truncado");
      expected = blockEnd;
    }
    if (expected !== byteLength) fail("bytes extra al final");
    if (!hasBit(this.keyBits, 0) || !firstPalette) fail("frame inicial incompleto");

    this._initialPalette = firstPalette;
    this._initialPaletteEntries = firstPaletteCount;
    this.palette = firstPalette;
    this.paletteEntries = firstPaletteCount;
    this.cells = new Uint8Array(n);
    /* Dirty hibrido: celdas exactas para deltas dispersos y tiles para
     * comandos regionales densos. Los dos conjuntos se mantienen disjuntos. */
    this.dirtyCellBits = new Uint8Array(this._maskLength);
    this.dirtyCellCount = 0;
    this.dirtyTileBits = new Uint8Array(Math.ceil(this.tileCount / 8));
    this.dirtyTiles = new Uint16Array(this.tileCount);
    this.dirtyCount = 0;
    this.dirtyFull = false;
    this.dirtyY0 = h.rows;
    this.dirtyY1 = -1;
    this.decodedIndex = -1;
    this._scratch = null;
    this.actualLength = 0;
    this._dFull = false;
    this._dCellCount = 0;
    this._dCount = 0;
    this._dY0 = h.rows;
    this._dY1 = -1;
    this._varValue = 0;
    this._varNext = 0;
  }

  ReaderV2.prototype._offset = function (index) {
    return this.dv.getUint32(this.header.dataOff + index * 4, true);
  };

  ReaderV2.prototype._isKey = function (index) { return hasBit(this.keyBits, index); };

  ReaderV2.prototype._readUvar = function (raw, p, end) {
    var value = 0, shift = 0, count = 0, byte;
    while (count < 5) {
      if (p >= end) fail("uvarint truncado");
      byte = raw[p++];
      count++;
      if (count === 5 && (byte & 0xf0)) fail("uvarint excede uint32");
      value += (byte & 0x7f) * Math.pow(2, shift);
      if ((byte & 0x80) === 0) {
        if (count > 1 && (byte & 0x7f) === 0) fail("uvarint no canonico");
        this._varValue = value;
        this._varNext = p;
        return;
      }
      shift += 7;
    }
    fail("uvarint demasiado largo");
  };

  ReaderV2.prototype._tileGeometry = function (tile) {
    var tx = tile % this.tileCols, ty = Math.floor(tile / this.tileCols);
    var x = tx * this.tileSize, y = ty * this.tileSize;
    this._tileX = x;
    this._tileY = y;
    this._tileW = Math.min(this.tileSize, this.header.cols - x);
    this._tileH = Math.min(this.tileSize, this.header.rows - y);
    this._tilePixels = this._tileW * this._tileH;
  };

  ReaderV2.prototype._markDirty = function (tile) {
    var byteIndex, mask, y1, y, x, base, cell, cellByte, cellMask;
    if (this._dFull) return;
    byteIndex = tile >>> 3;
    mask = 1 << (tile & 7);
    if ((this.dirtyTileBits[byteIndex] & mask) === 0) {
      this.dirtyTileBits[byteIndex] |= mask;
      this._dCount++;
      /* Un tile denso reemplaza cualquier bit exacto previo que solape. */
      this._tileGeometry(tile);
      for (y = 0; y < this._tileH; y++) {
        base = (this._tileY + y) * this.header.cols + this._tileX;
        for (x = 0; x < this._tileW; x++) {
          cell = base + x;
          cellByte = cell >>> 3;
          cellMask = 1 << (cell & 7);
          if (this.dirtyCellBits[cellByte] & cellMask) {
            this.dirtyCellBits[cellByte] &= ~cellMask;
            this._dCellCount--;
          }
        }
      }
    } else {
      this._tileGeometry(tile);
    }
    if (this._tileY < this._dY0) this._dY0 = this._tileY;
    y1 = this._tileY + this._tileH - 1;
    if (y1 > this._dY1) this._dY1 = y1;
  };

  ReaderV2.prototype._markDirtyCell = function (cell) {
    var x, y, tile, tileByte, tileMask, cellByte, cellMask;
    if (this._dFull) return;
    x = cell % this.header.cols;
    y = Math.floor(cell / this.header.cols);
    tile = Math.floor(y / this.tileSize) * this.tileCols + Math.floor(x / this.tileSize);
    tileByte = tile >>> 3;
    tileMask = 1 << (tile & 7);
    if (this.dirtyTileBits[tileByte] & tileMask) return;
    cellByte = cell >>> 3;
    cellMask = 1 << (cell & 7);
    if ((this.dirtyCellBits[cellByte] & cellMask) === 0) {
      this.dirtyCellBits[cellByte] |= cellMask;
      this._dCellCount++;
    }
    if (y < this._dY0) this._dY0 = y;
    if (y > this._dY1) this._dY1 = y;
  };

  ReaderV2.prototype._markFull = function () {
    this._dFull = true;
    clearBytes(this.dirtyCellBits);
    this._dCellCount = 0;
    this._dCount = this.tileCount;
    this._dY0 = 0;
    this._dY1 = this.header.rows - 1;
  };

  ReaderV2.prototype._inflate = function (payload, maxLength) {
    var raw, capacity, next;
    if (!inflateZlib) fail("inflate zlib no disponible");
    if (!this._scratch) {
      capacity = Math.min(maxLength, Math.max(64, this.n));
      this._scratch = new Uint8Array(capacity);
    }
    if (inflateZlibInto) {
      while (1) {
        try {
          this.actualLength = inflateZlibInto(payload, this._scratch, maxLength);
          return this._scratch;
        } catch (error) {
          if (!error || error.code !== "ASCL_OUTPUT_BUFFER") throw error;
          next = Math.min(maxLength, Math.max(error.required || 0, this._scratch.length * 2));
          if (next <= this._scratch.length) throw error;
          this._scratch = new Uint8Array(next);
        }
      }
    }
    raw = inflateZlib(payload, maxLength);
    if (raw.length > maxLength) fail("inflate supera limite");
    if (raw.length > this._scratch.length) this._scratch = new Uint8Array(raw.length);
    this._scratch.set(raw);
    this.actualLength = raw.length;
    return this._scratch;
  };

  ReaderV2.prototype._validateIndex = function (value, paletteEntries) {
    if (value >= paletteEntries) fail("indice de paleta fuera de rango");
  };

  ReaderV2.prototype._writeTileValue = function (tile, value) {
    var y, x, base;
    this._tileGeometry(tile);
    for (y = 0; y < this._tileH; y++) {
      base = (this._tileY + y) * this.header.cols + this._tileX;
      for (x = 0; x < this._tileW; x++) this.cells[base + x] = value;
    }
  };

  ReaderV2.prototype._writeTilePacked = function (tile, raw, packedStart, bits, mapStart, mapCount) {
    var q, code, byte, bitShift, y, x, globalIndex;
    this._tileGeometry(tile);
    for (q = 0; q < this._tilePixels; q++) {
      bitShift = (q * bits) & 7;
      byte = raw[packedStart + Math.floor(q * bits / 8)];
      code = (byte >>> bitShift) & ((1 << bits) - 1);
      y = Math.floor(q / this._tileW);
      x = q - y * this._tileW;
      globalIndex = (this._tileY + y) * this.header.cols + this._tileX + x;
      this.cells[globalIndex] = raw[mapStart + code];
    }
  };

  /*
   * Recorre el mismo stream dos veces. apply=false no modifica ningun estado de
   * video; apply=true se ejecuta solo despues de una validacion completa exitosa.
   */
  ReaderV2.prototype._walkRegional = function (raw, length, keyframe, paletteEntries, apply) {
    var p = 0, cursor = 0, opcode, run, tile, npix, i, k, offset, previousOffset;
    var value, maskLength, changed, byte, validBits, valuesStart, q, globalIndex;
    var mapStart, mapCount, packedStart, packedLength, bits, code, shift, lastMap;
    var y, x, byteIndex;
    if (!length) fail("stream regional vacio");
    while (p < length) {
      if (cursor >= this.tileCount) fail("bytes posteriores a cobertura regional");
      opcode = raw[p++];
      tile = cursor;
      this._tileGeometry(tile);
      npix = this._tilePixels;

      if (opcode === OP_SKIP_RUN) {
        if (keyframe) fail("SKIP no permitido en keyframe");
        this._readUvar(raw, p, length);
        run = this._varValue; p = this._varNext;
        if (!run || run > this.tileCount - cursor) fail("SKIP_RUN fuera de grilla");
        cursor += run;
        continue;
      }

      if (opcode === OP_SOLID) {
        if (p >= length) fail("SOLID truncado");
        value = raw[p++];
        this._validateIndex(value, paletteEntries);
        if (apply) this._writeTileValue(tile, value);
      } else if (opcode === OP_SPARSE) {
        if (keyframe) fail("SPARSE no permitido en keyframe");
        this._readUvar(raw, p, length);
        k = this._varValue; p = this._varNext;
        if (!k || k > npix) fail("SPARSE count invalido");
        previousOffset = -1;
        for (i = 0; i < k; i++) {
          this._readUvar(raw, p, length);
          offset = this._varValue; p = this._varNext;
          if (offset >= npix || offset <= previousOffset) fail("offset SPARSE no canonico");
          if (p >= length) fail("SPARSE truncado");
          value = raw[p++];
          this._validateIndex(value, paletteEntries);
          y = Math.floor(offset / this._tileW);
          x = offset - y * this._tileW;
          globalIndex = (this._tileY + y) * this.header.cols + this._tileX + x;
          if (value === this.cells[globalIndex]) fail("SPARSE contiene escritura identica");
          if (apply) {
            this._markDirtyCell(globalIndex);
            this.cells[globalIndex] = value;
          }
          previousOffset = offset;
        }
      } else if (opcode === OP_MASK) {
        if (keyframe) fail("MASK no permitido en keyframe");
        maskLength = Math.ceil(npix / 8);
        if (p + maskLength > length) fail("MASK truncado");
        if ((npix & 7) !== 0) {
          validBits = (1 << (npix & 7)) - 1;
          if (raw[p + maskLength - 1] & (~validBits & 255)) fail("MASK con padding activo");
        }
        changed = 0;
        for (i = 0; i < maskLength; i++) changed += getPopCount(raw[p + i]);
        if (!changed) fail("MASK vacio");
        valuesStart = p + maskLength;
        if (valuesStart + changed > length) fail("valores MASK truncados");
        q = 0;
        for (i = 0; i < npix; i++) {
          if ((raw[p + (i >>> 3)] >>> (i & 7)) & 1) {
            value = raw[valuesStart + q++];
            this._validateIndex(value, paletteEntries);
            y = Math.floor(i / this._tileW);
            x = i - y * this._tileW;
            globalIndex = (this._tileY + y) * this.header.cols + this._tileX + x;
            if (value === this.cells[globalIndex]) fail("MASK contiene escritura identica");
            if (apply) {
              this._markDirtyCell(globalIndex);
              this.cells[globalIndex] = value;
            }
          }
        }
        p = valuesStart + changed;
      } else if (opcode === OP_PACK1 || opcode === OP_PACK2 || opcode === OP_PAL4) {
        bits = opcode === OP_PACK1 ? 1 : (opcode === OP_PACK2 ? 2 : 4);
        if (opcode === OP_PACK1) {
          mapCount = 2;
        } else {
          if (p >= length) fail("mapa packed truncado");
          mapCount = raw[p++];
          if ((opcode === OP_PACK2 && (mapCount < 3 || mapCount > 4)) ||
              (opcode === OP_PAL4 && (mapCount < 5 || mapCount > 16))) {
            fail("cantidad de mapa packed invalida");
          }
        }
        mapStart = p;
        if (p + mapCount > length) fail("mapa packed truncado");
        lastMap = -1;
        for (i = 0; i < mapCount; i++) {
          value = raw[p++];
          this._validateIndex(value, paletteEntries);
          if (value <= lastMap) fail("mapa packed no canonico");
          lastMap = value;
        }
        packedStart = p;
        packedLength = Math.ceil(npix * bits / 8);
        if (p + packedLength > length) fail("indices packed truncados");
        for (i = 0; i < npix; i++) {
          byteIndex = Math.floor(i * bits / 8);
          shift = (i * bits) & 7;
          code = (raw[packedStart + byteIndex] >>> shift) & ((1 << bits) - 1);
          if (code >= mapCount) fail("indice packed fuera de mapa");
        }
        if ((npix * bits & 7) !== 0) {
          validBits = (1 << (npix * bits & 7)) - 1;
          if (raw[packedStart + packedLength - 1] & (~validBits & 255)) {
            fail("packed con padding activo");
          }
        }
        if (apply) this._writeTilePacked(tile, raw, packedStart, bits, mapStart, mapCount);
        p += packedLength;
      } else if (opcode === OP_PAL8) {
        if (p + npix > length) fail("PAL8 truncado");
        for (i = 0; i < npix; i++) this._validateIndex(raw[p + i], paletteEntries);
        if (apply) {
          q = 0;
          for (y = 0; y < this._tileH; y++) {
            globalIndex = (this._tileY + y) * this.header.cols + this._tileX;
            for (x = 0; x < this._tileW; x++) this.cells[globalIndex + x] = raw[p + q++];
          }
        }
        p += npix;
      } else {
        fail("opcode regional desconocido " + opcode);
      }

      if (apply && !keyframe && opcode !== OP_SPARSE && opcode !== OP_MASK) {
        this._markDirty(tile);
      }
      cursor++;
    }
    if (cursor !== this.tileCount) fail("stream regional no cubre la grilla");
    if (apply && keyframe) this._markFull();
  };

  ReaderV2.prototype._decodeLegacyDelta = function (tag, raw, actual, paletteEntries) {
    var k, rdv, valueStart, i, off, value, maskLen, changed, validBits, p;
    if (tag === TAG_DELTA) {
      if (actual % 5 !== 0) fail("DELTA con longitud invalida");
      k = actual / 5;
      if (k > this.n) fail("DELTA excede cantidad de celdas");
      rdv = new DataView(raw.buffer, raw.byteOffset, actual);
      valueStart = k * 4;
      for (i = 0; i < k; i++) {
        off = rdv.getUint32(i * 4, true);
        if (off >= this.n) fail("offset DELTA fuera de rango");
        this._validateIndex(raw[valueStart + i], paletteEntries);
      }
      for (i = 0; i < k; i++) {
        off = rdv.getUint32(i * 4, true);
        value = raw[valueStart + i];
        if (this.cells[off] !== value) this._markDirtyCell(off);
        this.cells[off] = value;
      }
      return;
    }
    maskLen = this._maskLength;
    if (actual < maskLen) fail("DELTA_MASK truncado");
    if ((this.n & 7) !== 0) {
      validBits = (1 << (this.n & 7)) - 1;
      if (raw[maskLen - 1] & (~validBits & 255)) fail("DELTA_MASK con bits fuera de grilla");
    }
    changed = 0;
    for (i = 0; i < maskLen; i++) changed += getPopCount(raw[i]);
    if (actual !== maskLen + changed) fail("DELTA_MASK con longitud invalida");
    for (i = 0; i < changed; i++) this._validateIndex(raw[maskLen + i], paletteEntries);
    p = maskLen;
    for (i = 0; i < this.n; i++) {
      if ((raw[i >>> 3] >>> (i & 7)) & 1) {
        value = raw[p++];
        if (this.cells[i] !== value) this._markDirtyCell(i);
        this.cells[i] = value;
      }
    }
  };

  /*
   * Los predictores son transformadas byte-a-byte reversibles. El residual se
   * infla en el scratch compartido. Para keyframes se reconstruye y valida ahi
   * antes del unico cells.set; para deltas se valida todo en una primera pasada
   * y recien entonces se aplican los residuales no nulos. Asi un frame corrupto
   * nunca deja una matriz parcialmente modificada ni exige un segundo frame.
   */
  ReaderV2.prototype._decodePredictor = function (tag, payload, paletteEntries) {
    var keyframe = tag === TAG_PREDICT_KEY_ZLIB;
    var predictor, raw, actual, i, x, y, predicted, left, top, topLeft, value;
    var cols = this.header.cols;
    if (payload.length < 2) fail("payload predictor truncado");
    predictor = payload[0];
    if (keyframe) {
      if (predictor !== PRED_LEFT && predictor !== PRED_TOP &&
          predictor !== PRED_GRADIENT) fail("predictor incompatible con key/delta");
    } else if (predictor !== PRED_PREVIOUS_SUB && predictor !== PRED_PREVIOUS_XOR) {
      fail("predictor incompatible con key/delta");
    }

    raw = this._inflate(payload.subarray(1), this.n);
    actual = this.actualLength;
    if (actual !== this.n) fail("PREDICT con longitud descomprimida incorrecta");

    if (keyframe) {
      /* raw pasa de residual a frame reconstruido, fila por fila. Todos los
       * vecinos que consulta ya fueron reconstruidos en el mismo scratch. */
      for (i = 0; i < this.n; i++) {
        x = i % cols;
        y = Math.floor(i / cols);
        if (predictor === PRED_LEFT) {
          predicted = x ? raw[i - 1] : 0;
        } else if (predictor === PRED_TOP) {
          predicted = y ? raw[i - cols] : 0;
        } else {
          left = x ? raw[i - 1] : 0;
          top = y ? raw[i - cols] : 0;
          topLeft = x && y ? raw[i - cols - 1] : 0;
          predicted = (left + top - topLeft) & 255;
        }
        value = (predicted + raw[i]) & 255;
        this._validateIndex(value, paletteEntries);
        raw[i] = value;
      }
      this.cells.set(raw.subarray(0, this.n));
      this._markFull();
      return;
    }

    /* Primera pasada: ni cells ni dirty cambian hasta que cada indice final
     * quedo validado contra la paleta activa. */
    for (i = 0; i < this.n; i++) {
      value = predictor === PRED_PREVIOUS_SUB ?
        ((this.cells[i] + raw[i]) & 255) : (this.cells[i] ^ raw[i]);
      this._validateIndex(value, paletteEntries);
    }
    for (i = 0; i < this.n; i++) {
      if (raw[i] !== 0) {
        this.cells[i] = predictor === PRED_PREVIOUS_SUB ?
          ((this.cells[i] + raw[i]) & 255) : (this.cells[i] ^ raw[i]);
        this._markDirtyCell(i);
      }
    }
  };

  ReaderV2.prototype._decodeOne = function (index) {
    var o = this._offset(index), blockLen, blockEnd, p, tag, palCount, palBytes;
    var nextPalette = this.palette, nextPaletteEntries = this.paletteEntries;
    var payload, raw, actual, i;
    if (o > this.bytes.length - 7) fail("frame mutado o truncado");
    blockLen = this.dv.getUint32(o, true);
    blockEnd = o + 4 + blockLen;
    if (blockLen < 3 || blockEnd > this.bytes.length) fail("frame mutado o truncado");
    p = o + 4;
    tag = this.bytes[p++];
    palCount = this.dv.getUint16(p, true);
    palBytes = palCount * 3;
    p += 2;
    if (tag > TAG_PREDICT_DELTA_ZLIB || palCount > this.header.palSize ||
        palCount > 256 || p + palBytes > blockEnd) fail("frame corrupto");
    if (isDeltaTag(tag) && palCount) fail("delta no puede cambiar paleta");
    if (this.header.flags & FLAG_PAL_GLOBAL) {
      if (index === 0 && !palCount) fail("paleta global ausente");
      if (index > 0 && palCount) fail("paleta global reemitida");
    } else if (this.header.flags & FLAG_PAL_PER_SCENE) {
      if (isKeyTag(tag) && !palCount) fail("keyframe sin paleta autonoma");
    } else if (!palCount) {
      fail("paleta per-frame ausente");
    }
    if (palCount) {
      nextPalette = this.bytes.subarray(p, p + palBytes);
      nextPaletteEntries = palCount;
      if ((this.header.flags & FLAG_PAL_GLOBAL) &&
          !sameBytes(this._initialPalette, nextPalette)) fail("paleta global modificada");
      p += palBytes;
    }
    payload = this.bytes.subarray(p, blockEnd);
    if (tag !== TAG_RAW && !payload.length) fail("payload vacio");

    if (tag === TAG_RAW || tag === TAG_ZLIB) {
      if (tag === TAG_RAW) {
        raw = payload; actual = raw.length;
      } else {
        raw = this._inflate(payload, this.n); actual = this.actualLength;
      }
      if (actual !== this.n) fail("keyframe completo con longitud invalida");
      for (i = 0; i < this.n; i++) this._validateIndex(raw[i], nextPaletteEntries);
      this.cells.set(raw.subarray(0, actual));
      this._markFull();
    } else if (tag === TAG_DELTA || tag === TAG_DELTA_MASK) {
      raw = this._inflate(payload, tag === TAG_DELTA ? this._legacyDeltaMax : this._legacyMaskMax);
      actual = this.actualLength;
      this._decodeLegacyDelta(tag, raw, actual, nextPaletteEntries);
    } else if (tag === TAG_PREDICT_KEY_ZLIB || tag === TAG_PREDICT_DELTA_ZLIB) {
      this._decodePredictor(tag, payload, nextPaletteEntries);
    } else {
      if (tag === TAG_REGIONAL_KEY_RAW || tag === TAG_REGIONAL_DELTA_RAW) {
        raw = payload; actual = raw.length;
      } else {
        raw = this._inflate(payload, this._regionalMax); actual = this.actualLength;
      }
      this._walkRegional(raw, actual,
        tag === TAG_REGIONAL_KEY_RAW || tag === TAG_REGIONAL_KEY_ZLIB,
        nextPaletteEntries, false);
      this._walkRegional(raw, actual,
        tag === TAG_REGIONAL_KEY_RAW || tag === TAG_REGIONAL_KEY_ZLIB,
        nextPaletteEntries, true);
    }
    if (palCount) {
      this.palette = nextPalette;
      this.paletteEntries = nextPaletteEntries;
    }
  };

  ReaderV2.prototype.seek = function (target) {
    var start, key, i, byteIndex, byte, bit;
    target = Number(target);
    if (target !== target) fail("frame target invalido");
    target = Math.floor(target);
    if (target < 0) target = 0;
    if (target >= this.header.nFrames) target = this.header.nFrames - 1;
    clearBytes(this.dirtyCellBits);
    clearBytes(this.dirtyTileBits);
    this._dFull = false;
    this._dCellCount = 0;
    this._dCount = 0;
    this._dY0 = this.header.rows;
    this._dY1 = -1;

    if (this.decodedIndex >= 0 && this.decodedIndex <= target) {
      /* En playback normal solo inspecciona el salto solicitado, no retrocede
       * hasta el inicio del GOP en cada frame. Si el salto cruza un keyframe,
       * empieza alli y evita decodificar deltas que quedaran sobrescritos. */
      key = target;
      while (key > this.decodedIndex && !this._isKey(key)) key--;
      if (key > this.decodedIndex && this._isKey(key)) {
        start = key;
        this.palette = this._initialPalette;
        this.paletteEntries = this._initialPaletteEntries;
      } else {
        start = this.decodedIndex + 1;
      }
    } else {
      key = target;
      while (key > 0 && !this._isKey(key)) key--;
      if (!this._isKey(key)) fail("cadena sin keyframe");
      start = key;
      this.palette = this._initialPalette;
      this.paletteEntries = this._initialPaletteEntries;
    }
    try {
      for (i = start; i <= target; i++) this._decodeOne(i);
    } catch (error) {
      this.decodedIndex = -1;
      this.palette = this._initialPalette;
      this.paletteEntries = this._initialPaletteEntries;
      clearBytes(this.dirtyCellBits);
      clearBytes(this.dirtyTileBits);
      this.dirtyFull = false;
      this.dirtyCellCount = 0;
      this.dirtyCount = 0;
      this.dirtyY0 = this.header.rows;
      this.dirtyY1 = -1;
      throw error;
    }
    this.decodedIndex = target;
    this.dirtyFull = this._dFull;
    this.dirtyY0 = this._dY0;
    this.dirtyY1 = this._dY1;
    if (this._dFull) {
      this.dirtyCellCount = 0;
      this.dirtyCount = this.tileCount;
    } else {
      this.dirtyCellCount = this._dCellCount;
      i = 0;
      for (byteIndex = 0; byteIndex < this.dirtyTileBits.length; byteIndex++) {
        byte = this.dirtyTileBits[byteIndex];
        for (bit = 0; bit < 8 && byte; bit++) {
          if (byte & (1 << bit)) this.dirtyTiles[i++] = (byteIndex << 3) + bit;
        }
      }
      this.dirtyCount = i;
    }
    return this;
  };

  ReaderV2.prototype.fillRGBARows = function (out, y0, y1) {
    var start, end, i, c, pi;
    if (!out || typeof out.length !== "number" || out.length < this.n * 4) {
      fail("buffer RGBA insuficiente");
    }
    y0 = Number(y0); y1 = Number(y1);
    if (y0 !== Math.floor(y0) || y1 !== Math.floor(y1) ||
        y0 < 0 || y1 < y0 || y1 >= this.header.rows) fail("rango de filas RGBA invalido");
    if (!this.palette) fail("RGBA sin paleta");
    start = y0 * this.header.cols;
    end = (y1 + 1) * this.header.cols;
    for (i = start; i < end; i++) {
      pi = this.cells[i] * 3; c = i * 4;
      out[c] = this.palette[pi]; out[c + 1] = this.palette[pi + 1];
      out[c + 2] = this.palette[pi + 2]; out[c + 3] = 255;
    }
    return out;
  };

  ReaderV2.prototype.fillRGBA = function (out) {
    return this.fillRGBARows(out, 0, this.header.rows - 1);
  };

  ReaderV2.prototype.fillRGBAChanged = function (out) {
    var d, tile, y, x, base, i, c, pi, byteIndex, byte, bit, mask, bitIndex;
    if (this.dirtyFull) return this.fillRGBA(out);
    if (!out || typeof out.length !== "number" || out.length < this.n * 4) {
      fail("buffer RGBA insuficiente");
    }
    if (!this.dirtyCount && !this.dirtyCellCount) return out;
    if (!this.palette) fail("RGBA sin paleta");
    for (d = 0; d < this.dirtyCount; d++) {
      tile = this.dirtyTiles[d];
      this._tileGeometry(tile);
      for (y = 0; y < this._tileH; y++) {
        base = (this._tileY + y) * this.header.cols + this._tileX;
        for (x = 0; x < this._tileW; x++) {
          i = base + x; c = i * 4; pi = this.cells[i] * 3;
          out[c] = this.palette[pi]; out[c + 1] = this.palette[pi + 1];
          out[c + 2] = this.palette[pi + 2]; out[c + 3] = 255;
        }
      }
    }
    if (this.dirtyCellCount) {
      if (!lowBitIndex) {
        lowBitIndex = new Uint8Array(256);
        for (bit = 0; bit < 8; bit++) lowBitIndex[1 << bit] = bit;
      }
      bitIndex = lowBitIndex;
      for (byteIndex = 0; byteIndex < this.dirtyCellBits.length; byteIndex++) {
        byte = this.dirtyCellBits[byteIndex];
        while (byte) {
          mask = byte & -byte;
          bit = bitIndex[mask];
          i = (byteIndex << 3) + bit;
          pi = this.cells[i] * 3;
          c = i * 4;
          out[c] = this.palette[pi]; out[c + 1] = this.palette[pi + 1];
          out[c + 2] = this.palette[pi + 2]; out[c + 3] = 255;
          byte ^= mask;
        }
      }
    }
    return out;
  };

  ReaderV2.prototype.dispose = function () {
    this.bytes = null;
    this.dv = null;
    this.cells = null;
    this.palette = null;
    this._scratch = null;
    this.dirtyCellBits = null;
    this.dirtyTileBits = null;
    this.dirtyTiles = null;
  };

  root.ASCLV2 = {
    parse: function (buffer, byteOffset, byteLength) {
      return new ReaderV2(buffer, byteOffset, byteLength);
    },
    ReaderV2: ReaderV2,
    MODE_PIXEL: MODE_PIXEL,
    TAG_REGIONAL_KEY_RAW: TAG_REGIONAL_KEY_RAW,
    TAG_REGIONAL_KEY_ZLIB: TAG_REGIONAL_KEY_ZLIB,
    TAG_REGIONAL_DELTA_RAW: TAG_REGIONAL_DELTA_RAW,
    TAG_REGIONAL_DELTA_ZLIB: TAG_REGIONAL_DELTA_ZLIB,
    TAG_PREDICT_KEY_ZLIB: TAG_PREDICT_KEY_ZLIB,
    TAG_PREDICT_DELTA_ZLIB: TAG_PREDICT_DELTA_ZLIB,
    PRED_LEFT: PRED_LEFT,
    PRED_TOP: PRED_TOP,
    PRED_GRADIENT: PRED_GRADIENT,
    PRED_PREVIOUS_SUB: PRED_PREVIOUS_SUB,
    PRED_PREVIOUS_XOR: PRED_PREVIOUS_XOR,
    OP_SKIP_RUN: OP_SKIP_RUN,
    OP_SOLID: OP_SOLID,
    OP_SPARSE: OP_SPARSE,
    OP_MASK: OP_MASK,
    OP_PACK1: OP_PACK1,
    OP_PACK2: OP_PACK2,
    OP_PAL4: OP_PAL4,
    OP_PAL8: OP_PAL8,
    crc32v2: crc32v2
  };
  if (typeof module !== "undefined" && module.exports) module.exports = root.ASCLV2;
})(typeof window !== "undefined" ? window : this);
