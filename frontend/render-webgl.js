/*
 * render-webgl.js - Renderer WebGL 1.0 (ES5). La ruta que rompe el techo de 360p.
 *
 * Idea (spec 3.1): en vez de cientos de miles de fillRect, se sube el frame como
 * UNA textura RGBA (cols x rows) y se dibuja un quad fullscreen -> 1 texImage2D + 1 draw.
 * Filtro NEAREST/SOFT seleccionable. En PIXEL el backing store conserva cols x rows
 * y el zoom es solo visual (CSS), evitando framebuffers sobredimensionados.
 *
 * Cubre cualquier modo via reader.fillRGBA (PIXEL nitido; PAL/RGB como mosaico de
 * color sin glifos). Para glifos ASCII usar Canvas2D (o glyph-atlas, mejora Fase 6).
 *
 * Fallback (NO negociable): si getContext('webgl') devuelve null, init() retorna false
 * y el caller cae a Canvas2D sin romper nada.
 */
(function (root) {
  "use strict";

  function reconstructionName(value) {
    return value === "soft" ? "soft" : "nearest";
  }

  function setCanvasImageRendering(canvas, reconstruction) {
    var style = canvas.style;
    if (reconstruction === "soft") {
      style.imageRendering = "auto";
      style.msInterpolationMode = "bicubic";
    } else {
      style.imageRendering = "pixelated";
      if (!style.imageRendering) { style.imageRendering = "-moz-crisp-edges"; }
      style.msInterpolationMode = "nearest-neighbor";
    }
  }

  var VERT = [
    "attribute vec2 a_pos;",
    "varying vec2 v_uv;",
    "void main(){",
    "  v_uv = vec2((a_pos.x+1.0)*0.5, (1.0-a_pos.y)*0.5);", // flip Y (textura top-left)
    "  gl_Position = vec4(a_pos, 0.0, 1.0);",
    "}"
  ].join("\n");

  var FRAG = [
    "precision mediump float;",
    "varying vec2 v_uv;",
    "uniform sampler2D u_tex;",
    "void main(){ gl_FragColor = texture2D(u_tex, v_uv); }"
  ].join("\n");

  function compile(gl, type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      throw new Error("shader: " + gl.getShaderInfoLog(s));
    }
    return s;
  }

  function WebGLRenderer(canvas) {
    this.canvas = canvas; this.gl = null; this.name = "webgl";
  }

  WebGLRenderer.prototype.init = function (reader, cellPx, reconstruction) {
    var h = reader.header;
    var gl = null;
    try {
      gl = this.canvas.getContext("webgl") || this.canvas.getContext("experimental-webgl");
    } catch (e) { gl = null; }
    if (!gl) return false;                 // <-- degradacion elegante a Canvas2D
    this.gl = gl; this.reader = reader;
    this.cellPx = cellPx || (h.mode === 3 ? 4 : 8);
    if (h.mode === 3) {
      this.canvas.width = h.cols;
      this.canvas.height = h.rows;
      this.canvas.style.width = (h.cols * this.cellPx) + "px";
      this.canvas.style.height = "auto";
    } else {
      this.canvas.width = h.cols * this.cellPx;
      this.canvas.height = h.rows * this.cellPx;
    }
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);

    var prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error("link: " + gl.getProgramInfoLog(prog));
    }
    gl.useProgram(prog);
    this.prog = prog;

    var buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1, -1,  1, -1,  -1, 1,   -1, 1,  1, -1,  1, 1
    ]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    this.tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.uniform1i(gl.getUniformLocation(prog, "u_tex"), 0);

    this.rgba = new Uint8Array(reader.n * 4);
    this.texW = h.cols; this.texH = h.rows;
    this.setReconstruction(reconstruction);
    return true;
  };

  WebGLRenderer.prototype.setReconstruction = function (reconstruction) {
    var gl = this.gl;
    this.reconstruction = reconstructionName(reconstruction);
    setCanvasImageRendering(this.canvas, this.reconstruction);
    if (gl && this.tex) {
      var filter = this.reconstruction === "soft" ? gl.LINEAR : gl.NEAREST;
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    }
  };

  WebGLRenderer.prototype.draw = function (reader) {
    var gl = this.gl;
    reader.fillRGBA(this.rgba);
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    // C) subida parcial: si solo cambiaron unas filas (DELTA/MASK), texSubImage2D de esa banda.
    //    Primer frame / keyframe / reader viejo sin dirty -> subida completa (fallback seguro).
    if (!this._texInit || reader.dirtyFull || reader.dirtyY0 === undefined) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.texW, this.texH, 0,
                    gl.RGBA, gl.UNSIGNED_BYTE, this.rgba);
      this._texInit = true;
    } else if (reader.dirtyY1 >= reader.dirtyY0) {
      var y0 = reader.dirtyY0, hh = reader.dirtyY1 - y0 + 1;
      var sub = this.rgba.subarray(y0 * this.texW * 4, (reader.dirtyY1 + 1) * this.texW * 4);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, y0, this.texW, hh,
                       gl.RGBA, gl.UNSIGNED_BYTE, sub);
    } // else: nada cambio -> no se sube nada
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };

  root.WebGLRenderer = WebGLRenderer;
})(typeof window !== "undefined" ? window : this);
