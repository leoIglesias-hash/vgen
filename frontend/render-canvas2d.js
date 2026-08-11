/*
 * render-canvas2d.js - Renderer fallback Canvas 2D (ES5). Red de seguridad universal.
 *
 * - PIXEL: el backing store queda en cols x rows. El zoom es solo visual (CSS), con
 *   reconstruccion NEAREST o SOFT seleccionable sin multiplicar la RAM del canvas.
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
      this.canvas.width = h.cols;
      this.canvas.height = h.rows;
      this.canvas.style.width = (h.cols * this.cellPx) + "px";
      this.canvas.style.height = "auto";
      this.imgData = this.ctx.createImageData(h.cols, h.rows);
      this.rgba = this.imgData.data;
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

  Canvas2DRenderer.prototype.setReconstruction = function (reconstruction) {
    this.reconstruction = reconstructionName(reconstruction);
    setSmoothing(this.ctx, this.reconstruction === "soft");
    setCanvasImageRendering(this.canvas, this.reconstruction);
  };

  Canvas2DRenderer.prototype.draw = function (reader) {
    var h = reader.header;
    if (h.mode === MODE_PIXEL) {
      reader.fillRGBA(this.rgba);
      this.ctx.putImageData(this.imgData, 0, 0);
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

  root.Canvas2DRenderer = Canvas2DRenderer;
})(typeof window !== "undefined" ? window : this);
