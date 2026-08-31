#!/usr/bin/env node
/*
 * bench_render.js - W-16 (F9): banco de la etapa de conversion indice->RGBA.
 *
 * Uso: node tools/bench_render.js [ruta-a-reader-v2.js] [repeticiones]
 *
 * Mide lo que el frontend paga por frame DESPUES de decodificar: pasar de un
 * indice por celda a RGBA. Es CPU pura sobre typed arrays, no necesita
 * navegador ni canvas, del mismo estilo que bench_inflate.js y
 * bench_reader_v2.js.
 *
 * Corpus determinista: tres grillas (768x432, 1280x720, 1920x1080) por tres
 * perfiles (keyframe completo, delta disperso ~5 % de celdas, delta de tiles
 * densos), paleta de 256 entradas, tiles de 16.
 *
 * Dos variantes por caso:
 *   bytes  el camino vigente del reader (fillRGBA / fillRGBAChanged): 3 lecturas
 *          de paleta y 4 escrituras de byte por celda.
 *   lut32  el prototipo de W-17: LUT Uint32Array(256) con la paleta empaquetada
 *          en el orden de bytes de la maquina y UNA escritura de palabra.
 *
 * El banco NO juzga tiempos: el runner de CI es ruidoso y una asercion de
 * velocidad seria un test intermitente. Publica la tabla (regla 5: la mejora se
 * registra, no se supone) y verifica PARIDAD, que si es criterio duro: las dos
 * variantes y la conversion completa tienen que producir los mismos bytes.
 *
 * El clip sintetico es ASCL v2 a proposito: la etapa medida es identica en v2 y
 * v3 (el SPARSE diferencial de v3 cambia el walk, no la conversion).
 */
"use strict";

var path = require("path");

var TILE = 16;
var PAL_ENTRIES = 256;
var OP_SKIP = 0, OP_SPARSE = 2, OP_PAL8 = 7;
var TAG_KEY_RAW = 4, TAG_DELTA_RAW = 6;
var SPARSE_RATE = 0.05;

var GRIDS = [
  { label: "768x432", cols: 768, rows: 432 },
  { label: "1280x720", cols: 1280, rows: 720 },
  { label: "1920x1080", cols: 1920, rows: 1080 }
];

/* ---------------------------------------------------------------- corpus --- */

function makeRng(seed) {
  var s = (seed >>> 0) || 1;
  return function () {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s;
  };
}

function writeUvar(buffer, pos, value) {
  var part;
  do {
    part = value % 128;
    value = Math.floor(value / 128);
    buffer[pos++] = part | (value ? 128 : 0);
  } while (value);
  return pos;
}

function gridInfo(grid) {
  var tileCols = Math.ceil(grid.cols / TILE);
  var tileRows = Math.ceil(grid.rows / TILE);
  return {
    label: grid.label,
    cols: grid.cols,
    rows: grid.rows,
    n: grid.cols * grid.rows,
    tileCols: tileCols,
    tileRows: tileRows,
    tileCount: tileCols * tileRows
  };
}

/* Misma geometria que ReaderV2._tileGeometry, incluida la fila de tiles
 * recortada que aparece en 1920x1080 (1080 no es multiplo de 16). */
function tileBox(info, tile, box) {
  var tx = tile % info.tileCols, ty = Math.floor(tile / info.tileCols);
  box.x = tx * TILE;
  box.y = ty * TILE;
  box.w = Math.min(TILE, info.cols - box.x);
  box.h = Math.min(TILE, info.rows - box.y);
  box.npix = box.w * box.h;
  return box;
}

function paletteBytes(count) {
  var out = Buffer.alloc(count * 3), i;
  for (i = 0; i < count; i++) {
    out[i * 3] = (i * 7) & 255;
    out[i * 3 + 1] = (255 - i * 5) & 255;
    out[i * 3 + 2] = (i * 3) & 255;
  }
  return out;
}

/* Keyframe: un PAL8 por tile. Devuelve el stream y deja en cells el estado
 * exacto que tendra el reader, que el delta disperso necesita para no emitir
 * escrituras identicas (el validador las rechaza). */
function buildKeyStream(info, cells) {
  var out = Buffer.alloc(info.tileCount + info.n), pos = 0;
  var rng = makeRng(0x5EED01 ^ info.n), box = {}, tile, y, x, base, value;
  for (tile = 0; tile < info.tileCount; tile++) {
    tileBox(info, tile, box);
    out[pos++] = OP_PAL8;
    for (y = 0; y < box.h; y++) {
      base = (box.y + y) * info.cols + box.x;
      for (x = 0; x < box.w; x++) {
        value = rng() & 255;
        out[pos++] = value;
        cells[base + x] = value;
      }
    }
  }
  return out.slice(0, pos);
}

/* Delta disperso: SPARSE en todos los tiles con ~5 % de las celdas de cada uno.
 * Marca celdas exactas, que es el perfil que recorre dirtyCellBits. */
function buildSparseStream(info, cells) {
  var out = Buffer.alloc(info.tileCount * 4 + info.n), pos = 0;
  var box = {}, tile, k, i, offset, y, x, global, touched = 0;
  for (tile = 0; tile < info.tileCount; tile++) {
    tileBox(info, tile, box);
    k = Math.round(box.npix * SPARSE_RATE);
    if (k < 1) k = 1;
    out[pos++] = OP_SPARSE;
    pos = writeUvar(out, pos, k);
    for (i = 0; i < k; i++) {
      /* Estrictamente creciente por construccion (npix/k >= 1): la canonicidad
       * del formato exige offsets crecientes dentro del tile. */
      offset = Math.floor(i * box.npix / k);
      pos = writeUvar(out, pos, offset);
      y = Math.floor(offset / box.w);
      x = offset - y * box.w;
      global = (box.y + y) * info.cols + box.x + x;
      out[pos++] = (cells[global] + 1) & 255;
      touched++;
    }
  }
  return { stream: out.slice(0, pos), touched: touched };
}

/* Delta de tiles densos: PAL8 en los tiles pares, SKIP_RUN en los impares.
 * Marca tiles enteros, que es el perfil que recorre dirtyTiles. */
function buildDenseStream(info) {
  var out = Buffer.alloc(info.tileCount * 4 + info.n), pos = 0;
  var rng = makeRng(0xBEEF11 ^ info.n), box = {}, tile, i, run = 0, touched = 0;
  for (tile = 0; tile < info.tileCount; tile++) {
    if (tile & 1) { run++; continue; }
    if (run) { out[pos++] = OP_SKIP; pos = writeUvar(out, pos, run); run = 0; }
    tileBox(info, tile, box);
    out[pos++] = OP_PAL8;
    for (i = 0; i < box.npix; i++) out[pos++] = rng() & 255;
    touched += box.npix;
  }
  if (run) { out[pos++] = OP_SKIP; pos = writeUvar(out, pos, run); }
  return { stream: out.slice(0, pos), touched: touched };
}

function block(tag, palette, payload) {
  var pal = palette || Buffer.alloc(0);
  var body = Buffer.alloc(3 + pal.length + payload.length);
  var out;
  body[0] = tag;
  body.writeUInt16LE(pal.length / 3, 1);
  pal.copy(body, 3);
  payload.copy(body, 3 + pal.length);
  out = Buffer.alloc(4 + body.length);
  out.writeUInt32LE(body.length, 0);
  body.copy(out, 4);
  return out;
}

function makeAscl(ASCLV2, frames, info) {
  var header = Buffer.alloc(32), table = Buffer.alloc(frames.length * 4);
  var offset = 32 + table.length, i, out;
  header.write("ASCL", 0, "ascii");
  header[4] = 2;
  header[5] = 3;
  header[6] = 12;              /* tabla de offsets + paleta global */
  header[7] = 15;
  header.writeUInt16LE(info.cols, 8);
  header.writeUInt16LE(info.rows, 10);
  header.writeUInt16LE(PAL_ENTRIES, 12);
  header.writeUInt32LE(frames.length, 14);
  header[18] = 0;
  header[19] = 3;              /* cell_fmt PIXEL */
  header.writeUInt32LE(32, 20);
  header.writeUInt16LE(1000, 24);
  header[26] = TILE;
  header[27] = 1;              /* codec regional */
  for (i = 0; i < frames.length; i++) {
    table.writeUInt32LE(offset, i * 4);
    offset += frames[i].length;
  }
  out = Buffer.concat([header, table].concat(frames));
  out.writeUInt32LE(ASCLV2.crc32v2(out), 28);
  return out;
}

function buildCase(ASCLV2, grid) {
  var info = gridInfo(grid);
  var cells = Buffer.alloc(info.n);
  var pal = paletteBytes(PAL_ENTRIES);
  var key = buildKeyStream(info, cells);
  var sparse = buildSparseStream(info, cells);
  var dense = buildDenseStream(info);
  var file = makeAscl(ASCLV2, [
    block(TAG_KEY_RAW, pal, key),
    block(TAG_DELTA_RAW, null, sparse.stream),
    block(TAG_DELTA_RAW, null, dense.stream)
  ], info);
  return {
    info: info,
    reader: ASCLV2.parse(file.buffer, file.byteOffset, file.byteLength),
    touched: [info.n, sparse.touched, dense.touched]
  };
}

/* -------------------------------------------------- prototipo LUT (W-17) --- */

var LOW_BIT = new Uint8Array(256);
(function () {
  var bit;
  for (bit = 0; bit < 8; bit++) LOW_BIT[1 << bit] = bit;
}());

/* La endianness se detecta, no se asume: el mismo contrato que pide W-17. */
function makeLut(palette, entries) {
  var lut = new Uint32Array(256), probe = new Uint32Array(1);
  var probeBytes = new Uint8Array(probe.buffer), little, i, r, g, b;
  probe[0] = 1;
  little = probeBytes[0] === 1;
  for (i = 0; i < entries; i++) {
    r = palette[i * 3]; g = palette[i * 3 + 1]; b = palette[i * 3 + 2];
    lut[i] = little
      ? (((255 << 24) | (b << 16) | (g << 8) | r) >>> 0)
      : (((r << 24) | (g << 16) | (b << 8) | 255) >>> 0);
  }
  return lut;
}

function lutFull(reader, out32, lut) {
  var cells = reader.cells, end = reader.n, i;
  for (i = 0; i < end; i++) out32[i] = lut[cells[i]];
}

function lutChanged(reader, out32, lut) {
  var cells = reader.cells, cols = reader.header.cols, rows = reader.header.rows;
  var size = reader.tileSize, tileCols = reader.tileCols;
  var d, tile, tx, ty, x0, y0, w, h, y, x, base, i, bits, byteIndex, byte, mask;
  if (reader.dirtyFull) { lutFull(reader, out32, lut); return; }
  for (d = 0; d < reader.dirtyCount; d++) {
    tile = reader.dirtyTiles[d];
    tx = tile % tileCols; ty = Math.floor(tile / tileCols);
    x0 = tx * size; y0 = ty * size;
    w = Math.min(size, cols - x0); h = Math.min(size, rows - y0);
    for (y = 0; y < h; y++) {
      base = (y0 + y) * cols + x0;
      for (x = 0; x < w; x++) { i = base + x; out32[i] = lut[cells[i]]; }
    }
  }
  if (reader.dirtyCellCount) {
    bits = reader.dirtyCellBits;
    for (byteIndex = 0; byteIndex < bits.length; byteIndex++) {
      byte = bits[byteIndex];
      while (byte) {
        mask = byte & -byte;
        i = (byteIndex << 3) + LOW_BIT[mask];
        out32[i] = lut[cells[i]];
        byte ^= mask;
      }
    }
  }
}

/* ---------------------------------------------------------------- medida --- */

function timeIt(fn, repeats) {
  var t0, dt, k;
  t0 = process.hrtime();
  for (k = 0; k < repeats; k++) fn();
  dt = process.hrtime(t0);
  return dt[0] * 1000 + dt[1] / 1e6;
}

function firstDifference(a, b) {
  var i, end = a.length;
  for (i = 0; i < end; i++) if (a[i] !== b[i]) return i;
  return -1;
}

function assertSame(label, a, b) {
  var index = firstDifference(a, b);
  if (index >= 0) {
    throw new Error("paridad rota en " + label + ": primer byte distinto en " +
                    index + " (" + a[index] + " vs " + b[index] + ")");
  }
}

function pad(text, width, right) {
  text = "" + text;
  while (text.length < width) text = right ? text + " " : " " + text;
  return text;
}

function run(options) {
  options = options || {};
  var ASCLV2 = options.module ||
    require(options.target || path.join(__dirname, "..", "frontend", "reader-v2.js"));
  var grids = options.grids || GRIDS;
  var repeats = options.repeats || 40;
  var log = options.log || function (line) { console.log(line); };
  var rows = [], gi, ci, kase, info, reader, lut, out, alt, ref, out32, alt32;
  var PROFILES = ["key", "sparse", "tiles"];
  var profile, touched, msBytes, msLut, makeBytes, makeLut32;

  if (typeof ASCLV2.parse !== "function" || typeof ASCLV2.crc32v2 !== "function") {
    throw new Error("el modulo no exporta parse/crc32v2");
  }

  log(pad("grilla", 11, true) + pad("perfil", 8, true) + pad("celdas", 10) +
      pad("variante", 10) + pad("ms/frame", 10) + pad("MB/s", 9) + pad("x", 7));

  for (gi = 0; gi < grids.length; gi++) {
    kase = buildCase(ASCLV2, grids[gi]);
    info = kase.info;
    reader = kase.reader;
    out = new Uint8Array(info.n * 4);
    alt = new Uint8Array(info.n * 4);
    ref = new Uint8Array(info.n * 4);
    out32 = new Uint32Array(out.buffer, out.byteOffset, info.n);
    alt32 = new Uint32Array(alt.buffer, alt.byteOffset, info.n);

    for (ci = 0; ci < PROFILES.length; ci++) {
      profile = PROFILES[ci];
      touched = kase.touched[ci];
      reader.seek(ci);
      lut = makeLut(reader.palette, reader.paletteEntries);

      /* Una pasada de cada variante, y la conversion completa como referencia:
       * el camino incremental tiene que coincidir con reconstruir todo. */
      if (ci === 0) {
        reader.fillRGBA(out);
        lutFull(reader, alt32, lut);
      } else {
        reader.fillRGBAChanged(out);
        lutChanged(reader, alt32, lut);
      }
      reader.fillRGBA(ref);
      assertSame(info.label + " " + profile + " bytes", out, ref);
      assertSame(info.label + " " + profile + " lut32", alt, ref);

      if (ci === 0) {
        makeBytes = function () { reader.fillRGBA(out); };
        makeLut32 = function () { lutFull(reader, out32, lut); };
      } else {
        makeBytes = function () { reader.fillRGBAChanged(out); };
        makeLut32 = function () { lutChanged(reader, out32, lut); };
      }
      timeIt(makeBytes, 2);
      timeIt(makeLut32, 2);
      msBytes = timeIt(makeBytes, repeats) / repeats;
      msLut = timeIt(makeLut32, repeats) / repeats;

      rows.push({
        grid: info.label, profile: profile, cells: touched,
        variant: "bytes", ms: msBytes, mbs: touched * 4 / 1048576 / (msBytes / 1000),
        speedup: 1
      });
      rows.push({
        grid: info.label, profile: profile, cells: touched,
        variant: "lut32", ms: msLut, mbs: touched * 4 / 1048576 / (msLut / 1000),
        speedup: msLut > 0 ? msBytes / msLut : 0
      });
      log(pad(info.label, 11, true) + pad(profile, 8, true) + pad(touched, 10) +
          pad("bytes", 10) + pad(msBytes.toFixed(3), 10) +
          pad(rows[rows.length - 2].mbs.toFixed(0), 9) + pad("1.00", 7));
      log(pad("", 11, true) + pad("", 8, true) + pad("", 10) +
          pad("lut32", 10) + pad(msLut.toFixed(3), 10) +
          pad(rows[rows.length - 1].mbs.toFixed(0), 9) +
          pad(rows[rows.length - 1].speedup.toFixed(2), 7));
    }
    reader.dispose();
  }
  log("paridad: OK (bytes == lut32 == conversion completa en " +
      (rows.length / 2) + " casos)");
  return rows;
}

function main() {
  var target = process.argv[2] || null;
  var repeats = parseInt(process.argv[3] || "40", 10);
  if (!(repeats > 0)) {
    console.error("uso: node tools/bench_render.js [reader-v2.js] [repeticiones]");
    process.exit(2);
  }
  run({ target: target ? path.resolve(target) : null, repeats: repeats });
}

if (require.main === module) main();

module.exports = {
  run: run,
  GRIDS: GRIDS,
  makeLut: makeLut,
  lutFull: lutFull,
  lutChanged: lutChanged
};
