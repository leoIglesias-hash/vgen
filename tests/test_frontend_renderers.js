"use strict";

var assert = require("assert");
var Canvas2DRenderer = require("../frontend/render-canvas2d.js").Canvas2DRenderer;
var WebGLRenderer = require("../frontend/render-webgl.js").WebGLRenderer;


function pixelReader(cols, rows) {
  return {
    header: { mode: 3, cols: cols, rows: rows },
    n: cols * rows,
    dirtyFull: true,
    dirtyY0: 0,
    dirtyY1: rows - 1,
    fillRGBA: function (out) {
      var i;
      for (i = 0; i < out.length; i += 4) {
        out[i] = 20; out[i + 1] = 40; out[i + 2] = 60; out[i + 3] = 255;
      }
    }
  };
}


function canvas2DMock() {
  var ctx = {
    puts: 0,
    createImageData: function (w, h) {
      return { width: w, height: h, data: new Uint8ClampedArray(w * h * 4) };
    },
    putImageData: function () { this.puts += 1; }
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
    RGBA: 16, UNSIGNED_BYTE: 17, TRIANGLES: 18,
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
    viewport: function () {}, texImage2D: function () {}, texSubImage2D: function () {},
    drawArrays: function () {}
  };
  gl.params = params;
  return gl;
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
  assert.strictEqual(canvas.ctx.puts, 1);
  renderer.setReconstruction("nearest");
  assert.strictEqual(canvas.ctx.imageSmoothingEnabled, false);
}());


(function testWebGLPixelBackingAndFilters() {
  var gl = webGLMock();
  var canvas = {
    style: {}, width: 0, height: 0,
    getContext: function () { return gl; }
  };
  var reader = pixelReader(320, 180);
  var renderer = new WebGLRenderer(canvas);
  assert.strictEqual(renderer.init(reader, 4, "soft"), true);
  assert.strictEqual(canvas.width, 320);
  assert.strictEqual(canvas.height, 180);
  assert.strictEqual(canvas.style.width, "1280px");
  assert(gl.params.some(function (p) { return p[1] === gl.LINEAR; }));
  renderer.setReconstruction("nearest");
  assert(gl.params.some(function (p) { return p[1] === gl.NEAREST; }));
}());

console.log("frontend renderer tests: OK");
