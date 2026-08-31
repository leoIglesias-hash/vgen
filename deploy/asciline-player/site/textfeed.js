/*
 * textfeed.js - INT-006: alimentar campos de texto nativo SIN sidecar.
 *
 * Adapta una capa de texto (textlayer.js) a la interfaz que consume
 * datachannel.js (digitCount + setValues), para que el canal de datos y el
 * boton de carga simulada funcionen igual con o sin overlay de matriz.
 * datachannel.js no se toca: para el canal, el feed ES un overlay.
 *
 * API:
 *   ASCILINETextFeed.create(capa, campos) -> feed | null
 *     capa:   objeto con setText(id, str) -> bool (una capa de textlayer.js)
 *     campo:  { id, width }  id declarado en la capa; width en digitos (1..16)
 *   feed.digitCount          suma de los anchos, en orden de declaracion
 *   feed.setValues(digits) -> bool
 *     todo-numerico (0x30..0x39), longitud EXACTA digitCount, todo-o-nada:
 *     se valida el payload completo antes de escribir un solo campo; un
 *     payload invalido devuelve false y conserva el estado (INV-7).
 *
 * create() verifica cada id escribiendo "" en la capa (setText con texto
 * vacio es la operacion de borrado, siempre valida para un id declarado):
 * los campos del feed arrancan VACIOS de forma determinista. Si un id no
 * existe en la capa devuelve null (todo-o-nada del contrato; los campos ya
 * probados quedan vacios, y sin feed el modo standalone no arranca: INV-7).
 */
(function (root) {
  "use strict";

  var MAX_FIELDS = 64;   /* mismo techo que MAX_ITEMS de textlayer.js */
  var MAX_WIDTH = 16;
  var MAX_ID = 32;

  function isValidId(value) {
    var i;
    if (typeof value === "number") {
      return isFinite(value) && value === Math.floor(value) && value >= 0;
    }
    if (typeof value !== "string" || value.length === 0 ||
        value.length > MAX_ID) {
      return false;
    }
    for (i = 0; i < value.length; i++) {
      if (value.charCodeAt(i) < 32) return false;
    }
    return true;
  }

  function Feed(capa, fields, total) {
    this._capa = capa;
    this._ids = [];
    this._widths = [];
    this.digitCount = total;
    var i;
    for (i = 0; i < fields.length; i++) {
      this._ids[i] = fields[i].id;
      this._widths[i] = fields[i].width;
    }
  }

  /* Todo-o-nada: la validacion completa (tipo, longitud exacta, solo digitos
   * ASCII) ocurre ANTES de la primera escritura; las escrituras no pueden
   * fallar (ids probados en create, tramos de digitos siempre validos para
   * setText). false conserva el ultimo estado valido (INV-7). */
  Feed.prototype.setValues = function (digits) {
    var i, c, off;
    if (typeof digits !== "string" || digits.length !== this.digitCount) {
      return false;
    }
    for (i = 0; i < digits.length; i++) {
      c = digits.charCodeAt(i);
      if (c < 48 || c > 57) return false;
    }
    off = 0;
    for (i = 0; i < this._ids.length; i++) {
      this._capa.setText(this._ids[i], digits.substr(off, this._widths[i]));
      off += this._widths[i];
    }
    return true;
  };

  /* Devuelve el feed o null; no lanza (mismo contrato que
   * ASCILINEOverlay.attach y ASCILINETextLayer.create). */
  function create(capa, campos) {
    var seen = {}, total = 0, i, campo, key;
    if (!capa || typeof capa.setText !== "function") return null;
    if (!campos || typeof campos.length !== "number" ||
        campos.length < 1 || campos.length > MAX_FIELDS ||
        campos.length !== Math.floor(campos.length)) {
      return null;
    }
    for (i = 0; i < campos.length; i++) {
      campo = campos[i];
      if (!campo || typeof campo !== "object") return null;
      if (!isValidId(campo.id)) return null;
      key = "t" + campo.id;
      if (Object.prototype.hasOwnProperty.call(seen, key)) return null;
      seen[key] = true;
      if (typeof campo.width !== "number" || !isFinite(campo.width) ||
          campo.width !== Math.floor(campo.width) ||
          campo.width < 1 || campo.width > MAX_WIDTH) {
        return null;
      }
      total += campo.width;
    }
    /* la forma ya es valida: probar los ids contra la capa (y dejar los
     * campos declarados vacios, estado inicial determinista) */
    for (i = 0; i < campos.length; i++) {
      if (!capa.setText(campos[i].id, "")) return null;
    }
    return new Feed(capa, campos, total);
  }

  root.ASCILINETextFeed = { create: create };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { create: create };
  }
})(typeof window !== "undefined" ? window : this);
