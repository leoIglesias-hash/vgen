/*
 * reader.js - Parser y decodificador .ascl, ES5 (corre en webviews viejos ES2015+).
 *
 * No asume APIs modernas: usa DataView/TypedArray (universales) y el inflate propio.
 * Decodifica RAW / ZLIB / DELTA manteniendo estado, con seek por keyframes.
 *
 * Uso:
 *   var reader = ASCL.parse(arrayBuffer);     // parsea header + tabla de offsets
 *   reader.seek(frameIndex);                   // deja reader.cells en ese frame
 *   // render: usar reader.header, reader.cells, reader.palette, reader.ramp
 *
 * Layout de reader.cells: cell-major, stride = bpc bytes por celda.
 *   PIXEL/BW : [idx|char]                 (bpc 1)
 *   ASCII_PAL: [char, colorIdx]           (bpc 2)
 *   ASCII_RGB: [char, R, G, B]            (bpc 4)
 */
(function (root) {
  "use strict";

  var inflateZlib = (typeof root.ASCL_inflateZlib === "function")
    ? root.ASCL_inflateZlib
    : (typeof require === "function" ? require("./inflate.js").ASCL_inflateZlib : null);

  var MODE_BW = 0, MODE_PAL = 1, MODE_RGB = 2, MODE_PIXEL = 3;
  var TAG_RAW = 0, TAG_ZLIB = 1, TAG_DELTA = 2, TAG_DELTA_MASK = 3;
  var BPC = { 0: 1, 1: 2, 2: 4, 3: 1 };

  function parseHeader(dv) {
    // "ASCLVID1" (bundle .asclv) comparte los 4 primeros bytes con "ASCL": detectarlo aparte.
    if (dv.byteLength >= 8 && dv.getUint8(4) === 0x56 && dv.getUint8(5) === 0x49 &&
        dv.getUint8(6) === 0x44 && dv.getUint8(7) === 0x31 &&
        dv.getUint8(0) === 0x41 && dv.getUint8(1) === 0x53 &&
        dv.getUint8(2) === 0x43 && dv.getUint8(3) === 0x4C) {
      throw new Error("es un .asclv (bundle), no un .ascl suelto");
    }
    if (dv.getUint8(0) !== 0x41 || dv.getUint8(1) !== 0x53 ||
        dv.getUint8(2) !== 0x43 || dv.getUint8(3) !== 0x4C) {
      throw new Error("no es .ascl (magic invalido)");
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

  function planesToCells(planes, mode, n, cells) {
    var i, b;
    if (mode === MODE_PIXEL || mode === MODE_BW) {
      for (i = 0; i < n; i++) cells[i] = planes[i];
    } else if (mode === MODE_PAL) {
      for (i = 0; i < n; i++) { cells[i * 2] = planes[i]; cells[i * 2 + 1] = planes[n + i]; }
    } else if (mode === MODE_RGB) {
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
    byteOffset = byteOffset || 0;
    byteLength = byteLength === undefined ? buffer.byteLength - byteOffset : byteLength;
    if (byteOffset < 0 || byteLength < 32 || byteOffset + byteLength > buffer.byteLength) {
      throw new Error("rango .ascl invalido");
    }
    // Vista directa dentro del .asclv: evita duplicar el video completo en memoria.
    this.bytes = new Uint8Array(buffer, byteOffset, byteLength);
    this.dv = new DataView(buffer, byteOffset, byteLength);
    this.header = parseHeader(this.dv);
    var h = this.header;
    this.bpc = BPC[h.mode];
    this.n = h.cols * h.rows;
    this.ramp = "";
    for (var r = 0; r < h.rampLen; r++) this.ramp += String.fromCharCode(this.bytes[32 + r]);

    this.offsets = new Array(h.nFrames);
    this.isKey = new Array(h.nFrames);
    var p = h.dataOff;
    for (var i = 0; i < h.nFrames; i++) { this.offsets[i] = this.dv.getUint32(p, true); p += 4; }
    // pre-scan: tag por frame (keyframe = no DELTA) y precarga de la 1a paleta (modo global)
    this.palette = null;
    for (var k = 0; k < h.nFrames; k++) {
      var o = this.offsets[k], q = o + 4;
      var tag = this.bytes[q]; q += 1;
      var palCount = this.dv.getUint16(q, true); q += 2;
      this.isKey[k] = (tag === TAG_RAW || tag === TAG_ZLIB);
      if (palCount > 0 && this.palette === null) {
        this.palette = this.bytes.subarray(q, q + palCount * 3);
      }
    }
    this.cells = new Uint8Array(this.n * this.bpc);
    this.decodedIndex = -1;
  }

  Reader.prototype._decodeOne = function (i) {
    var o = this.offsets[i];
    var blockLen = this.dv.getUint32(o, true);
    var p = o + 4;
    var tag = this.bytes[p]; p += 1;
    var palCount = this.dv.getUint16(p, true); p += 2;
    if (palCount > 0) { this.palette = this.bytes.subarray(p, p + palCount * 3); p += palCount * 3; }
    var payload = this.bytes.subarray(p, o + 4 + blockLen);
    var mode = this.header.mode, n = this.n, bpc = this.bpc, cols = this.header.cols;
    var _lo = -1, _hi = -1, _full = false;
    if (tag === TAG_RAW) {
      planesToCells(payload, mode, n, this.cells); _full = true;
    } else if (tag === TAG_ZLIB) {
      planesToCells(inflateZlib(payload), mode, n, this.cells); _full = true;
    } else if (tag === TAG_DELTA) {
      var raw = inflateZlib(payload);
      var k = (raw.length / (4 + bpc)) | 0;
      var rdv = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
      var voff = k * 4, j, m, off, base, vb, cells = this.cells;
      for (j = 0; j < k; j++) {
        off = rdv.getUint32(j * 4, true);
        if (_lo < 0 || off < _lo) _lo = off;
        if (off > _hi) _hi = off;
        base = off * bpc; vb = voff + j * bpc;
        for (m = 0; m < bpc; m++) cells[base + m] = raw[vb + m];
      }
    } else if (tag === TAG_DELTA_MASK) {
      var rawm = inflateZlib(payload);
      var maskLen = (n + 7) >> 3;
      var cm = this.cells, vp = maskLen, jj, mm, bb, bs;
      for (jj = 0; jj < n; jj++) {
        bb = (rawm[jj >> 3] >> (jj & 7)) & 1;
        if (bb) {
          if (_lo < 0) _lo = jj;
          _hi = jj;
          bs = jj * bpc;
          for (mm = 0; mm < bpc; mm++) cm[bs + mm] = rawm[vp + mm];
          vp += bpc;
        }
      }
    } else {
      throw new Error("tag desconocido " + tag);
    }
    if (_full) { this._dFull = true; }
    else if (_lo >= 0) {
      var _r0 = (_lo / cols) | 0, _r1 = (_hi / cols) | 0;
      if (_r0 < this._dY0) this._dY0 = _r0;
      if (_r1 > this._dY1) this._dY1 = _r1;
    }
  };

  // Deja reader.cells en el frame `target`, decodificando la cadena minima.
  Reader.prototype.seek = function (target) {
    if (target < 0) target = 0;
    if (target >= this.header.nFrames) target = this.header.nFrames - 1;
    this._dFull = false; this._dY0 = this.header.rows; this._dY1 = -1;
    var start;
    if (this.decodedIndex >= 0 && this.decodedIndex <= target) {
      start = this.decodedIndex + 1;          // avanzar
    } else {
      // retroceder o primer decode: ir al keyframe <= target
      var k = target;
      while (k > 0 && !this.isKey[k]) k--;
      start = k;
    }
    for (var i = start; i <= target; i++) this._decodeOne(i);
    this.decodedIndex = target;
    this.dirtyFull = this._dFull;
    this.dirtyY0 = this._dY0; this.dirtyY1 = this._dY1;
    return this;
  };

  // Rellena `out` (Uint8Array n*4) con RGBA del frame actual (para WebGL/ImageData).
  Reader.prototype.fillRGBA = function (out) {
    var mode = this.header.mode, n = this.n, cells = this.cells, pal = this.palette, i, c, pi;
    if (mode === MODE_PIXEL) {
      for (i = 0; i < n; i++) { pi = cells[i] * 3; c = i * 4; out[c] = pal[pi]; out[c+1] = pal[pi+1]; out[c+2] = pal[pi+2]; out[c+3] = 255; }
    } else if (mode === MODE_PAL) {
      for (i = 0; i < n; i++) { pi = cells[i*2+1] * 3; c = i * 4; out[c] = pal[pi]; out[c+1] = pal[pi+1]; out[c+2] = pal[pi+2]; out[c+3] = 255; }
    } else if (mode === MODE_RGB) {
      for (i = 0; i < n; i++) { c = i * 4; out[c] = cells[i*4+1]; out[c+1] = cells[i*4+2]; out[c+2] = cells[i*4+3]; out[c+3] = 255; }
    } else { // BW
      for (i = 0; i < n; i++) { var g = Math.round(cells[i] / Math.max(1, this.header.rampLen - 1) * 255); c = i * 4; out[c]=g; out[c+1]=g; out[c+2]=g; out[c+3]=255; }
    }
    return out;
  };

  root.ASCL = {
    parse: function (buffer, byteOffset, byteLength) {
      return new Reader(buffer, byteOffset, byteLength);
    },
    MODE_BW: MODE_BW, MODE_PAL: MODE_PAL, MODE_RGB: MODE_RGB, MODE_PIXEL: MODE_PIXEL
  };
  if (typeof module !== "undefined" && module.exports) module.exports = root.ASCL;
})(typeof window !== "undefined" ? window : this);
