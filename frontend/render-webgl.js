/*
 * render-webgl.js - Renderer WebGL 1.0 (ES5). La ruta que rompe el techo de 360p.
 *
 * Idea (spec 3.1): en vez de cientos de miles de fillRect, se sube el frame como
 * UNA textura y se dibuja un quad fullscreen -> 1 upload + 1 draw.
 *
 * W-18: en modo PIXEL la textura que se sube son los INDICES tal cual
 * (LUMINANCE, 1 byte por celda) y la paleta viaja como textura 256x1 RGBA; el
 * lookup lo hace el fragment shader. La CPU deja de convertir indice->RGBA y la
 * subida por frame cae a la cuarta parte (2,07 MB en vez de 8,3 MB a 1920);
 * ademas no se reserva el buffer RGBA residente.
 *
 * W-19: la reconstruccion es explicita. `nearest` es 1 tap, identico a antes.
 * `soft` toma 4 taps NEAREST SOBRE LOS INDICES, hace 4 lookups de paleta y
 * mezcla los COLORES resultantes. Interpolar indices esta prohibido: el indice
 * 100 entre el 99 y el 101 no tiene ninguna relacion de color con ellos, por eso
 * la textura de indices nunca se filtra con LINEAR. Para que la mezcla sirva de
 * algo, en `soft` el backing store crece hasta el tamano de presentacion (ahi es
 * donde ocurre el estirado real); en `nearest` sigue siendo cols x rows y el
 * zoom lo hace el compositor, exactamente como antes.
 *
 * Fallbacks (NO negociables): si el camino indexado no esta disponible -modo no
 * PIXEL, shader que no compila, LUMINANCE rechazado por el driver- se conserva
 * ENTERO el camino RGBA anterior. Y si getContext('webgl') devuelve null,
 * init() retorna false y el caller cae a Canvas2D sin romper nada.
 */
(function (root) {
  "use strict";

  var MODE_PIXEL = 3;

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

  /* Los 256 niveles de indice necesitan pasos de 1/255: mediump (~2^-10) entra
     justo, sin margen. Se pide highp cuando el compilador lo declara. */
  var PRECISION = [
    "#ifdef GL_FRAGMENT_PRECISION_HIGH",
    "precision highp float;",
    "#else",
    "precision mediump float;",
    "#endif"
  ].join("\n");

  /* 255/256 y medio texel: sin la correccion de medio texel el lookup cae en el
     borde entre dos entradas y los colores salen corridos una posicion. */
  var PAL_LOOKUP = [
    "uniform sampler2D u_idx;",
    "uniform sampler2D u_pal;",
    "vec4 palLookup(vec2 uv){",
    "  float idx = texture2D(u_idx, uv).r;",
    "  return texture2D(u_pal, vec2(idx * 0.99609375 + 0.001953125, 0.5));",
    "}"
  ].join("\n");

  var FRAG_INDEX_NEAREST = [
    PRECISION,
    "varying vec2 v_uv;",
    PAL_LOOKUP,
    "void main(){ gl_FragColor = palLookup(v_uv); }"
  ].join("\n");

  /* 4 taps sobre indices + 4 lookups + mezcla en espacio de color. */
  var FRAG_INDEX_SOFT = [
    PRECISION,
    "varying vec2 v_uv;",
    "uniform vec2 u_size;",
    PAL_LOOKUP,
    "void main(){",
    "  vec2 p = v_uv * u_size - 0.5;",
    "  vec2 f = fract(p);",
    "  vec2 b = (floor(p) + 0.5) / u_size;",
    "  vec2 d = 1.0 / u_size;",
    "  vec4 c00 = palLookup(b);",
    "  vec4 c10 = palLookup(vec2(b.x + d.x, b.y));",
    "  vec4 c01 = palLookup(vec2(b.x, b.y + d.y));",
    "  vec4 c11 = palLookup(b + d);",
    "  gl_FragColor = mix(mix(c00, c10, f.x), mix(c01, c11, f.x), f.y);",
    "}"
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

  /* Compila, linkea y deja el quad atado. Cada programa guarda sus uniforms
     resueltos: cambiar de reconstruccion no vuelve a consultarlos. */
  WebGLRenderer.prototype._buildProgram = function (fragSrc) {
    var gl = this.gl, prog = gl.createProgram(), entry, loc;
    entry = {
      prog: prog,
      vs: compile(gl, gl.VERTEX_SHADER, VERT),
      fs: compile(gl, gl.FRAGMENT_SHADER, fragSrc)
    };
    gl.attachShader(prog, entry.vs);
    gl.attachShader(prog, entry.fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error("link: " + gl.getProgramInfoLog(prog));
    }
    gl.useProgram(prog);
    loc = gl.getAttribLocation(prog, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    entry.attrib = loc;
    entry.uTex = gl.getUniformLocation(prog, "u_tex");
    entry.uIdx = gl.getUniformLocation(prog, "u_idx");
    entry.uPal = gl.getUniformLocation(prog, "u_pal");
    entry.uSize = gl.getUniformLocation(prog, "u_size");
    this._programs.push(entry);
    return entry;
  };

  WebGLRenderer.prototype._activate = function (entry) {
    var gl = this.gl;
    this.active = entry;
    gl.useProgram(entry.prog);
    gl.enableVertexAttribArray(entry.attrib);
    gl.vertexAttribPointer(entry.attrib, 2, gl.FLOAT, false, 0, 0);
    /* Una location valida puede ser 0 en un doble de prueba: se compara contra
       null/undefined, nunca por veracidad. */
    if (entry.uTex !== null && entry.uTex !== undefined) { gl.uniform1i(entry.uTex, 0); }
    if (entry.uIdx !== null && entry.uIdx !== undefined) { gl.uniform1i(entry.uIdx, 0); }
    if (entry.uPal !== null && entry.uPal !== undefined) { gl.uniform1i(entry.uPal, 1); }
    if (entry.uSize !== null && entry.uSize !== undefined &&
        typeof gl.uniform2f === "function") {
      gl.uniform2f(entry.uSize, this.texW, this.texH);
    }
  };

  /* El camino indexado necesita un reader que exponga un byte por celda. */
  function indexable(reader) {
    return !!(reader && reader.header && reader.header.mode === MODE_PIXEL &&
      reader.cells && typeof reader.cells.length === "number" &&
      reader.cells.length === reader.n && reader.palette);
  }

  WebGLRenderer.prototype._initIndexed = function (reader) {
    var gl = this.gl, probe;
    if (!indexable(reader)) return false;
    if (gl.LUMINANCE === undefined || typeof gl.pixelStorei !== "function") return false;
    try {
      this.progNearest = this._buildProgram(FRAG_INDEX_NEAREST);
    } catch (shaderError) {
      return false;
    }
    this.palTex = gl.createTexture();
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE1); }
    gl.bindTexture(gl.TEXTURE_2D, this.palTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    /* El default de UNPACK_ALIGNMENT es 4: una textura de 1 byte por texel con
       ancho no multiplo de 4 se subiria corrida fila a fila. La directiva del
       operador es que el front acepte cualquier resolucion, asi que esto no es
       opcional aunque 1280 y 1920 sean multiplos de 4. */
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    /* Sonda barata: si el driver no acepta LUMINANCE, mejor saberlo ahora que
       con la textura del video ya reservada. */
    if (typeof gl.getError === "function") {
      try { gl.getError(); } catch (ignoredOld) {}
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, 2, 2, 0,
                    gl.LUMINANCE, gl.UNSIGNED_BYTE, new Uint8Array(4));
      probe = 0;
      try { probe = gl.getError(); } catch (ignoredProbe) { probe = 0; }
      if (probe !== 0 && probe !== gl.NO_ERROR) { return false; }
    }
    this.palRGBA = new Uint8Array(1024);
    this._palSource = null;
    return true;
  };

  WebGLRenderer.prototype._initRgba = function (reader) {
    this.progRgba = this._buildProgram(FRAG);
    this.rgba = new Uint8Array(reader.n * 4);
  };

  WebGLRenderer.prototype.init = function (reader, cellPx, reconstruction) {
    var h = reader.header;
    var gl = getContext(this.canvas);
    if (!gl) return false;                 // <-- degradacion elegante a Canvas2D
    this.gl = gl;

    // Evita pedir una textura imposible (y potenciales OOM) antes de reservar RGBA.
    // WebViews incompletos que no exponen la consulta conservan el comportamiento ES5.
    this.maxTexture = 0;
    try {
      if (gl.MAX_TEXTURE_SIZE !== undefined && typeof gl.getParameter === "function") {
        var maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE);
        if (typeof maxTextureSize === "number" && maxTextureSize > 0) {
          this.maxTexture = maxTextureSize;
          if (h.cols > maxTextureSize || h.rows > maxTextureSize) {
            this.dispose(true);
            return false;
          }
        }
      }
    } catch (sizeError) {}
    this.reader = reader;
    this.cellPx = cellPx || (h.mode === MODE_PIXEL ? 4 : 8);
    this.texW = h.cols; this.texH = h.rows;
    this._programs = [];
    this._presW = 0; this._presH = 0;
    this.reconstruction = reconstructionName(reconstruction);
    if (h.mode === MODE_PIXEL) {
      this.canvas.width = h.cols;
      this.canvas.height = h.rows;
      this.canvas.style.width = (h.cols * this.cellPx) + "px";
      this.canvas.style.height = "auto";
    } else {
      this.canvas.width = h.cols * this.cellPx;
      this.canvas.height = h.rows * this.cellPx;
    }
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);

    var buf = gl.createBuffer();
    this.buf = buf;
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1, -1,  1, -1,  -1, 1,   -1, 1,  1, -1,  1, 1
    ]), gl.STATIC_DRAW);

    this.tex = gl.createTexture();
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    this.rgba = null;
    this.indexed = this._initIndexed(reader);
    if (!this.indexed) { this._initRgba(reader); }

    this._texInit = false;
    this._fullUploadChecked = false;
    this._subRGBA = null; this._subY0 = -1; this._subY1 = -1;
    this._subUploadSupported = null;
    this.setReconstruction(this.reconstruction);
    return true;
  };

  /* W-19: el backing store solo crece en `soft` indexado, que es donde la
     mezcla de 4 taps tiene sentido (si el framebuffer midiera lo mismo que la
     grilla, cada fragmento caeria justo en el centro de un texel y la mezcla
     seria un no-op). En `nearest` se conserva cols x rows, bit a bit como antes. */
  WebGLRenderer.prototype._targetSize = function () {
    var w = this.texW, h = this.texH, cap = this.maxTexture > 0 ? this.maxTexture : 4096;
    if (this.indexed && this.reconstruction === "soft" && this._presW > 0 && this._presH > 0) {
      w = this._presW; h = this._presH;
      if (w > cap) { w = cap; }
      if (h > cap) { h = cap; }
      if (w < this.texW || h < this.texH) { w = this.texW; h = this.texH; }
    }
    return { width: Math.round(w), height: Math.round(h) };
  };

  WebGLRenderer.prototype._applySize = function () {
    var size, changed = false;
    /* Solo PIXEL: en PAL/RGB el backing store es cols*cellPx y no lo toca nadie. */
    if (!this.reader || this.reader.header.mode !== MODE_PIXEL) return false;
    size = this._targetSize();
    if (this.canvas.width !== size.width || this.canvas.height !== size.height) {
      this.canvas.width = size.width;
      this.canvas.height = size.height;
      changed = true;
    }
    this.gl.viewport(0, 0, size.width, size.height);
    return changed;
  };

  /* La informa el player despues de acomodar el canvas (CSS). Devuelve true si
     el backing store cambio: el caller tiene que volver a presentar, porque
     redimensionarlo lo deja en blanco. */
  WebGLRenderer.prototype.setPresentationSize = function (width, height) {
    width = Math.round(Number(width) || 0);
    height = Math.round(Number(height) || 0);
    if (width <= 0 || height <= 0) return false;
    if (width === this._presW && height === this._presH) return false;
    this._presW = width; this._presH = height;
    return this._applySize();
  };

  WebGLRenderer.prototype.setReconstruction = function (reconstruction) {
    var gl = this.gl, filter, entry;
    this.reconstruction = reconstructionName(reconstruction);
    setCanvasImageRendering(this.canvas, this.reconstruction);
    if (!gl) return;
    if (this.indexed) {
      /* La textura de INDICES nunca se filtra: interpolar indices produce
         colores arbitrarios. El suavizado, si se pide, lo hace el shader. */
      if (this.reconstruction === "soft") {
        if (!this.progSoft) {
          try { this.progSoft = this._buildProgram(FRAG_INDEX_SOFT); }
          catch (softError) { this.progSoft = null; }
        }
        entry = this.progSoft || this.progNearest;
      } else {
        entry = this.progNearest;
      }
      this._activate(entry);
      if (this.tex) {
        if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
        gl.bindTexture(gl.TEXTURE_2D, this.tex);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      }
      this._applySize();
      return;
    }
    if (this.progRgba) { this._activate(this.progRgba); }
    if (this.tex) {
      filter = this.reconstruction === "soft" ? gl.LINEAR : gl.NEAREST;
      gl.bindTexture(gl.TEXTURE_2D, this.tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    }
  };

  /* La paleta se re-sube solo cuando cambia (1 KB). Igual que la LUT de W-17,
     la identidad del objeto alcanza: las paletas son subvistas inmutables. */
  WebGLRenderer.prototype._uploadPalette = function (reader) {
    var gl = this.gl, pal = reader.palette, out = this.palRGBA, count, i;
    if (!pal || pal === this._palSource) return;
    count = Math.floor(pal.length / 3);
    if (count > 256) count = 256;
    for (i = 0; i < count; i++) {
      out[i * 4] = pal[i * 3];
      out[i * 4 + 1] = pal[i * 3 + 1];
      out[i * 4 + 2] = pal[i * 3 + 2];
      out[i * 4 + 3] = 255;
    }
    for (i = count; i < 256; i++) {
      out[i * 4] = 0; out[i * 4 + 1] = 0; out[i * 4 + 2] = 0; out[i * 4 + 3] = 255;
    }
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE1); }
    gl.bindTexture(gl.TEXTURE_2D, this.palTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, out);
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    this._palSource = pal;
  };

  /* Si la primera subida indexada falla, se abandona el camino indexado y se
     arma el RGBA anterior: el fallback conserva la reproduccion, no la corta. */
  WebGLRenderer.prototype._downgradeToRgba = function (reader) {
    var gl = this.gl;
    this.indexed = false;
    this._palSource = null;
    this.palRGBA = null;
    if (this.palTex) {
      try { if (gl.deleteTexture) { gl.deleteTexture(this.palTex); } } catch (ignoredPal) {}
      this.palTex = null;
    }
    if (!this.progRgba) { this._initRgba(reader); }
    else if (!this.rgba) { this.rgba = new Uint8Array(reader.n * 4); }
    this._texInit = false;
    this._subRGBA = null; this._subY0 = -1; this._subY1 = -1;
    this.setReconstruction(this.reconstruction);
  };

  WebGLRenderer.prototype._drawIndexed = function (reader, full, y0, y1) {
    var gl = this.gl, hh, probeFull, code = 0, cells = reader.cells;
    this._uploadPalette(reader);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    if (full) {
      probeFull = !this._fullUploadChecked && typeof gl.getError === "function";
      if (probeFull) {
        try { gl.getError(); } catch (ignoredBefore) { probeFull = false; }
      }
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, this.texW, this.texH, 0,
                    gl.LUMINANCE, gl.UNSIGNED_BYTE, cells);
      if (probeFull) {
        try { code = gl.getError(); } catch (ignoredProbe) { code = 0; }
        if (code !== 0 && code !== gl.NO_ERROR) {
          this._downgradeToRgba(reader);
          return false;
        }
      }
      this._fullUploadChecked = true;
      this._texInit = true;
      return true;
    }
    hh = y1 - y0 + 1;
    /* subarray es una vista del propio `cells`: no copia la banda ni reserva
       nada por cuadro (invariante 7). */
    if (!this._subCells || this._subY0 !== y0 || this._subY1 !== y1) {
      this._subCells = cells.subarray(y0 * this.texW, (y1 + 1) * this.texW);
      this._subY0 = y0; this._subY1 = y1;
    }
    if (this._subUploadSupported === false) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, this.texW, this.texH, 0,
                    gl.LUMINANCE, gl.UNSIGNED_BYTE, cells);
      return true;
    }
    var firstProbe = this._subUploadSupported === null;
    var canProbe = firstProbe && typeof gl.getError === "function";
    var failed = false;
    if (canProbe) {
      try { gl.getError(); } catch (ignoredOldSub) { canProbe = false; }
    }
    try {
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, y0, this.texW, hh,
                       gl.LUMINANCE, gl.UNSIGNED_BYTE, this._subCells);
    } catch (subError) { failed = true; }
    if (!failed && canProbe) {
      try { code = gl.getError(); } catch (ignoredSubProbe) { code = 0; }
      if (code !== 0 && code !== gl.NO_ERROR) { failed = true; }
    }
    if (failed) {
      this._subUploadSupported = false;
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.LUMINANCE, this.texW, this.texH, 0,
                    gl.LUMINANCE, gl.UNSIGNED_BYTE, cells);
    } else if (firstProbe) {
      this._subUploadSupported = true;
    }
    return true;
  };

  WebGLRenderer.prototype._drawRgba = function (reader, full, y0, y1) {
    var gl = this.gl;
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
      return;
    }
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
      return;
    }
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
    if (!this.indexed && !full && typeof reader.fillRGBAChanged !== "function" &&
        typeof reader.fillRGBARows !== "function") full = true;
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
    gl.bindTexture(gl.TEXTURE_2D, this.tex);

    // Primer cuadro, keyframe/cambio de paleta, metadata dirty no confiable o lector
    // anterior: conversion y subida completas como fallback seguro.
    if (this.indexed) {
      if (!this._drawIndexed(reader, full, y0, y1)) {
        /* El camino indexado se cayo a RGBA en el medio del cuadro: se rehace
           completo por el camino nuevo para no dibujar una textura a medias. */
        this._drawRgba(reader, true, 0, this.texH - 1);
      }
    } else if (full || y1 >= y0) {
      this._drawRgba(reader, full, y0, y1);
    }
    gl.drawArrays(gl.TRIANGLES, 0, 6);
  };

  /* Vuelve a dibujar lo que ya esta en la textura, sin subir nada. Lo usa el
     player cuando el backing store cambio de tamano (queda en blanco). */
  WebGLRenderer.prototype.present = function () {
    var gl = this.gl;
    if (!gl || !this._texInit) return false;
    if (typeof gl.activeTexture === "function") { gl.activeTexture(gl.TEXTURE0); }
    gl.bindTexture(gl.TEXTURE_2D, this.tex);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    return true;
  };

  WebGLRenderer.prototype.dispose = function (releaseContext) {
    var gl = this.gl, extension = null, list = this._programs || [], i;
    if (gl) {
      try { if (this.tex && gl.deleteTexture) { gl.deleteTexture(this.tex); } } catch (ignoredTexture) {}
      try { if (this.palTex && gl.deleteTexture) { gl.deleteTexture(this.palTex); } } catch (ignoredPalTex) {}
      try { if (this.buf && gl.deleteBuffer) { gl.deleteBuffer(this.buf); } } catch (ignoredBuffer) {}
      for (i = 0; i < list.length; i++) {
        try { if (gl.deleteProgram) { gl.deleteProgram(list[i].prog); } } catch (ignoredProgram) {}
        try {
          if (gl.deleteShader) { gl.deleteShader(list[i].vs); gl.deleteShader(list[i].fs); }
        } catch (ignoredShader) {}
      }
      if (releaseContext && typeof gl.getExtension === "function") {
        try { extension = gl.getExtension("WEBGL_lose_context"); } catch (ignoredExtension) {}
        try { if (extension && extension.loseContext) { extension.loseContext(); } } catch (ignoredLoss) {}
      }
    }
    this.gl = null; this.reader = null; this.canvas = null;
    this.tex = null; this.palTex = null; this.buf = null;
    this._programs = []; this.active = null;
    this.progRgba = null; this.progNearest = null; this.progSoft = null;
    this.rgba = null; this._subRGBA = null; this._subCells = null;
    this.palRGBA = null; this._palSource = null;
    this.indexed = false;
    this._texInit = false; this._fullUploadChecked = false;
    this._subUploadSupported = null;
  };

  root.WebGLRenderer = WebGLRenderer;
})(typeof window !== "undefined" ? window : this);
