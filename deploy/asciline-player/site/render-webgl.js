/*
 * render-webgl.js - Renderer WebGL 1.0 (ES5). La ruta que rompe el techo de 360p.
 *
 * Idea (spec 3.1): en vez de cientos de miles de fillRect, se sube el frame como
 * UNA textura RGBA (cols x rows) y se dibuja un quad fullscreen -> 1 texImage2D + 1 draw.
 * Filtro NEAREST/SOFT seleccionable. En PIXEL el backing store conserva cols x rows
 * y el zoom es solo visual (CSS), evitando framebuffers sobredimensionados.
 *
 * Cubre cualquier modo via reader.fillRGBA/fillRGBAChanged/fillRGBARows (PIXEL
 * nitido; PAL/RGB como mosaico de color sin glifos). Para glifos ASCII usar Canvas2D.
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
      var message = gl.getShaderInfoLog(s);
      try { if (gl.deleteShader) { gl.deleteShader(s); } } catch (ignoredDelete) {}
      throw new Error("shader: " + message);
    }
    return s;
  }

  function tryContext(canvas, name, attributes, withAttributes) {
    try {
      return withAttributes ? canvas.getContext(name, attributes) : canvas.getContext(name);
    } catch (ignoredContextError) {
      return null;
    }
  }

  function getContext(canvas) {
    var gl = null;
    var light = {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: false
    };
    /* El quad ocupa todo el framebuffer: alpha, AA, depth y stencil no aportan
       imagen. Algunos WebViews antiguos rechazan el objeto de atributos, por eso
       se reintenta exactamente con la llamada legacy sin segundo argumento. */
    gl = tryContext(canvas, "webgl", light, true);
    if (!gl) { gl = tryContext(canvas, "experimental-webgl", light, true); }
    if (gl) { return gl; }
    gl = tryContext(canvas, "webgl", null, false);
    if (!gl) { gl = tryContext(canvas, "experimental-webgl", null, false); }
    return gl;
  }

  function WebGLRenderer(canvas) {
    this.canvas = canvas; this.gl = null; this.name = "webgl";
  }

  WebGLRenderer.prototype.init = function (reader, cellPx, reconstruction) {
    var h = reader.header;
    var gl = getContext(this.canvas);
    if (!gl) return false;                 // <-- degradacion elegante a Canvas2D
    this.gl = gl;

    // Evita pedir una textura imposible (y potenciales OOM) antes de reservar RGBA.
    // WebViews incompletos que no exponen la consulta conservan el comportamiento ES5.
    try {
      if (gl.MAX_TEXTURE_SIZE !== undefined && typeof gl.getParameter === "function") {
        var maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
        if (typeof maxTextureSize === "number" && maxTextureSize > 0 &&
            (h.cols > maxTextureSize || h.rows > maxTextureSize)) {
          this.dispose(true);
          return false;
        }
      }
    } catch (sizeError) {}
    this.reader = reader;
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
    this.prog = prog;
    this.vertexShader = compile(gl, gl.VERTEX_SHADER, VERT);
    this.fragmentShader = compile(gl, gl.FRAGMENT_SHADER, FRAG);
    gl.attachShader(prog, this.vertexShader);
    gl.attachShader(prog, this.fragmentShader);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error("link: " + gl.getProgramInfoLog(prog));
    }
    gl.useProgram(prog);
    var buf = gl.createBuffer();
    this.buf = buf;
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
    this._texInit = false;
    this._fullUploadChecked = false;
    this._subRGBA = null; this._subY0 = -1; this._subY1 = -1;
    this._subUploadSupported = null;
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
    var gl = this.gl, y0 = reader.dirtyY0, y1 = reader.dirtyY1;
    var dirtyKnown = typeof y0 === "number" && isFinite(y0) && Math.floor(y0) === y0 &&
                     typeof y1 === "number" && isFinite(y1) && Math.floor(y1) === y1;
    var empty = dirtyKnown && y0 === this.texH && y1 === -1;
    var dirtyValid = empty || (dirtyKnown && y0 >= 0 && y0 < this.texH &&
      y1 >= y0 && y1 < this.texH);
    var full = !this._texInit || reader.dirtyFull || !dirtyKnown ||
               !dirtyValid;

    // Rango vacio canonico despues de inicializar: ni siquiera altera el estado GL.
    if (!full && empty) return;
    if (!full && typeof reader.fillRGBAChanged !== "function" &&
        typeof reader.fillRGBARows !== "function") full = true;
    gl.bindTexture(gl.TEXTURE_2D, this.tex);

    // Primer cuadro, keyframe/cambio de paleta, metadata dirty no confiable o lector
    // anterior: conversion y subida completas como fallback seguro.
    if (full) {
      var probeFull = !this._fullUploadChecked && typeof gl.getError === "function";
      var fullError = 0;
      reader.fillRGBA(this.rgba);
      if (probeFull) {
        try { gl.getError(); } catch (ignoredBeforeFull) { probeFull = false; }
      }
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.texW, this.texH, 0,
                    gl.RGBA, gl.UNSIGNED_BYTE, this.rgba);
      if (probeFull) {
        try { fullError = gl.getError(); }
        catch (ignoredFullProbe) { fullError = 0; }
        if (fullError !== 0 && fullError !== gl.NO_ERROR) {
          throw new Error("WebGL no pudo reservar la textura del video");
        }
      }
      /* El chequeo sincronico se paga una sola vez, nunca por keyframe. */
      this._fullUploadChecked = true;
      this._texInit = true;
    } else if (y1 >= y0) {
      var hh = y1 - y0 + 1;
      if (typeof reader.fillRGBAChanged === "function") {
        reader.fillRGBAChanged(this.rgba);
      } else {
        reader.fillRGBARows(this.rgba, y0, y1);
      }
      // subarray crea solo una vista del buffer persistente, no copia la banda. Se
      // reutiliza mientras el rango no cambie para evitar basura por cuadro.
      if (!this._subRGBA || this._subY0 !== y0 || this._subY1 !== y1) {
        this._subRGBA = this.rgba.subarray(y0 * this.texW * 4, (y1 + 1) * this.texW * 4);
        this._subY0 = y0; this._subY1 = y1;
      }
      if (this._subUploadSupported === false) {
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.texW, this.texH, 0,
                      gl.RGBA, gl.UNSIGNED_BYTE, this.rgba);
      } else {
        var firstProbe = this._subUploadSupported === null;
        var canProbe = firstProbe && typeof gl.getError === "function";
        var uploadFailed = false, errorCode = 0;
        if (canProbe) {
          try { gl.getError(); } catch (ignoredOldError) { canProbe = false; }
        }
        try {
          gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, y0, this.texW, hh,
                           gl.RGBA, gl.UNSIGNED_BYTE, this._subRGBA);
        } catch (subUploadError) {
          uploadFailed = true;
        }
        if (!uploadFailed && canProbe) {
          try { errorCode = gl.getError(); }
          catch (ignoredProbeError) { errorCode = 0; }
          if (errorCode !== 0 && errorCode !== gl.NO_ERROR) { uploadFailed = true; }
        }
        if (uploadFailed) {
          /* El RGBA persistente ya contiene el frame completo anterior mas las
             filas nuevas: el fallback exacto no necesita copiar otro buffer. */
          this._subUploadSupported = false;
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.texW, this.texH, 0,
                        gl.RGBA, gl.UNSIGNED_BYTE, this.rgba);
        } else if (firstProbe) {
          this._subUploadSupported = true;
        }
      }
    }
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };

  WebGLRenderer.prototype.dispose = function (releaseContext) {
    var gl = this.gl, extension = null;
    if (gl) {
      try { if (this.tex && gl.deleteTexture) { gl.deleteTexture(this.tex); } } catch (ignoredTexture) {}
      try { if (this.buf && gl.deleteBuffer) { gl.deleteBuffer(this.buf); } } catch (ignoredBuffer) {}
      try { if (this.prog && gl.deleteProgram) { gl.deleteProgram(this.prog); } } catch (ignoredProgram) {}
      try {
        if (this.vertexShader && gl.deleteShader) { gl.deleteShader(this.vertexShader); }
        if (this.fragmentShader && gl.deleteShader) { gl.deleteShader(this.fragmentShader); }
      } catch (ignoredShader) {}
      if (releaseContext && typeof gl.getExtension === "function") {
        try { extension = gl.getExtension("WEBGL_lose_context"); } catch (ignoredExtension) {}
        try { if (extension && extension.loseContext) { extension.loseContext(); } } catch (ignoredLoss) {}
      }
    }
    this.gl = null; this.reader = null; this.canvas = null;
    this.tex = null; this.buf = null; this.prog = null;
    this.vertexShader = null; this.fragmentShader = null;
    this.rgba = null; this._subRGBA = null;
    this._texInit = false; this._fullUploadChecked = false;
    this._subUploadSupported = null;
  };

  root.WebGLRenderer = WebGLRenderer;
})(typeof window !== "undefined" ? window : this);
