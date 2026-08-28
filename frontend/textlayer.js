/*
 * textlayer.js - INT-004: texto nativo sobre el MISMO canvas del video.
 *
 * Los textos NO viven en la matriz de celdas: se dibujan con la API de texto
 * de Canvas2D (strokeText/fillText) despues de pintar el frame, a resolucion
 * de pantalla, con cualquier fuente y borde (DISENO-PARCHES-GENERICOS §10).
 * Sigue habiendo UN solo elemento canvas; cuando hay textos declarados el
 * renderer debe ser Canvas2D (regla 6: WebGL solo acelera, nunca agrega
 * funcion). El texto no es byte-verificable en cells: propiedad documentada.
 *
 * API:
 *   ASCILINETextLayer.create(items) -> capa | null   (todo-o-nada)
 *     item: { id, x, y, w, h,        caja en CELDAS (x,y,w,h enteros)
 *             size,                  altura del texto en celdas (0 < size <= h)
 *             color,                 relleno CSS
 *             outline,               borde CSS u omitido (sin borde)
 *             font,                  familia (default "sans-serif")
 *             align,                 "left" | "center" | "right" (default center)
 *             text }                 texto inicial (default "")
 *   capa.setText(id, str) -> bool    valida; false conserva el estado (INV-7)
 *   capa.markDirty(reader) -> n      marca via markRectDirty las cajas CON
 *                                    texto que entran en la grilla (el video
 *                                    se repinta debajo antes del redibujo)
 *   capa.draw(ctx, cellPx)           borde y luego relleno, por item con texto
 *
 * Sin allocaciones en el camino caliente: los strings de fuente y los anclajes
 * en pixeles se cachean por item y se reconstruyen solo cuando cambia cellPx.
 */
(function (root) {
  "use strict";

  var MAX_ITEMS = 64;
  var MAX_ID = 32;
  var MAX_TEXT = 64;
  var MAX_STYLE = 64;
  var MAX_FONT = 128;

  function isCleanString(value, maxLength) {
    var i;
    if (typeof value !== "string" || value.length === 0 ||
        value.length > maxLength) {
      return false;
    }
    for (i = 0; i < value.length; i++) {
      if (value.charCodeAt(i) < 32) return false;
    }
    return true;
  }

  /* "" es valido (borra el texto); el resto como isCleanString. */
  function isValidText(value) {
    return value === "" || isCleanString(value, MAX_TEXT);
  }

  function isValidId(value) {
    if (isCleanString(value, MAX_ID)) return true;
    return typeof value === "number" && isFinite(value) &&
      value === Math.floor(value) && value >= 0;
  }

  function isCellInt(value, minimum) {
    return typeof value === "number" && isFinite(value) &&
      value === Math.floor(value) && value >= minimum && value <= 65535;
  }

  function TextLayer(items) {
    var n = items.length, i, item;
    this.count = n;
    this._x = new Uint16Array(n);
    this._y = new Uint16Array(n);
    this._w = new Uint16Array(n);
    this._h = new Uint16Array(n);
    this._size = new Float64Array(n);
    this._color = [];
    this._outline = [];
    this._font = [];
    this._align = [];
    this._text = [];
    this._index = {};
    /* cache por item, valido mientras cellPx no cambie */
    this._pxFor = new Float64Array(n);   /* 0 = sin construir */
    this._fontStr = [];
    this._lineW = new Float64Array(n);
    this._ax = new Float64Array(n);
    this._ay = new Float64Array(n);
    this._maxW = new Float64Array(n);
    for (i = 0; i < n; i++) {
      item = items[i];
      this._x[i] = item.x;
      this._y[i] = item.y;
      this._w[i] = item.w;
      this._h[i] = item.h;
      this._size[i] = item.size;
      this._color[i] = item.color;
      this._outline[i] = item.outline;
      this._font[i] = item.font;
      this._align[i] = item.align;
      this._text[i] = item.text;
      this._index["t" + item.id] = i;
      this._fontStr[i] = "";
    }
  }

  /* Valida y devuelve true; ante cualquier entrada invalida devuelve false y
   * conserva el ultimo texto valido (INV-7: un fallo de datos nunca
   * interrumpe la reproduccion). */
  TextLayer.prototype.setText = function (id, str) {
    var key = "t" + id, i;
    if (!Object.prototype.hasOwnProperty.call(this._index, key)) return false;
    if (!isValidText(str)) return false;
    i = this._index[key];
    this._text[i] = str;
    return true;
  };

  /* Marca sucias las cajas de los items CON texto que entran en la grilla del
   * reader, para que el video se repinte debajo antes de redibujar el texto.
   * Una caja fuera de grilla se saltea (no lanza: INV-7). Devuelve cuantas
   * cajas marco. */
  TextLayer.prototype.markDirty = function (reader) {
    var marked = 0, cols, rows, i;
    if (!reader || !reader.header ||
        typeof reader.markRectDirty !== "function") {
      return 0;
    }
    cols = reader.header.cols;
    rows = reader.header.rows;
    for (i = 0; i < this.count; i++) {
      if (this._text[i].length === 0) continue;
      if (this._x[i] + this._w[i] > cols ||
          this._y[i] + this._h[i] > rows) {
        continue;
      }
      reader.markRectDirty(this._x[i], this._y[i], this._w[i], this._h[i]);
      marked++;
    }
    return marked;
  };

  /* Pinta cada item con texto: primero el borde (strokeText), despues el
   * relleno (fillText), ambos limitados al ancho de la caja (maxWidth) para
   * no salirse del rect marcado sucio. cellPx es el lado de la celda en
   * pixeles del canvas. */
  TextLayer.prototype.draw = function (ctx, cellPx) {
    var i, sizePx;
    if (!ctx || typeof cellPx !== "number" || !isFinite(cellPx) ||
        cellPx <= 0) {
      return;
    }
    for (i = 0; i < this.count; i++) {
      if (this._text[i].length === 0) continue;
      if (this._pxFor[i] !== cellPx) {
        sizePx = this._size[i] * cellPx;
        this._fontStr[i] = sizePx + "px " + this._font[i];
        this._lineW[i] = Math.max(1, sizePx / 8);
        if (this._align[i] === "left") {
          this._ax[i] = this._x[i] * cellPx;
        } else if (this._align[i] === "right") {
          this._ax[i] = (this._x[i] + this._w[i]) * cellPx;
        } else {
          this._ax[i] = (this._x[i] + this._w[i] / 2) * cellPx;
        }
        this._ay[i] = (this._y[i] + this._h[i] / 2) * cellPx;
        this._maxW[i] = this._w[i] * cellPx;
        this._pxFor[i] = cellPx;
      }
      ctx.font = this._fontStr[i];
      ctx.textAlign = this._align[i];
      ctx.textBaseline = "middle";
      if (this._outline[i] !== null) {
        ctx.lineJoin = "round";
        ctx.lineWidth = this._lineW[i];
        ctx.strokeStyle = this._outline[i];
        ctx.strokeText(this._text[i], this._ax[i], this._ay[i],
                       this._maxW[i]);
      }
      ctx.fillStyle = this._color[i];
      ctx.fillText(this._text[i], this._ax[i], this._ay[i], this._maxW[i]);
    }
  };

  /* Todo-o-nada: si UN item es invalido no se crea nada (contrato del
   * runbook §4-INT-004). Devuelve la capa o null; no lanza. */
  function create(items) {
    var seen = {}, normalized = [], i, item, copy, key;
    if (!items || typeof items.length !== "number" ||
        items.length < 1 || items.length > MAX_ITEMS ||
        items.length !== Math.floor(items.length)) {
      return null;
    }
    for (i = 0; i < items.length; i++) {
      item = items[i];
      if (!item || typeof item !== "object") return null;
      if (!isValidId(item.id)) return null;
      key = "t" + item.id;
      if (Object.prototype.hasOwnProperty.call(seen, key)) return null;
      seen[key] = true;
      if (!isCellInt(item.x, 0) || !isCellInt(item.y, 0) ||
          !isCellInt(item.w, 1) || !isCellInt(item.h, 1)) {
        return null;
      }
      if (typeof item.size !== "number" || !isFinite(item.size) ||
          item.size <= 0 || item.size > item.h) {
        return null;
      }
      if (!isCleanString(item.color, MAX_STYLE)) return null;
      if (item.outline !== undefined && item.outline !== null &&
          !isCleanString(item.outline, MAX_STYLE)) {
        return null;
      }
      if (item.font !== undefined &&
          !isCleanString(item.font, MAX_FONT)) {
        return null;
      }
      if (item.align !== undefined && item.align !== "left" &&
          item.align !== "center" && item.align !== "right") {
        return null;
      }
      if (item.text !== undefined && !isValidText(item.text)) return null;
      copy = {
        id: item.id,
        x: item.x, y: item.y, w: item.w, h: item.h,
        size: item.size,
        color: item.color,
        outline: (item.outline === undefined || item.outline === null)
          ? null : item.outline,
        font: item.font === undefined ? "sans-serif" : item.font,
        align: item.align === undefined ? "center" : item.align,
        text: item.text === undefined ? "" : item.text
      };
      normalized.push(copy);
    }
    return new TextLayer(normalized);
  }

  root.ASCILINETextLayer = { create: create };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { create: create };
  }
})(typeof window !== "undefined" ? window : this);
