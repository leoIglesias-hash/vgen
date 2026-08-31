"use strict";

/* W-18 / W-19: camino indexado del renderer WebGL.
 *
 * En el CI no hay contexto WebGL real, asi que lo que se verifica aca es el
 * CONTRATO con el driver -que formato se sube, con que alineacion, cuantas
 * veces, y sobre todo que la CPU deje de convertir- mas la aritmetica del
 * shader, que es donde viven los errores silenciosos (medio texel).
 * La paridad de pixeles contra Canvas2D corre donde si hay GL: la hace
 * `frontend/diagnostic-player.html` al abrir y la publica en su HUD.
 */

var assert = require("assert");
var WebGLRenderer = require("../frontend/render-webgl.js").WebGLRenderer;

function glMock(options) {
  options = options || {};
  var gl = {
    VERTEX_SHADER: 1, FRAGMENT_SHADER: 2, COMPILE_STATUS: 3, LINK_STATUS: 4,
    ARRAY_BUFFER: 5, STATIC_DRAW: 6, FLOAT: 7, TEXTURE_2D: 8,
    TEXTURE_MIN_FILTER: 9, TEXTURE_MAG_FILTER: 10, TEXTURE_WRAP_S: 11,
    TEXTURE_WRAP_T: 12, CLAMP_TO_EDGE: 13, NEAREST: 14, LINEAR: 15,
    RGBA: 16, UNSIGNED_BYTE: 17, TRIANGLES: 18, MAX_TEXTURE_SIZE: 19,
    TEXTURE0: 33984, TEXTURE1: 33985, UNPACK_ALIGNMENT: 3317, NO_ERROR: 0,
    shaders: [], images: [], subImages: [], params: [], stores: [], units: [],
    sizes: [], draws: 0, linked: 0, errorQueue: options.errors || [],
    createShader: function () { return {}; },
    shaderSource: function (shader, source) { gl.shaders.push(source); },
    compileShader: function () {},
    getShaderParameter: function () { return true; },
    getShaderInfoLog: function () { return ""; },
    createProgram: function () { return {}; },
    attachShader: function () {}, linkProgram: function () { gl.linked += 1; },
    getProgramParameter: function () { return true; },
    getProgramInfoLog: function () { return ""; },
    useProgram: function () {}, createBuffer: function () { return {}; },
    bindBuffer: function () {}, bufferData: function () {},
    getAttribLocation: function () { return 0; },
    enableVertexAttribArray: function () {}, vertexAttribPointer: function () {},
    createTexture: function () { return {}; },
    bindTexture: function () {},
    activeTexture: function (unit) { gl.units.push(unit); },
    texParameteri: function (target, name, value) { gl.params.push([name, value]); },
    pixelStorei: function (name, value) { gl.stores.push([name, value]); },
    getUniformLocation: function (prog, name) { return { name: name }; },
    uniform1i: function () {},
    uniform2f: function (loc, x, y) { gl.sizes.push([x, y]); },
    getParameter: function () { return 4096; },
    getError: function () { return gl.errorQueue.length ? gl.errorQueue.shift() : 0; },
    getExtension: function () { return null; },
    deleteTexture: function () {}, deleteBuffer: function () {},
    deleteProgram: function () {}, deleteShader: function () {},
    viewport: function (x, y, w, h) { gl.viewportArgs = [x, y, w, h]; },
    texImage2D: function () { gl.images.push(Array.prototype.slice.call(arguments)); },
    texSubImage2D: function () { gl.subImages.push(Array.prototype.slice.call(arguments)); },
    readPixels: function () {},
    drawArrays: function () { gl.draws += 1; }
  };
  if (!options.noLuminance) { gl.LUMINANCE = 6409; }
  if (options.noLuminance) { gl.pixelStorei = undefined; }
  return gl;
}

function canvasMock(gl) {
  return {
    style: {}, width: 0, height: 0,
    getContext: function () { return gl; }
  };
}

function indexedReader(cols, rows) {
  var cells = new Uint8Array(cols * rows), pal = new Uint8Array(768), i;
  for (i = 0; i < cells.length; i++) cells[i] = i & 255;
  for (i = 0; i < 256; i++) {
    pal[i * 3] = i & 255; pal[i * 3 + 1] = (255 - i) & 255; pal[i * 3 + 2] = (i * 3) & 255;
  }
  return {
    header: { mode: 3, cols: cols, rows: rows },
    n: cols * rows, cells: cells, palette: pal, paletteEntries: 256,
    dirtyFull: true, dirtyY0: 0, dirtyY1: rows - 1, fillCalls: 0,
    fillRGBA: function (out) { this.fillCalls += 1; return out; },
    fillRGBAChanged: function (out) { this.fillCalls += 1; return out; },
    fillRGBARows: function (out) { this.fillCalls += 1; return out; }
  };
}

function indexUploads(gl) {
  var out = [], i;
  for (i = 0; i < gl.images.length; i++) {
    if (gl.images[i][2] === gl.LUMINANCE) out.push(gl.images[i]);
  }
  return out;
}

function paletteUploads(gl) {
  var out = [], i;
  for (i = 0; i < gl.images.length; i++) {
    if (gl.images[i][2] === gl.RGBA && gl.images[i][3] === 256 && gl.images[i][4] === 1) {
      out.push(gl.images[i]);
    }
  }
  return out;
}

/* ------------------------------------------- 1. el camino indexado se activa --- */

var gl = glMock();
var reader = indexedReader(64, 32);
var renderer = new WebGLRenderer(canvasMock(gl));
assert.strictEqual(renderer.init(reader, 1, "nearest"), true);
assert.strictEqual(renderer.indexed, true, "con LUMINANCE disponible debe indexar");
assert.strictEqual(renderer.rgba, null,
  "en indexado no se reserva el RGBA residente (8,3 MB a 1920)");

var alignment = null, s;
for (s = 0; s < gl.stores.length; s++) {
  if (gl.stores[s][0] === gl.UNPACK_ALIGNMENT) alignment = gl.stores[s][1];
}
assert.strictEqual(alignment, 1,
  "UNPACK_ALIGNMENT debe quedar en 1: el default 4 corre las filas de una textura de 1 byte");

renderer.draw(reader);
assert.strictEqual(reader.fillCalls, 0,
  "en indexado la CPU no convierte: ningun fill del reader debe llamarse");
var uploads = indexUploads(gl);
var full = uploads[uploads.length - 1];
assert.strictEqual(full[3], 64, "la textura de indices mide cols x rows");
assert.strictEqual(full[4], 32);
assert.strictEqual(full[6], gl.LUMINANCE, "formato LUMINANCE");
assert.strictEqual(full[8], reader.cells, "se sube `cells` tal cual, sin copia");
var pals = paletteUploads(gl);
assert.strictEqual(pals.length, 1, "la paleta se sube una vez, 256x1 RGBA");
assert.strictEqual(pals[0][8].length, 1024);
assert.strictEqual(pals[0][8][3], 255, "alfa opaco en la textura de paleta");
assert.strictEqual(gl.draws, 1);

/* ------------------------------------------------- 2. banda parcial y paleta --- */

reader.dirtyFull = false;
reader.dirtyY0 = 8; reader.dirtyY1 = 11;
renderer.draw(reader);
assert.strictEqual(reader.fillCalls, 0);
assert.strictEqual(gl.subImages.length, 1, "la banda va por texSubImage2D");
var band = gl.subImages[0];
assert.strictEqual(band[3], 8, "yoffset = primera fila sucia");
assert.strictEqual(band[5], 4, "alto = filas sucias inclusivas");
assert.strictEqual(band[6], gl.LUMINANCE);
assert.strictEqual(band[8].length, 64 * 4, "la banda son cols*filas bytes de indices");
assert.strictEqual(band[8].buffer, reader.cells.buffer,
  "la banda es una vista de `cells`, no una copia");
assert.strictEqual(paletteUploads(gl).length, 1,
  "la paleta no se re-sube si no cambio");

var otherPalette = new Uint8Array(768);
reader.palette = otherPalette;
renderer.draw(reader);
assert.strictEqual(paletteUploads(gl).length, 2,
  "una paleta nueva se re-sube (1 KB), y solo entonces");

/* --------------------------------------------- 3. reconstruccion soft (W-19) --- */

var softGl = glMock();
var softReader = indexedReader(32, 16);
var softRenderer = new WebGLRenderer(canvasMock(softGl));
softRenderer.init(softReader, 1, "nearest");
var programsBefore = softGl.linked;
softRenderer.setReconstruction("soft");
assert.strictEqual(softGl.linked, programsBefore + 1,
  "soft compila su propio programa, no ramifica por fragmento");
var i, linearOnIndex = false;
for (i = 0; i < softGl.params.length; i++) {
  if ((softGl.params[i][0] === softGl.TEXTURE_MIN_FILTER ||
       softGl.params[i][0] === softGl.TEXTURE_MAG_FILTER) &&
      softGl.params[i][1] === softGl.LINEAR) {
    linearOnIndex = true;
  }
}
assert.strictEqual(linearOnIndex, false,
  "la textura de INDICES nunca se filtra con LINEAR: interpolar indices da colores arbitrarios");
assert(softGl.sizes.length > 0, "el shader soft recibe u_size");
assert.deepStrictEqual(softGl.sizes[softGl.sizes.length - 1], [32, 16]);

/* El shader soft tiene que tomar 4 taps y mezclar colores, no indices. */
var softSource = "";
for (i = 0; i < softGl.shaders.length; i++) {
  if (softGl.shaders[i].indexOf("mix(") >= 0) softSource = softGl.shaders[i];
}
assert(softSource, "debe existir un fragment shader con mezcla");
assert(softSource.indexOf("fract(") >= 0, "la mezcla necesita la parte fraccionaria");
assert.strictEqual((softSource.match(/palLookup\(/g) || []).length, 5,
  "4 taps mas la definicion: los lookups se hacen DESPUES de resolver cada indice");

/* -------------------------------------------- 4. backing store de la mezcla --- */

assert.strictEqual(softRenderer.setPresentationSize(1920, 960), true,
  "en soft el backing store sigue al tamano de presentacion");
assert.strictEqual(softRenderer.canvas.width, 1920);
assert.strictEqual(softRenderer.canvas.height, 960);
assert.deepStrictEqual(softGl.viewportArgs, [0, 0, 1920, 960]);
softRenderer.setReconstruction("nearest");
assert.strictEqual(softRenderer.canvas.width, 32,
  "en nearest el backing store vuelve a la grilla, bit a bit como antes");
assert.strictEqual(softRenderer.canvas.height, 16);
softRenderer.setReconstruction("soft");
assert.strictEqual(softRenderer.setPresentationSize(10, 5), true);
assert.strictEqual(softRenderer.canvas.width, 32,
  "nunca por debajo de la grilla: eso perderia informacion del archivo");

/* ------------------------------------------------- 5. aritmetica del shader --- */

/* Medio texel: para los 256 indices posibles, el lookup tiene que caer dentro
 * del texel correcto de la paleta 256x1. Sin el offset de 0,5/256 los colores
 * salen corridos una entrada y nadie lo nota hasta verlo en el TV. */
var idx, coord, texel;
for (idx = 0; idx < 256; idx++) {
  coord = (idx / 255) * 0.99609375 + 0.001953125;
  texel = Math.floor(coord * 256);
  assert.strictEqual(texel, idx, "indice " + idx + " cae en el texel " + texel);
  assert(Math.abs(coord * 256 - (idx + 0.5)) < 1e-6,
    "el lookup debe caer en el CENTRO del texel, no en su borde");
}

/* -------------------------------------------------- 6. fallbacks obligatorios --- */

var plainGl = glMock({ noLuminance: true });
var plainReader = indexedReader(16, 8);
var plainRenderer = new WebGLRenderer(canvasMock(plainGl));
plainRenderer.init(plainReader, 1, "nearest");
assert.strictEqual(plainRenderer.indexed, false,
  "sin LUMINANCE se conserva el camino RGBA entero");
assert(plainRenderer.rgba, "el RGBA residente vuelve a existir en el fallback");
plainRenderer.draw(plainReader);
assert.strictEqual(plainReader.fillCalls, 1, "el fallback si convierte en CPU");
assert.strictEqual(plainGl.images[0][2], plainGl.RGBA);

/* Driver que acepta la sonda pero rechaza LUMINANCE en la textura del video:
   el renderer baja a RGBA en caliente en vez de cortar la reproduccion. */
var lateGl = glMock({ errors: [0, 0, 0, 1285] });
var lateReader = indexedReader(16, 8);
var lateRenderer = new WebGLRenderer(canvasMock(lateGl));
lateRenderer.init(lateReader, 1, "nearest");
assert.strictEqual(lateRenderer.indexed, true, "la sonda de init pasa");
lateRenderer.draw(lateReader);
assert.strictEqual(lateRenderer.indexed, false,
  "un fallo en la primera subida indexada degrada a RGBA");
assert(lateRenderer.rgba, "y reserva el RGBA que hacia falta");
assert.strictEqual(lateReader.fillCalls, 1, "el cuadro se rehace completo por RGBA");
assert.strictEqual(lateGl.draws, 1, "el cuadro igual se dibuja: no hay hueco visible");

/* Sonda de init que falla: ni siquiera se intenta el camino indexado. */
var probeGl = glMock({ errors: [0, 1281] });
var probeReader = indexedReader(16, 8);
var probeRenderer = new WebGLRenderer(canvasMock(probeGl));
probeRenderer.init(probeReader, 1, "nearest");
assert.strictEqual(probeRenderer.indexed, false,
  "si el driver rechaza una LUMINANCE de 2x2, no se arriesga la del video");
assert(probeRenderer.rgba);

/* Modo no PIXEL (PAL/RGB de v1): cells no es un byte por celda. */
var palGl = glMock();
var palReader = indexedReader(16, 8);
palReader.header.mode = 1;
palReader.cells = new Uint8Array(16 * 8 * 2);
var palRenderer = new WebGLRenderer(canvasMock(palGl));
palRenderer.init(palReader, 1, "nearest");
assert.strictEqual(palRenderer.indexed, false,
  "solo PIXEL tiene un indice de 1 byte por celda");

console.log("render indexed tests: OK");
