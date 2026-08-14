"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var Canvas2DRenderer = require("../frontend/render-canvas2d.js").Canvas2DRenderer;
var WebGLRenderer = require("../frontend/render-webgl.js").WebGLRenderer;


function pixelReader(cols, rows) {
  var reader = {
    header: { mode: 3, cols: cols, rows: rows },
    n: cols * rows,
    dirtyFull: true,
    dirtyY0: 0,
    dirtyY1: rows - 1,
    fullCalls: 0,
    rowCalls: [],
    fillRGBA: function (out) {
      var i;
      this.fullCalls += 1;
      for (i = 0; i < out.length; i += 4) {
        out[i] = 20; out[i + 1] = 40; out[i + 2] = 60; out[i + 3] = 255;
      }
    },
    fillRGBARows: function (out, y0, y1) {
      var i, first = y0 * cols * 4, end = (y1 + 1) * cols * 4;
      this.rowCalls.push([y0, y1]);
      for (i = first; i < end; i += 4) {
        out[i] = 21; out[i + 1] = 41; out[i + 2] = 61; out[i + 3] = 255;
      }
    }
  };
  return reader;
}


function changedPixelReader(cols, rows) {
  var reader = pixelReader(cols, rows);
  reader.changedCalls = 0;
  reader.fillRGBAChanged = function (out) {
    this.changedCalls += 1;
    out[cols * 4] = 99;
    out[cols * 4 + 3] = 255;
  };
  return reader;
}


function canvas2DMock(rejectDirtyRect) {
  var ctx = {
    putCalls: [], dirtyAttempts: 0,
    createImageData: function (w, h) {
      return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
    },
    putImageData: function () {
      if (arguments.length > 3) {
        this.dirtyAttempts += 1;
        if (rejectDirtyRect) throw new Error("dirty rect no soportado");
      }
      this.putCalls.push(Array.prototype.slice.call(arguments));
    }
  };
  return {
    style: {}, width: 0, height: 0, ctx: ctx,
    getContext: function (name) { return name === "2d" ? ctx : null; }
  };
}


function webGLMock() {
  var params = [];
  var gl = {
    VERTEX_SHADER: 1, FRAGMENT_SHADER: 2, COMPILE_STATUS: 3, LINK_STATUS: 4,
    ARRAY_BUFFER: 5, STATIC_DRAW: 6, FLOAT: 7, TEXTURE_2D: 8,
    TEXTURE_MIN_FILTER: 9, TEXTURE_MAG_FILTER: 10, TEXTURE_WRAP_S: 11,
    TEXTURE_WRAP_T: 12, CLAMP_TO_EDGE: 13, NEAREST: 14, LINEAR: 15,
    RGBA: 16, UNSIGNED_BYTE: 17, TRIANGLES: 18, MAX_TEXTURE_SIZE: 19,
    NO_ERROR: 0,
    imageCalls: [], subImageCalls: [], draws: 0,
    deletedTextures: 0, deletedBuffers: 0, deletedPrograms: 0,
    deletedShaders: 0, lostContexts: 0,
    createShader: function () { return {}; }, shaderSource: function () {},
    compileShader: function () {}, getShaderParameter: function () { return true; },
    getShaderInfoLog: function () { return ""; }, createProgram: function () { return {}; },
    attachShader: function () {}, linkProgram: function () {},
    getProgramParameter: function () { return true; }, getProgramInfoLog: function () { return ""; },
    useProgram: function () {}, createBuffer: function () { return {}; },
    bindBuffer: function () {}, bufferData: function () {}, getAttribLocation: function () { return 0; },
    enableVertexAttribArray: function () {}, vertexAttribPointer: function () {},
    createTexture: function () { return {}; }, bindTexture: function () {},
    texParameteri: function (target, name, value) { params.push([name, value]); },
    getUniformLocation: function () { return 0; }, uniform1i: function () {},
    getParameter: function () { return 4096; },
    getError: function () { return 0; },
    getExtension: function (name) {
      if (name !== "WEBGL_lose_context") return null;
      return { loseContext: function () { gl.lostContexts += 1; } };
    },
    deleteTexture: function () { this.deletedTextures += 1; },
    deleteBuffer: function () { this.deletedBuffers += 1; },
    deleteProgram: function () { this.deletedPrograms += 1; },
    deleteShader: function () { this.deletedShaders += 1; },
    viewport: function () {},
    texImage2D: function () {
      this.imageCalls.push(Array.prototype.slice.call(arguments));
    },
    texSubImage2D: function () {
      this.subImageCalls.push(Array.prototype.slice.call(arguments));
    },
    drawArrays: function () { this.draws += 1; }
  };
  gl.params = params;
  return gl;
}


function webGLCanvas(gl, rejectLightAttributes) {
  var canvas = {
    style: {}, width: 0, height: 0,
    contextCalls: [],
    getContext: function (name, attributes) {
      this.contextCalls.push([name, attributes]);
      if (rejectLightAttributes && attributes) return null;
      return gl;
    }
  };
  return canvas;
}


(function testCanvasPixelBackingAndReconstruction() {
  var canvas = canvas2DMock();
  var reader = pixelReader(320, 180);
  var renderer = new Canvas2DRenderer(canvas);
  assert.strictEqual(renderer.init(reader, 4, "soft"), true);
  assert.strictEqual(canvas.width, 320);
  assert.strictEqual(canvas.height, 180);
  assert.strictEqual(canvas.style.width, "1280px");
  assert.strictEqual(renderer.reconstruction, "soft");
  assert.strictEqual(canvas.ctx.imageSmoothingEnabled, true);
  renderer.draw(reader);
  assert.strictEqual(reader.fullCalls, 1);
  assert.strictEqual(canvas.ctx.putCalls.length, 1);
  assert.strictEqual(canvas.ctx.putCalls[0].length, 3, "primer cuadro debe copiarse completo");
  renderer.setReconstruction("nearest");
  assert.strictEqual(canvas.ctx.imageSmoothingEnabled, false);
}());


(function testWebGLPixelBackingAndFilters() {
  var gl = webGLMock();
  var canvas = webGLCanvas(gl);
  var reader = pixelReader(320, 180);
  var renderer = new WebGLRenderer(canvas);
  assert.strictEqual(renderer.init(reader, 4, "soft"), true);
  assert.strictEqual(canvas.width, 320);
  assert.strictEqual(canvas.height, 180);
  assert.strictEqual(canvas.style.width, "1280px");
  assert(gl.params.some(function (p) { return p[1] === gl.LINEAR; }));
  renderer.setReconstruction("nearest");
  assert(gl.params.some(function (p) { return p[1] === gl.NEAREST; }));
  assert.strictEqual(canvas.contextCalls.length, 1);
  assert.deepStrictEqual(canvas.contextCalls[0][1], {
    alpha: false, antialias: false, depth: false, stencil: false,
    preserveDrawingBuffer: false
  }, "WebGL debe evitar buffers que el quad fullscreen no utiliza");
}());


(function testWebGLLegacyContextRetryWithoutAttributes() {
  var gl = webGLMock(), canvas = webGLCanvas(gl, true);
  var renderer = new WebGLRenderer(canvas);
  assert.strictEqual(renderer.init(pixelReader(8, 5), 4, "nearest"), true);
  assert.strictEqual(canvas.contextCalls.length, 3);
  assert.strictEqual(canvas.contextCalls[0][0], "webgl");
  assert.strictEqual(canvas.contextCalls[1][0], "experimental-webgl");
  assert.strictEqual(canvas.contextCalls[2][0], "webgl");
  assert.strictEqual(canvas.contextCalls[2][1], undefined,
    "un WebView que rechaza atributos debe recibir la llamada legacy exacta");
}());


(function testWebGLTriesPrefixedContextWhenStandardThrows() {
  var gl = webGLMock();
  var canvas = {
    style: {}, width: 0, height: 0, contextCalls: [],
    getContext: function (name, attributes) {
      this.contextCalls.push([name, attributes]);
      if (name === "webgl") throw new Error("standard context unsupported");
      return name === "experimental-webgl" ? gl : null;
    }
  };
  var renderer = new WebGLRenderer(canvas);
  assert.strictEqual(renderer.init(pixelReader(8, 5), 4, "nearest"), true);
  assert.strictEqual(canvas.contextCalls.length, 2);
  assert.strictEqual(canvas.contextCalls[0][0], "webgl");
  assert.strictEqual(canvas.contextCalls[1][0], "experimental-webgl");
  assert(canvas.contextCalls[1][1],
    "el contexto prefijado tambien debe recibir atributos livianos");
}());


(function testWebGLRejectsTexturesLargerThanTheDeviceLimit() {
  var gl = webGLMock();
  gl.getParameter = function (name) {
    assert.strictEqual(name, gl.MAX_TEXTURE_SIZE);
    return 4;
  };
  var renderer = new WebGLRenderer(webGLCanvas(gl));
  assert.strictEqual(renderer.init(pixelReader(8, 5), 4, "nearest"), false);
  assert.strictEqual(renderer.gl, null);
  assert.strictEqual(renderer.rgba, null, "no debe reservar el buffer RGBA imposible");
}());


(function testBothRenderersConvertTheSameDirtyRows() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(), canvasReader = pixelReader(cols, rows);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  var gl = webGLMock(), webglReader = pixelReader(cols, rows);
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  canvasRenderer.init(canvasReader, 4, "soft");
  webglRenderer.init(webglReader, 4, "soft");

  // Aunque el reader marque parcial, el primer draw siempre inicializa el frame entero.
  canvasReader.dirtyFull = false; canvasReader.dirtyY0 = 2; canvasReader.dirtyY1 = 3;
  webglReader.dirtyFull = false; webglReader.dirtyY0 = 2; webglReader.dirtyY1 = 3;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 1);
  assert.strictEqual(webglReader.fullCalls, 1);
  assert.deepStrictEqual(canvasReader.rowCalls, []);
  assert.deepStrictEqual(webglReader.rowCalls, []);

  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.deepStrictEqual(canvasReader.rowCalls, [[2, 3]]);
  assert.deepStrictEqual(webglReader.rowCalls, canvasReader.rowCalls);

  var dirtyPut = canvas.ctx.putCalls[1];
  assert.deepStrictEqual(dirtyPut.slice(1), [0, 0, 0, 2, cols, 2],
                         "Canvas2D debe copiar exactamente la banda inclusiva");
  assert.strictEqual(gl.subImageCalls.length, 1);
  var sub = gl.subImageCalls[0], pixels = sub[8];
  assert.deepStrictEqual(sub.slice(2, 6), [0, 2, cols, 2],
                         "WebGL debe subir exactamente la misma banda");
  assert.strictEqual(pixels.buffer, webglRenderer.rgba.buffer,
                     "la banda WebGL debe ser una vista, no una copia");
  assert.strictEqual(pixels.byteOffset, 2 * cols * 4);
  assert.strictEqual(pixels.byteLength, 2 * cols * 4);

  // El mismo rango reutiliza la vista en lugar de crear un objeto por draw.
  webglRenderer.draw(webglReader);
  assert.strictEqual(gl.subImageCalls[1][8], pixels);
}());


(function testBothRenderersPreferExactChangedCellsWhenAvailable() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(), canvasReader = changedPixelReader(cols, rows);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  var gl = webGLMock(), webglReader = changedPixelReader(cols, rows);
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  canvasRenderer.init(canvasReader, 4, "nearest");
  webglRenderer.init(webglReader, 4, "nearest");
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);

  canvasReader.dirtyFull = false; canvasReader.dirtyY0 = 1; canvasReader.dirtyY1 = 1;
  webglReader.dirtyFull = false; webglReader.dirtyY0 = 1; webglReader.dirtyY1 = 1;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.changedCalls, 1);
  assert.strictEqual(webglReader.changedCalls, 1);
  assert.deepStrictEqual(canvasReader.rowCalls, []);
  assert.deepStrictEqual(webglReader.rowCalls, []);
  assert.strictEqual(canvas.ctx.putCalls[1].length, 7,
    "Canvas conserva la copia por banda aunque convierta solo celdas dirty");
  assert.strictEqual(gl.subImageCalls.length, 1,
    "WebGL conserva el upload por banda sin crear un buffer nuevo");
}());


(function testCanvasFallsBackWhenDirtyPutIsUnsupported() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(true), reader = pixelReader(cols, rows);
  var renderer = new Canvas2DRenderer(canvas);
  renderer.init(reader, 4, "nearest");
  renderer.draw(reader);

  reader.dirtyFull = false; reader.dirtyY0 = 1; reader.dirtyY1 = 1;
  renderer.draw(reader);
  assert.strictEqual(canvas.ctx.dirtyAttempts, 1);
  assert.strictEqual(canvas.ctx.putCalls.length, 2);
  assert.strictEqual(canvas.ctx.putCalls[1].length, 3,
                     "si falla el dirty rect debe copiar el ImageData persistente completo");

  reader.dirtyY0 = 2; reader.dirtyY1 = 3;
  renderer.draw(reader);
  assert.deepStrictEqual(reader.rowCalls, [[1, 1], [2, 3]],
                         "el fallback conserva la conversion por filas");
  assert.strictEqual(canvas.ctx.dirtyAttempts, 1,
                     "un Canvas incompatible no debe volver a recibir la firma de 7 argumentos");
  assert.strictEqual(canvas.ctx.putCalls.length, 3);
  assert.strictEqual(canvas.ctx.putCalls[2].length, 3);
}());


(function testEmptyDirtyRangeDoesNoWork() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(), canvasReader = pixelReader(cols, rows);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  var gl = webGLMock(), webglReader = pixelReader(cols, rows);
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  canvasRenderer.init(canvasReader, 4, "nearest");
  webglRenderer.init(webglReader, 4, "nearest");
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);

  canvasReader.dirtyFull = false; canvasReader.dirtyY0 = rows; canvasReader.dirtyY1 = -1;
  webglReader.dirtyFull = false; webglReader.dirtyY0 = rows; webglReader.dirtyY1 = -1;
  canvasReader.fillRGBARows = null; webglReader.fillRGBARows = null;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 1);
  assert.strictEqual(webglReader.fullCalls, 1);
  assert.deepStrictEqual(canvasReader.rowCalls, []);
  assert.deepStrictEqual(webglReader.rowCalls, []);
  assert.strictEqual(canvas.ctx.putCalls.length, 1);
  assert.strictEqual(gl.imageCalls.length, 1);
  assert.strictEqual(gl.subImageCalls.length, 0);
  assert.strictEqual(gl.draws, 1, "un cuadro repetido tampoco debe redibujar el quad");
}());


(function testNonCanonicalInvertedDirtyRangeFallsBackToFull() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(), canvasReader = pixelReader(cols, rows);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  var gl = webGLMock(), webglReader = pixelReader(cols, rows);
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  canvasRenderer.init(canvasReader, 4, "nearest");
  webglRenderer.init(webglReader, 4, "nearest");
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);

  canvasReader.dirtyFull = false; canvasReader.dirtyY0 = 4; canvasReader.dirtyY1 = 1;
  webglReader.dirtyFull = false; webglReader.dirtyY0 = 4; webglReader.dirtyY1 = 1;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 2);
  assert.strictEqual(webglReader.fullCalls, 2);
  assert.strictEqual(canvas.ctx.putCalls[1].length, 3);
  assert.strictEqual(gl.imageCalls.length, 2,
    "metadata dirty invertida no debe congelar silenciosamente el frame");
}());


(function testBrokenPartialWebGLUploadFallsBackAndIsMemoized() {
  var gl = webGLMock(), errors = [0, 0, 0, 1282];
  gl.getError = function () { return errors.length ? errors.shift() : 0; };
  var reader = pixelReader(8, 5);
  var renderer = new WebGLRenderer(webGLCanvas(gl));
  renderer.init(reader, 4, "nearest");
  renderer.draw(reader);

  reader.dirtyFull = false; reader.dirtyY0 = 1; reader.dirtyY1 = 2;
  renderer.draw(reader);
  assert.strictEqual(gl.subImageCalls.length, 1);
  assert.strictEqual(gl.imageCalls.length, 2,
    "un GL_ERROR en el primer sub-upload debe corregirse con upload completo");
  assert.strictEqual(gl.imageCalls[1][8], renderer.rgba,
    "el fallback debe reutilizar el RGBA persistente");
  assert.strictEqual(renderer._subUploadSupported, false);

  reader.dirtyY0 = 3; reader.dirtyY1 = 3;
  renderer.draw(reader);
  assert.strictEqual(gl.subImageCalls.length, 1,
    "el driver defectuoso no debe volver a recibir texSubImage2D");
  assert.strictEqual(gl.imageCalls.length, 3);
}());


(function testInitialFullWebGLUploadIsProbedOnlyOnce() {
  var gl = webGLMock(), errors = [0, 1285], errorCalls = 0;
  gl.getError = function () {
    errorCalls += 1;
    return errors.length ? errors.shift() : 0;
  };
  var reader = pixelReader(8, 5);
  var renderer = new WebGLRenderer(webGLCanvas(gl));
  renderer.init(reader, 4, "nearest");
  assert.throws(function () { renderer.draw(reader); }, /reservar la textura/,
    "un texImage2D fallido silenciosamente debe activar el fallback del player");
  assert.strictEqual(renderer._texInit, false);
  assert.strictEqual(errorCalls, 2);

  gl.getError = function () { errorCalls += 1; return 0; };
  renderer.draw(reader);
  assert.strictEqual(renderer._texInit, true);
  assert.strictEqual(errorCalls, 4);
  reader.dirtyFull = true;
  renderer.draw(reader);
  assert.strictEqual(errorCalls, 4,
    "los keyframes posteriores no deben pagar getError sincronico");
}());


(function testExplicitRendererDisposal() {
  var canvas = canvas2DMock(), reader = pixelReader(8, 5);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  canvasRenderer.init(reader, 4, "nearest");
  canvasRenderer.draw(reader);
  canvasRenderer.dispose();
  assert.strictEqual(canvasRenderer.rgba, null);
  assert.strictEqual(canvasRenderer.imgData, null);
  assert.strictEqual(canvasRenderer.ctx, null);

  var gl = webGLMock();
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  webglRenderer.init(reader, 4, "nearest");
  webglRenderer.draw(reader);
  webglRenderer.dispose(true);
  assert.strictEqual(gl.deletedTextures, 1);
  assert.strictEqual(gl.deletedBuffers, 1);
  assert.strictEqual(gl.deletedPrograms, 1);
  assert.strictEqual(gl.deletedShaders, 2);
  assert.strictEqual(gl.lostContexts, 1);
  assert.strictEqual(webglRenderer.gl, null);
  assert.strictEqual(webglRenderer.rgba, null);
}());


(function testFullAndLegacyFallbacks() {
  var cols = 8, rows = 5;
  var canvas = canvas2DMock(), canvasReader = pixelReader(cols, rows);
  var canvasRenderer = new Canvas2DRenderer(canvas);
  var gl = webGLMock(), webglReader = pixelReader(cols, rows);
  var webglRenderer = new WebGLRenderer(webGLCanvas(gl));
  canvasRenderer.init(canvasReader, 4, "nearest");
  webglRenderer.init(webglReader, 4, "nearest");
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);

  // Un keyframe o una paleta nueva se expresa como dirtyFull.
  canvasReader.dirtyFull = true; canvasReader.dirtyY0 = 1; canvasReader.dirtyY1 = 2;
  webglReader.dirtyFull = true; webglReader.dirtyY0 = 1; webglReader.dirtyY1 = 2;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 2);
  assert.strictEqual(webglReader.fullCalls, 2);
  assert.strictEqual(canvas.ctx.putCalls[1].length, 3);
  assert.strictEqual(gl.imageCalls.length, 2);

  // Un reader anterior, sin fillRGBARows, mantiene el camino completo aun con dirty parcial.
  canvasReader.dirtyFull = false; webglReader.dirtyFull = false;
  var canvasRows = canvasReader.fillRGBARows, webglRows = webglReader.fillRGBARows;
  canvasReader.fillRGBARows = null; webglReader.fillRGBARows = null;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 3);
  assert.strictEqual(webglReader.fullCalls, 3);
  assert.strictEqual(canvas.ctx.putCalls[2].length, 3);
  assert.strictEqual(gl.imageCalls.length, 3);

  // Metadata dirty fraccionaria o fuera del frame tampoco llega al camino parcial.
  canvasReader.fillRGBARows = canvasRows; webglReader.fillRGBARows = webglRows;
  canvasReader.dirtyY0 = 1.5; canvasReader.dirtyY1 = 2;
  webglReader.dirtyY0 = 1.5; webglReader.dirtyY1 = 2;
  canvasRenderer.draw(canvasReader);
  webglRenderer.draw(webglReader);
  assert.strictEqual(canvasReader.fullCalls, 4);
  assert.strictEqual(webglReader.fullCalls, 4);
  assert.deepStrictEqual(canvasReader.rowCalls, []);
  assert.deepStrictEqual(webglReader.rowCalls, []);
  assert.strictEqual(gl.imageCalls.length, 4);
}());


(function testDistributedRenderersStayES5() {
  ["render-canvas2d.js", "render-webgl.js"].forEach(function (name) {
    var source = fs.readFileSync(path.join(__dirname, "..", "frontend", name), "utf8");
    assert.strictEqual(/\b(?:let|const|class)\b/.test(source), false, name);
    assert.strictEqual(/=>/.test(source), false, name);
    assert.strictEqual(/\b(?:fetch|Promise)\b/.test(source), false, name);
    assert.doesNotThrow(function () { new Function(source); }, name);
  });
}());


console.log("frontend renderer tests: OK");
