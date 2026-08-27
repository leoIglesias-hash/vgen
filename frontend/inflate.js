/*
 * inflate.js - DEFLATE/zlib minimo y acotado, ES5, sin dependencias.
 *
 * API legacy (conservada):
 *   ASCL_inflateZlib(u8[, maxLength]) -> Uint8Array
 *   ASCL_inflateRaw(u8[, maxLength])  -> Uint8Array
 *
 * API sin asignacion proporcional (usada por reader.js):
 *   ASCL_inflateZlibInto(u8, out, maxLength) -> actualLength
 *   ASCL_inflateRawInto(u8, out, maxLength)  -> actualLength
 */
(function (root) {
  "use strict";

  var MAX_DYNAMIC_OUTPUT = 0x7fffffff;

  function fail(message) { throw new Error("inflate: " + message); }

  function outputFail(message, code, required) {
    var error = new Error("inflate: " + message);
    error.code = code;
    error.required = required;
    throw error;
  }

  /* W-06: cada arbol lleva ademas una tabla de lookup de LUT_BITS bits.
   * lut[i] = (len << 12) | simbolo para todo codigo de longitud <= LUT_BITS,
   * indexada por los proximos bits del stream (LSB primero, ya invertidos).
   * 0 = entrada no cubierta: codigo mas largo o prefijo invalido; se cae al
   * recorrido canonico bit a bit, que reproduce los errores historicos. */
  var LUT_BITS = 9;
  var LUT_SIZE = 1 << LUT_BITS;

  function makeTree() {
    return { table: new Uint16Array(16), trans: new Uint16Array(288),
             lut: new Uint16Array(LUT_SIZE), maxLen: 0 };
  }

  function buildTree(t, lengths, off, num, allowEmpty) {
    var i, len, sum, left = 1, used = 0, offs = new Uint16Array(16);
    var code, k, sym, rev, c, b, f, step, entry, idx;
    for (i = 0; i < 16; i++) t.table[i] = 0;
    for (i = 0; i < LUT_SIZE; i++) t.lut[i] = 0;
    for (i = 0; i < num; i++) {
      len = lengths[off + i];
      if (len > 15) fail("longitud Huffman invalida");
      t.table[len]++;
      if (len) used++;
    }
    if (!used) {
      if (allowEmpty) { t.table[0] = 0; t.maxLen = 0; return; }
      fail("arbol Huffman vacio");
    }
    t.table[0] = 0;
    t.maxLen = 0;
    for (i = 1; i < 16; i++) {
      left = (left << 1) - t.table[i];
      if (left < 0) fail("arbol Huffman sobre-suscripto");
      if (t.table[i]) t.maxLen = i;
    }
    for (sum = 0, i = 0; i < 16; i++) { offs[i] = sum; sum += t.table[i]; }
    for (i = 0; i < num; i++) {
      len = lengths[off + i];
      if (len) t.trans[offs[len]++] = i;
    }
    /* Codigos canonicos en el mismo orden que trans: por longitud y, dentro
     * de cada longitud, por indice de simbolo. */
    code = 0;
    idx = 0;
    for (len = 1; len <= 15; len++) {
      code <<= 1;
      for (k = 0; k < t.table[len]; k++) {
        sym = t.trans[idx++];
        if (len <= LUT_BITS) {
          rev = 0;
          c = code;
          for (b = 0; b < len; b++) { rev = (rev << 1) | (c & 1); c >>= 1; }
          entry = (len << 12) | sym;
          step = 1 << len;
          for (f = rev; f < LUT_SIZE; f += step) t.lut[f] = entry;
        }
        code++;
      }
    }
  }

  function validSource(source) {
    return source && typeof source.length === "number" &&
      typeof source.subarray === "function";
  }

  function validOutput(out) {
    return out && typeof out.length === "number" &&
      typeof out.subarray === "function" && typeof out.set === "function";
  }

  function normalizeLimit(value, fallback) {
    var n = value === undefined ? fallback : Number(value);
    if (n < 0 || n !== Math.floor(n) || n > MAX_DYNAMIC_OUTPUT) {
      fail("limite de salida invalido");
    }
    return n;
  }

  function Data(source, output, maxLength) {
    var initial;
    if (!validSource(source)) fail("entrada invalida");
    this.s = source;
    this.i = 0;
    this.tag = 0;
    this.bitcount = 0;
    this.fixed = !!output;
    this.max = maxLength;
    if (output) {
      this.dest = output;
    } else {
      initial = Math.min(maxLength, Math.max(256, source.length * 2));
      this.dest = new Uint8Array(initial);
    }
    this.op = 0;
    this.lt = makeTree();
    this.dt = makeTree();
  }

  function readByte(d) {
    if (d.i >= d.s.length) fail("entrada truncada");
    return d.s[d.i++];
  }

  function ensureOutput(d, needed) {
    var size, grown;
    if (needed > d.max) outputFail("salida supera maxLength", "ASCL_OUTPUT_LIMIT", needed);
    if (needed <= d.dest.length) return;
    if (d.fixed) outputFail("buffer de salida insuficiente", "ASCL_OUTPUT_BUFFER", needed);
    size = d.dest.length || 1;
    while (size < needed) {
      size = Math.min(d.max, size * 2);
      if (size < needed && size === d.max) fail("salida supera maxLength");
    }
    grown = new Uint8Array(size);
    grown.set(d.dest.subarray(0, d.op));
    d.dest = grown;
  }

  function putByte(d, value) {
    if (d.op >= d.max) outputFail("salida supera maxLength", "ASCL_OUTPUT_LIMIT", d.op + 1);
    if (d.op >= d.dest.length) ensureOutput(d, d.op + 1);
    d.dest[d.op++] = value;
  }

  /* W-06: bit-buffer de 32 bits. d.tag acumula bytes LSB-primero y d.bitcount
   * cuenta los bits validos. Los bytes solo se toman de d.s cuando hacen
   * falta, y los enteros no consumidos se devuelven al alinear a byte
   * (bloques stored) o al terminar el stream, conservando la semantica
   * historica de "entrada truncada" y de d.i. */
  var BIT_MASK = [0, 1, 3, 7, 15, 31, 63, 127, 255, 511, 1023, 2047, 4095,
                  8191, 16383, 32767];

  function alignToByte(d) {
    d.i -= d.bitcount >> 3;
    d.tag = 0;
    d.bitcount = 0;
  }

  function getBits(d, num, base) {
    var tag = d.tag, bc = d.bitcount, s = d.s, i = d.i, val;
    while (bc < num) {
      if (i >= s.length) fail("entrada truncada");
      tag |= s[i++] << bc;
      bc += 8;
    }
    val = tag & BIT_MASK[num];
    d.tag = tag >>> num;
    d.bitcount = bc - num;
    d.i = i;
    return val + base;
  }

  function takeBit(d) {
    var tag = d.tag, bit;
    if (d.bitcount === 0) {
      if (d.i >= d.s.length) fail("entrada truncada");
      tag = d.s[d.i++];
      d.bitcount = 8;
    }
    bit = tag & 1;
    d.tag = tag >>> 1;
    d.bitcount--;
    return bit;
  }

  function walkSymbol(d, t) {
    var sum = 0, cur = 0, len;
    for (len = 1; len <= t.maxLen; len++) {
      cur = 2 * cur + takeBit(d);
      sum += t.table[len];
      cur -= t.table[len];
      if (cur < 0) return t.trans[sum + cur];
    }
    fail("codigo Huffman invalido");
  }

  function decodeSymbol(d, t) {
    var tag = d.tag, bc = d.bitcount, s = d.s, i = d.i, entry, len;
    while (bc < LUT_BITS && i < s.length) {
      tag |= s[i++] << bc;
      bc += 8;
    }
    d.tag = tag;
    d.bitcount = bc;
    d.i = i;
    entry = t.lut[tag & (LUT_SIZE - 1)];
    if (entry) {
      len = entry >>> 12;
      if (len <= bc) {
        d.tag = tag >>> len;
        d.bitcount = bc - len;
        return entry & 0xfff;
      }
      /* Ningun codigo de longitud <= bits disponibles coincide: el stream
       * termina en mitad del codigo, igual que el camino bit a bit. */
      fail("entrada truncada");
    }
    /* Codigo mas largo que la tabla o prefijo invalido: recorrido canonico
     * desde la misma posicion (la tabla solo mira, no consume). */
    return walkSymbol(d, t);
  }

  var LBASE = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
  var LBITS = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
  var DBASE = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
  var DBITS = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
  var CLCIDX = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];

  var sltree = makeTree(), sdtree = makeTree(), inited = false;
  function initFixed() {
    var i, lengths = new Uint8Array(288), dl = new Uint8Array(30);
    for (i = 0; i < 144; i++) lengths[i] = 8;
    for (; i < 256; i++) lengths[i] = 9;
    for (; i < 280; i++) lengths[i] = 7;
    for (; i < 288; i++) lengths[i] = 8;
    buildTree(sltree, lengths, 0, 288);
    for (i = 0; i < 30; i++) dl[i] = 5;
    buildTree(sdtree, dl, 0, 30);
    inited = true;
  }

  function inflateBlockData(d, lt, dt) {
    var sym, length, distSym, distance, src, i;
    while (1) {
      sym = decodeSymbol(d, lt);
      if (sym === 256) return;
      if (sym < 256) {
        putByte(d, sym);
      } else {
        if (sym < 257 || sym > 285) fail("simbolo de longitud invalido");
        sym -= 257;
        length = getBits(d, LBITS[sym], LBASE[sym]);
        distSym = decodeSymbol(d, dt);
        if (distSym > 29) fail("simbolo de distancia invalido");
        distance = getBits(d, DBITS[distSym], DBASE[distSym]);
        if (distance < 1 || distance > d.op) fail("distancia invalida");
        ensureOutput(d, d.op + length);
        src = d.op - distance;
        for (i = 0; i < length; i++) d.dest[d.op++] = d.dest[src + i];
      }
    }
  }

  function inflateStored(d) {
    var length, nlength, end;
    alignToByte(d);
    if (d.i + 4 > d.s.length) fail("bloque stored truncado");
    length = readByte(d) | (readByte(d) << 8);
    nlength = readByte(d) | (readByte(d) << 8);
    if (((length ^ 0xffff) & 0xffff) !== nlength) fail("LEN/NLEN invalido");
    if (d.i + length > d.s.length) fail("bloque stored truncado");
    ensureOutput(d, d.op + length);
    end = d.i + length;
    d.dest.set(d.s.subarray(d.i, end), d.op);
    d.op += length;
    d.i = end;
  }

  function decodeTrees(d, lt, dt) {
    var hlit = getBits(d, 5, 257);
    var hdist = getBits(d, 5, 1);
    var hclen = getBits(d, 4, 4);
    var i, num, sym, repeat, prev, total, lengths = new Uint8Array(320);
    var codeTree = makeTree();
    if (hlit > 286 || hdist > 32) fail("cabecera Huffman invalida");
    for (i = 0; i < hclen; i++) lengths[CLCIDX[i]] = getBits(d, 3, 0);
    buildTree(codeTree, lengths, 0, 19);
    total = hlit + hdist;
    for (num = 0; num < total;) {
      sym = decodeSymbol(d, codeTree);
      if (sym <= 15) {
        lengths[num++] = sym;
      } else if (sym === 16) {
        if (num === 0) fail("repeticion Huffman sin previo");
        prev = lengths[num - 1];
        repeat = getBits(d, 2, 3);
        if (num + repeat > total) fail("repeticion Huffman fuera de rango");
        while (repeat--) lengths[num++] = prev;
      } else if (sym === 17) {
        repeat = getBits(d, 3, 3);
        if (num + repeat > total) fail("repeticion Huffman fuera de rango");
        while (repeat--) lengths[num++] = 0;
      } else if (sym === 18) {
        repeat = getBits(d, 7, 11);
        if (num + repeat > total) fail("repeticion Huffman fuera de rango");
        while (repeat--) lengths[num++] = 0;
      } else {
        fail("simbolo Huffman dinamico invalido");
      }
    }
    if (!lengths[256]) fail("arbol sin fin de bloque");
    buildTree(lt, lengths, 0, hlit);
    /* RFC 1951 permite un arbol de distancias vacio si el bloque solo usa literales. */
    buildTree(dt, lengths, hlit, hdist, true);
  }

  function inflateData(source, output, maxLength) {
    var d, bfinal, btype;
    if (!inited) initFixed();
    d = new Data(source, output, maxLength);
    do {
      bfinal = getBits(d, 1, 0);
      btype = getBits(d, 2, 0);
      if (btype === 0) inflateStored(d);
      else if (btype === 1) inflateBlockData(d, sltree, sdtree);
      else if (btype === 2) {
        decodeTrees(d, d.lt, d.dt);
        inflateBlockData(d, d.lt, d.dt);
      } else fail("btype invalido");
    } while (!bfinal);
    /* Devolver los bytes enteros prefetcheados: d.i debe apuntar igual que en
     * la version bit a bit para el chequeo de datos extra tras el stream. */
    alignToByte(d);
    return d;
  }

  function parseZlib(source) {
    var cmf, flg, header;
    if (!validSource(source) || source.length < 6) fail("zlib truncado");
    cmf = source[0];
    flg = source[1];
    header = (cmf << 8) | flg;
    if ((cmf & 15) !== 8 || (cmf >>> 4) > 7) fail("CMF invalido");
    if ((header % 31) !== 0) fail("FCHECK invalido");
    if (flg & 32) fail("diccionario preset no soportado");
    return source.subarray(2, source.length - 4);
  }

  function adler32(bytes, length) {
    var a = 1, b = 0, p = 0, end, i;
    while (p < length) {
      end = Math.min(p + 5552, length);
      for (i = p; i < end; i++) { a += bytes[i]; b += a; }
      a %= 65521;
      b %= 65521;
      p = end;
    }
    return (((b << 16) | a) >>> 0);
  }

  function expectedAdler(source) {
    var p = source.length - 4;
    return (((source[p] << 24) | (source[p + 1] << 16) |
      (source[p + 2] << 8) | source[p + 3]) >>> 0);
  }

  function ASCL_inflateRawInto(source, out, maxLength) {
    var limit;
    if (!validOutput(out)) fail("buffer de salida invalido");
    limit = normalizeLimit(maxLength, out.length);
    return inflateData(source, out, limit).op;
  }

  function ASCL_inflateZlibInto(source, out, maxLength) {
    var raw, d, limit, expected;
    if (!validOutput(out)) fail("buffer de salida invalido");
    limit = normalizeLimit(maxLength, out.length);
    raw = parseZlib(source);
    d = inflateData(raw, out, limit);
    if (d.i !== raw.length) fail("datos extra o DEFLATE incompleto");
    expected = expectedAdler(source);
    if (adler32(out, d.op) !== expected) fail("Adler32 invalido");
    return d.op;
  }

  function exactResult(d) {
    var result;
    if (d.op === d.dest.length) return d.dest;
    result = new Uint8Array(d.op);
    result.set(d.dest.subarray(0, d.op));
    return result;
  }

  function ASCL_inflateRaw(source, maxLength) {
    var limit = normalizeLimit(maxLength, MAX_DYNAMIC_OUTPUT);
    return exactResult(inflateData(source, null, limit));
  }

  function ASCL_inflateZlib(source, maxLength) {
    var raw = parseZlib(source), limit = normalizeLimit(maxLength, MAX_DYNAMIC_OUTPUT);
    var d = inflateData(raw, null, limit), result;
    if (d.i !== raw.length) fail("datos extra o DEFLATE incompleto");
    result = exactResult(d);
    if (adler32(result, result.length) !== expectedAdler(source)) fail("Adler32 invalido");
    return result;
  }

  root.ASCL_inflateRaw = ASCL_inflateRaw;
  root.ASCL_inflateZlib = ASCL_inflateZlib;
  root.ASCL_inflateRawInto = ASCL_inflateRawInto;
  root.ASCL_inflateZlibInto = ASCL_inflateZlibInto;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      ASCL_inflateRaw: ASCL_inflateRaw,
      ASCL_inflateZlib: ASCL_inflateZlib,
      ASCL_inflateRawInto: ASCL_inflateRawInto,
      ASCL_inflateZlibInto: ASCL_inflateZlibInto
    };
  }
})(typeof window !== "undefined" ? window : this);
