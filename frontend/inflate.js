/*
 * inflate.js - Descompresor DEFLATE/zlib minimo, ES5, sin dependencias.
 *
 * Por que existe: los webviews viejos NO traen un inflate sincronico nativo en JS.
 * Para leer frames con tag=ZLIB del .ascl necesitamos descomprimir en el cliente.
 * Implementacion propia de RFC 1951 (DEFLATE) + envoltura zlib (RFC 1950).
 *
 * API:
 *   ASCL_inflateZlib(u8)  -> Uint8Array   (entrada = stream zlib de Python zlib.compress)
 *   ASCL_inflateRaw(u8)   -> Uint8Array   (entrada = DEFLATE crudo)
 *
 * Nota: si el .ascl se encodea con --compress none (tag=RAW) este modulo no hace falta;
 * en ese caso se sirve el archivo con gzip/br por HTTP (decodifica el webview nativo).
 */
(function (root) {
  "use strict";

  function makeTree() { return { table: new Uint16Array(16), trans: new Uint16Array(288) }; }

  function buildTree(t, lengths, off, num) {
    var i, sum, offs = new Uint16Array(16);
    for (i = 0; i < 16; i++) t.table[i] = 0;
    for (i = 0; i < num; i++) t.table[lengths[off + i]]++;
    t.table[0] = 0;
    for (sum = 0, i = 0; i < 16; i++) { offs[i] = sum; sum += t.table[i]; }
    for (i = 0; i < num; i++) if (lengths[off + i]) t.trans[offs[lengths[off + i]]++] = i;
  }

  function Data(source) {
    this.s = source; this.i = 0; this.tag = 0; this.bitcount = 0;
    this.dest = []; this.lt = makeTree(); this.dt = makeTree();
  }

  function getBit(d) {
    if (d.bitcount-- === 0) { d.tag = d.s[d.i++]; d.bitcount = 7; }
    var bit = d.tag & 1; d.tag >>>= 1; return bit;
  }
  function getBits(d, num, base) {
    if (!num) return base;
    var val = 0, i = 0;
    for (; i < num; i++) val |= getBit(d) << i;
    return val + base;
  }
  function decodeSymbol(d, t) {
    var sum = 0, cur = 0, len = 0;
    do {
      cur = 2 * cur + getBit(d); len++;
      sum += t.table[len]; cur -= t.table[len];
    } while (cur >= 0);
    return t.trans[sum + cur];
  }

  var LBASE = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
  var LBITS = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
  var DBASE = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
  var DBITS = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
  var CLCIDX = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];

  var sltree = makeTree(), sdtree = makeTree(), inited = false;
  function initFixed() {
    var i, lengths = new Uint8Array(288);
    for (i = 0; i < 144; i++) lengths[i] = 8;
    for (; i < 256; i++) lengths[i] = 9;
    for (; i < 280; i++) lengths[i] = 7;
    for (; i < 288; i++) lengths[i] = 8;
    buildTree(sltree, lengths, 0, 288);
    var dl = new Uint8Array(30);
    for (i = 0; i < 30; i++) dl[i] = 5;
    buildTree(sdtree, dl, 0, 30);
    inited = true;
  }

  function inflateBlockData(d, lt, dt) {
    while (1) {
      var sym = decodeSymbol(d, lt);
      if (sym === 256) return;
      if (sym < 256) { d.dest.push(sym); }
      else {
        sym -= 257;
        var length = getBits(d, LBITS[sym], LBASE[sym]);
        var dist = decodeSymbol(d, dt);
        var offs = d.dest.length - getBits(d, DBITS[dist], DBASE[dist]);
        for (var i = offs; i < offs + length; i++) d.dest.push(d.dest[i]);
      }
    }
  }

  function inflateStored(d) {
    while (d.bitcount > 7) { d.i--; d.bitcount -= 8; }
    var length = d.s[d.i] | (d.s[d.i + 1] << 8);
    d.i += 4; // length + ~length
    for (var i = 0; i < length; i++) d.dest.push(d.s[d.i++]);
    d.bitcount = 0;
  }

  function decodeTrees(d, lt, dt) {
    var hlit = getBits(d, 5, 257);
    var hdist = getBits(d, 5, 1);
    var hclen = getBits(d, 4, 4);
    var i, num, lengths = new Uint8Array(320);
    for (i = 0; i < 19; i++) lengths[i] = 0;
    for (i = 0; i < hclen; i++) lengths[CLCIDX[i]] = getBits(d, 3, 0);
    var codeTree = makeTree();
    buildTree(codeTree, lengths, 0, 19);
    for (num = 0; num < hlit + hdist;) {
      var sym = decodeSymbol(d, codeTree);
      if (sym === 16) { var prev = lengths[num - 1]; for (var l = getBits(d, 2, 3); l; l--) lengths[num++] = prev; }
      else if (sym === 17) { for (var l2 = getBits(d, 3, 3); l2; l2--) lengths[num++] = 0; }
      else if (sym === 18) { for (var l3 = getBits(d, 7, 11); l3; l3--) lengths[num++] = 0; }
      else lengths[num++] = sym;
    }
    buildTree(lt, lengths, 0, hlit);
    buildTree(dt, lengths, hlit, hdist);
  }

  function ASCL_inflateRaw(source) {
    if (!inited) initFixed();
    var d = new Data(source), bfinal, btype;
    do {
      bfinal = getBit(d);
      btype = getBits(d, 2, 0);
      if (btype === 0) inflateStored(d);
      else if (btype === 1) inflateBlockData(d, sltree, sdtree);
      else if (btype === 2) { decodeTrees(d, d.lt, d.dt); inflateBlockData(d, d.lt, d.dt); }
      else throw new Error("inflate: btype invalido");
    } while (!bfinal);
    return Uint8Array.from ? Uint8Array.from(d.dest) : new Uint8Array(d.dest);
  }

  function ASCL_inflateZlib(source) {
    // zlib (RFC 1950): 2 bytes de header, luego DEFLATE, luego adler32 (ignorado).
    var cmf = source[0];
    if ((cmf & 0x0f) === 8) {
      return ASCL_inflateRaw(source.subarray(2));
    }
    // si no parece zlib, intentar como raw
    return ASCL_inflateRaw(source);
  }

  root.ASCL_inflateRaw = ASCL_inflateRaw;
  root.ASCL_inflateZlib = ASCL_inflateZlib;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { ASCL_inflateRaw: ASCL_inflateRaw, ASCL_inflateZlib: ASCL_inflateZlib };
  }
})(typeof window !== "undefined" ? window : this);
