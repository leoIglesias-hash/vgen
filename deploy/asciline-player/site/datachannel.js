/*
 * datachannel.js - F7-3: canal de datos en vivo del overlay (INT-001 §8).
 *
 * Consulta por XHR un recurso estatico diminuto de texto plano de longitud
 * fija (sin JSON): "<serial>|<digitos>\n", con serial de ocho digitos
 * decimales estrictamente creciente. Sin fetch, sin Promise, sin Worker.
 *
 * API:
 *   ASCILINEDataChannel.create(url, overlay, options) -> canal o null
 *   canal.start()  canal.stop()
 *
 * Validacion en cinco pasos (§8.3), antes de tocar un solo pixel:
 *   1. longitud exacta esperada (8 + 1 + digitos + 1) y forma fija;
 *   2. todos los caracteres de serial y digitos en 0x30..0x39;
 *   3. serial numerico estrictamente mayor al ultimo ACEPTADO;
 *   4. cada campo reconstruido dentro de [min, max] - lo hace
 *      overlay.setValues, todo o nada;
 *   5. indice de glifo charCodeAt-48: el paso 2 ya lo acota a 0..9, y
 *      setValues rechaza cualquier caracter fuera de ese rango.
 *
 * Ante cualquier fallo se conserva el ultimo estado valido y se registra el
 * motivo en canal.lastError (INV-7: el canal caido, corrupto o repetido nunca
 * interrumpe la reproduccion). El dato de red jamas elige una URL, jamas
 * indexa fuera de la tabla de glifos, jamas se evalua y jamas toca el DOM.
 *
 * Errores DE RED aplican backoff exponencial con techo (§8.2); un contenido
 * invalido con HTTP 200 mantiene la cadencia normal.
 *
 * `options` admite inyectar dependencias para test y para entornos sin
 * XMLHttpRequest global: createXhr, setTimer, clearTimer, now, intervalMs,
 * maxBackoffMs.
 */
(function (root) {
  "use strict";

  var DEFAULT_INTERVAL_MS = 20000;  /* dentro de los 15-30 s de §8.2 */
  var MAX_BACKOFF_MS = 300000;      /* techo de 5 minutos */

  function Channel(url, overlay, options) {
    var self = this;
    options = options || {};
    this.url = url;
    this.overlay = overlay;
    this.intervalMs = options.intervalMs > 0 ? options.intervalMs :
      DEFAULT_INTERVAL_MS;
    this.maxBackoffMs = options.maxBackoffMs > 0 ? options.maxBackoffMs :
      MAX_BACKOFF_MS;
    this._createXhr = options.createXhr || function () {
      return new XMLHttpRequest();
    };
    this._setTimer = options.setTimer || function (fn, ms) {
      return root.setTimeout(fn, ms);
    };
    this._clearTimer = options.clearTimer || function (id) {
      root.clearTimeout(id);
    };
    this._now = options.now || function () { return new Date().getTime(); };
    this.running = false;
    this.failures = 0;
    this.lastSerial = -1;
    this.lastError = "";
    this._timer = null;
    this._request = null;
    this._onTimer = function () {
      self._timer = null;
      self._poll();
    };
  }

  Channel.prototype.start = function () {
    if (this.running) return this;
    this.running = true;
    this.failures = 0;
    this._poll();
    return this;
  };

  Channel.prototype.stop = function () {
    this.running = false;
    if (this._timer !== null) {
      this._clearTimer(this._timer);
      this._timer = null;
    }
    if (this._request) {
      try {
        if (typeof this._request.abort === "function") this._request.abort();
      } catch (ignored) {
        /* un abort fallido no cambia nada: el estado ya es detenido */
      }
      this._request = null;
    }
    return this;
  };

  Channel.prototype._schedule = function (delay) {
    if (!this.running || this._timer !== null) return;
    this._timer = this._setTimer(this._onTimer, delay);
  };

  Channel.prototype._poll = function () {
    var self = this, xhr, separator;
    if (!this.running) return;
    xhr = this._createXhr();
    this._request = xhr;
    separator = this.url.indexOf("?") >= 0 ? "&" : "?";
    /* token anti-cache: la URL base es fija, el dato nunca la elige */
    xhr.open("GET", this.url + separator + "t=" + this._now(), true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) return;
      self._request = null;
      if (!self.running) return;
      if (xhr.status === 200) {
        self._handleText(String(xhr.responseText || ""));
        self.failures = 0;
        self._schedule(self.intervalMs);
      } else {
        self._networkFailure("HTTP " + xhr.status);
      }
    };
    try {
      xhr.send(null);
    } catch (error) {
      this._request = null;
      this._networkFailure("send fallo: " + error.message);
    }
  };

  Channel.prototype._networkFailure = function (reason) {
    var delay, i;
    this.failures++;
    this.lastError = reason;
    delay = this.intervalMs;
    for (i = 0; i < this.failures; i++) {
      delay *= 2;
      if (delay >= this.maxBackoffMs) {
        delay = this.maxBackoffMs;
        break;
      }
    }
    this._schedule(delay);
  };

  Channel.prototype._handleText = function (text) {
    var n = this.overlay.digitCount;
    var expected = 8 + 1 + n + 1;
    var i, c, serial;
    if (text.length !== expected) {
      this.lastError = "longitud invalida (" + text.length + ")";
      return false;
    }
    if (text.charCodeAt(8) !== 124 || text.charCodeAt(expected - 1) !== 10) {
      this.lastError = "forma invalida";
      return false;
    }
    for (i = 0; i < 8; i++) {
      c = text.charCodeAt(i);
      if (c < 48 || c > 57) {
        this.lastError = "serial no numerico";
        return false;
      }
    }
    for (i = 9; i < 9 + n; i++) {
      c = text.charCodeAt(i);
      if (c < 48 || c > 57) {
        this.lastError = "digito fuera de 0..9";
        return false;
      }
    }
    serial = 0;
    for (i = 0; i < 8; i++) serial = serial * 10 + (text.charCodeAt(i) - 48);
    if (serial <= this.lastSerial) {
      this.lastError = "serial repetido o retrocedido";
      return false;
    }
    if (!this.overlay.setValues(text.substring(9, 9 + n))) {
      this.lastError = "campos fuera de rango";
      return false;
    }
    this.lastSerial = serial;
    this.lastError = "";
    return true;
  };

  /* Devuelve el canal, o null si los argumentos no alcanzan para operar con
   * seguridad (mismo contrato que ASCILINEOverlay.attach). */
  function create(url, overlay, options) {
    if (typeof url !== "string" || !url) return null;
    if (!overlay || typeof overlay.setValues !== "function") return null;
    if (!(overlay.digitCount >= 1)) return null;
    return new Channel(url, overlay, options);
  }

  root.ASCILINEDataChannel = { create: create };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { create: create };
  }
})(typeof window !== "undefined" ? window : this);
