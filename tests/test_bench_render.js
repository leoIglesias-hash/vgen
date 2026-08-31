"use strict";

/* W-16: cablea el banco de conversion indice->RGBA en la regresion (regla 7).
 *
 * El CI publica la tabla, no la juzga: el runner comparte CPU y cualquier
 * asercion de velocidad seria intermitente. Lo que si se verifica es la
 * PARIDAD, que run() comprueba internamente y hace fallar con excepcion:
 * el camino de bytes vigente, el prototipo LUT de W-17 y la reconstruccion
 * completa tienen que producir exactamente los mismos bytes RGBA.
 */

var assert = require("assert");
var bench = require("../tools/bench_render.js");

var lines = [];
var rows = bench.run({
  repeats: 4,
  log: function (line) { lines.push(line); console.log(line); }
});

var PROFILES = 3, VARIANTS = 2;
assert.strictEqual(rows.length, bench.GRIDS.length * PROFILES * VARIANTS,
  "el banco debe medir las tres grillas por tres perfiles y dos variantes");
assert(lines.length >= rows.length,
  "cada medicion debe quedar publicada como una linea de tabla en el CI");
assert(lines[lines.length - 1].indexOf("paridad: OK") === 0,
  "el banco debe cerrar declarando la paridad verificada");

var seenBytes = 0, seenLut = 0, i, row;
for (i = 0; i < rows.length; i++) {
  row = rows[i];
  assert(row.cells > 0, "cada caso debe tocar celdas: " + row.grid + " " + row.profile);
  assert(row.ms > 0, "cada caso debe reportar tiempo: " + row.grid + " " + row.profile);
  assert(isFinite(row.mbs) && row.mbs > 0, "cada caso debe reportar MB/s");
  if (row.variant === "reader") seenBytes++;
  if (row.variant === "lut32") seenLut++;
}
assert.strictEqual(seenBytes, rows.length / 2);
assert.strictEqual(seenLut, rows.length / 2);

/* El perfil disperso tiene que ser realmente disperso y el de tiles densos
 * tiene que tocar mas celdas: si el corpus se degrada, la tabla mentiria. */
function pick(grid, profile) {
  var k;
  for (k = 0; k < rows.length; k++) {
    if (rows[k].grid === grid && rows[k].profile === profile) return rows[k];
  }
  return null;
}
var gridLabel = bench.GRIDS[0].label;
var key = pick(gridLabel, "key"), sparse = pick(gridLabel, "sparse");
var tiles = pick(gridLabel, "tiles");
assert(sparse.cells < key.cells * 0.10,
  "el delta disperso debe quedar por debajo del 10 % de las celdas");
assert(tiles.cells > sparse.cells,
  "el delta de tiles densos debe tocar mas celdas que el disperso");
assert(tiles.cells < key.cells,
  "el delta de tiles densos no puede tocar el frame entero");

/* La LUT se construye detectando la endianness, nunca asumiendo little endian. */
var palette = new Uint8Array([0, 0, 0, 10, 20, 30]);
var lut = bench.makeLut(palette, 2);
var word = new Uint32Array(1), viewBytes;
word[0] = lut[1];
viewBytes = new Uint8Array(word.buffer);
assert.strictEqual(viewBytes[0], 10, "R primero en el orden de bytes de la maquina");
assert.strictEqual(viewBytes[1], 20);
assert.strictEqual(viewBytes[2], 30);
assert.strictEqual(viewBytes[3], 255, "alfa opaco");

console.log("bench render tests: OK");
