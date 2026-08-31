/*
 * render-canvas2d.js - Renderer fallback Canvas 2D (ES5). Red de seguridad universal.
 *
 * - PIXEL: el backing store queda en cols x rows. El zoom es solo visual (CSS), con
 *   reconstruccion NEAREST o SOFT seleccionable sin multiplicar la RAM del canvas.
 * - PIXEL + texto nativo (INT-004): si el player fija renderer.pixelScale = s (entero
 *   >= 2) ANTES de init, el backing store pasa a cols*s x rows*s para que el texto de
 *   textlayer.js se dibuje nitido a esa resolucion. El frame se escribe chico con
 *   putImageData y se escala con UN drawImage del canvas sobre si mismo (la spec
 *   exige snapshot del origen: no hace falta un segundo canvas). Con pixelScale el
 *   put es siempre completo: el blit anterior piso la esquina y el texto pudo pisar
 *   cualquier region. Con pixelScale 1 (default) el comportamiento es identico al
 *   historico, byte a byte.
 * - ASCII (BW/PAL/RGB): dibuja glifos reales con fillText y fuente monoespaciada (D2,
 *   ruta universal). Suficiente hasta ~150 columnas.
 *
 * Siempre disponible: no requiere WebGL.
 */
(function (root) {
  "use strict";
  var MODE_BW = 0, MODE_PAL = 1, MODE_RGB = 2, MODE_PIXEL = 3;

  function reconstructionName(value) {
    return value === "soft" ? "soft" : "nearest";
  }

  function setSmoothing(ctx, enabled) {
    ctx.imageSmoothingEnabled = enabled;
    ctx.mozImageSmoothingEnabled = enabled;
    ctx.webkitImageSmoothingEnabled = enabled;
    ctx.msImageSmoothingEnabled = enabled;
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

  function Canvas2DRenderer(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.imgData = null; this.rgba = null;
    this._imageInit = false;
    this._dirtyPutSupported = null;
    this.name = "canvas2d";
  }

  Canvas2DRenderer.prototype.init = function (reader, cellPx, reconstruction) {
    var h = reader.header;
    this.reader = reader;
    this.cellPx = cellPx || (h.mode === MODE_PIXEL ? 4 : 8);
    if (h.mode === MODE_PIXEL || h.mode === MODE_RGB || h.mode === MODE_PAL) {
      this.glyphs = (h.mode !== MODE_PIXEL); // color modes: por defecto glifos en ASCII
    }
    if (h.mode === MODE_PIXEL) {
      this.pixelScale = (typeof this.pixelScale === "number" &&
        isFinite(this.pixelScale) &&
        this.pixelScale === Math.floor(this.pixelScale) &&
        this.pixelScale > 1) ? this.pixelScale : 1;
      this.canvas.width = h.cols * this.pixelScale;
      this.canvas.height = h.rows * this.pixelScale;
      this.canvas.style.width = (h.cols * this.cellPx) + "px";
      this.canvas.style.height = "auto";
      this.imgData = this.ctx.createImageData(h.cols, h.rows);
      this.rgba = this.imgData.data;
      this._imageInit = false;
      this._dirtyPutSupported = null;
    } else {
      // ASCII: tamaño de celda con correccion de aspecto
      this.cw = this.cellPx;
      this.ch = Math.round(this.cw / Math.max(0.1, h.charAspect));
      this.canvas.width = h.cols * this.cw;
      this.canvas.height = h.rows * this.ch;
      this.ctx.font = this.ch + "px monospace";
      this.ctx.textBaseline = "top";
    }
    this.setReconstruction(reconstruction);
    return true;
  };

  /* W-19: contraparte del contrato que usa WebGL. Canvas2D NO cambia su backing
   * store con el tamano de presentacion: su `soft` sigue siendo el remuestreo del
   * compositor (`image-rendering: auto`), que es la asimetria declarada entre
   * renderers. Devuelve false = el caller no necesita volver a presentar. */
  Canvas2DRenderer.prototype.setPresentationSize = function () { return false; };

  /* Re-emite el ultimo frame ya convertido, sin volver a leer del reader. */
  Canvas2DRenderer.prototype.present = function () {
    if (!this._imageInit || !this.imgData || !this.reader) return false;
    if (this.pixelScale > 1) { this._scaledPut(this.reader.header); }
    else { this.ctx.putImageData(this.imgData, 0, 0); }
    return true;
  };

  Canvas2DRenderer.prototype.setReconstruction = function (reconstruction) {
    this.reconstruction = reconstructionName(reconstruction);
    setSmoothing(this.ctx, this.reconstruction === "soft");
    setCanvasImageRendering(this.canvas, this.reconstruction);
  };

  Canvas2DRenderer.prototype.draw = function (reader) {
    var h = reader.header;
    if (h.mode === MODE_PIXEL) {
      var y0 = reader.dirtyY0, y1 = reader.dirtyY1;
      var dirtyKnown = typeof y0 === "number" && isFinite(y0) && Math.floor(y0) === y0 &&
                       typeof y1 === "number" && isFinite(y1) && Math.floor(y1) === y1;
      var empty = dirtyKnown && y0 === h.rows && y1 === -1;
      var dirtyValid = empty || (dirtyKnown && y0 >= 0 && y0 < h.rows &&
        y1 >= y0 && y1 < h.rows);
      var full = !this._imageInit || reader.dirtyFull || !dirtyKnown ||
                 !dirtyValid;
      var scale = this.pixelScale > 1 ? this.pixelScale : 1;

      // Solo rows/-1 es el sentinel acordado para un cuadro exactamente repetido.
      // Cualquier otro rango invertido o fuera del frame se trata como no confiable.
      // Con pixelScale > 1 un cuadro repetido igual se re-copia: el texto nativo
      // pudo pisar el canvas y el put chico + blit lo restauran completo.
      if (!full && empty && scale === 1) return;
      if (!full && !empty && typeof reader.fillRGBAChanged !== "function" &&
          typeof reader.fillRGBARows !== "function") full = true;

      // El primer cuadro, un keyframe/cambio de paleta o metadata dirty no confiable
      // reconstruyen todo. fillRGBA conserva compatibilidad con lectores anteriores.
      if (full) {
        reader.fillRGBA(this.rgba);
        if (scale > 1) {
          this._imageInit = true;
          this._scaledPut(h);
          return;
        }
        this.ctx.putImageData(this.imgData, 0, 0);
        this._imageInit = true;
      } else if (scale > 1) {
        // El RGBA persistente se mantiene incremental, pero la copia al canvas
        // es completa: el blit escalado del frame anterior ocupo el origen.
        if (!empty && y1 >= y0) {
          if (typeof reader.fillRGBAChanged === "function") {
            reader.fillRGBAChanged(this.rgba);
          } else {
            reader.fillRGBARows(this.rgba, y0, y1);
          }
        }
        this._scaledPut(h);
        return;
      } else if (y1 >= y0) {
        // ImageData y su backing RGBA se crean una sola vez. El reader nuevo
        // convierte celdas exactas; el fallback convierte la banda inclusiva.
        if (typeof reader.fillRGBAChanged === "function") {
          reader.fillRGBAChanged(this.rgba);
        } else {
          reader.fillRGBARows(this.rgba, y0, y1);
        }
        if (this._dirtyPutSupported === false) {
          this.ctx.putImageData(this.imgData, 0, 0);
        } else {
          try {
            this.ctx.putImageData(this.imgData, 0, 0, 0, y0, h.cols, y1 - y0 + 1);
            this._dirtyPutSupported = true;
          } catch (e) {
            // Algunos Canvas 2D antiguos exponen putImageData pero no sus 7 argumentos.
            // El buffer persistente ya contiene el frame correcto, por lo que el full
            // put es un fallback exacto y la excepcion no se repite en frames siguientes.
            this._dirtyPutSupported = false;
            this.ctx.putImageData(this.imgData, 0, 0);
          }
        }
      } // y1 < y0: cuadro repetido, no hay conversion ni escritura al canvas.
      return;
    }
    // ASCII con glifos
    var ctx = this.ctx, cols = h.cols, rows = h.rows, cw = this.cw, ch = this.ch;
    var ramp = reader.ramp, cells = reader.cells, pal = reader.palette, mode = h.mode;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.font = ch + "px monospace"; ctx.textBaseline = "top";
    var i = 0, r, c, ci, glyph, pi, rr, gg, bb;
    for (r = 0; r < rows; r++) {
      for (c = 0; c < cols; c++) {
        if (mode === MODE_PAL) { ci = cells[i*2]; pi = cells[i*2+1]*3; rr=pal[pi]; gg=pal[pi+1]; bb=pal[pi+2]; }
        else if (mode === MODE_RGB) { ci = cells[i*4]; rr=cells[i*4+1]; gg=cells[i*4+2]; bb=cells[i*4+3]; }
        else { ci = cells[i]; rr=gg=bb=Math.round(ci/Math.max(1,h.rampLen-1)*255); }
        i++;
        glyph = ramp.charAt(ci < ramp.length ? ci : ramp.length - 1);
        if (glyph === " " || glyph === "") continue;
        ctx.fillStyle = "rgb(" + rr + "," + gg + "," + bb + ")";
        ctx.fillText(glyph, c * cw, r * ch);
      }
    }
  };

  /* INT-004: frame chico al origen + blit escalado del canvas sobre si mismo
   * (drawImage snapshotea el origen por spec, el solape es seguro). */
  Canvas2DRenderer.prototype._scaledPut = function (h) {
    var s = this.pixelScale;
    this.ctx.putImageData(this.imgData, 0, 0);
    this.ctx.drawImage(this.canvas, 0, 0, h.cols, h.rows,
                       0, 0, h.cols * s, h.rows * s);
  };

  Canvas2DRenderer.prototype.dispose = function () {
    this.imgData = null;
    this.rgba = null;
    this.reader = null;
    this.ctx = null;
    this.canvas = null;
    this._imageInit = false;
  };

  root.Canvas2DRenderer = Canvas2DRenderer;
})(typeof window !== "undefined" ? window : this);
