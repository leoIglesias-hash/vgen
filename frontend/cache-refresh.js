/*
 * cache-refresh.js - Utilidades ES5 para renovar un ASCLV con URL estable.
 *
 * El token cambia solamente la URL de solicitud del video. No intenta borrar
 * la cache global del navegador ni depende de APIs modernas.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  root.ASCILINECacheRefresh = api;
}(typeof window !== "undefined" ? window : this, function () {
  "use strict";

  function clockNow() {
    return Date.now ? Date.now() : new Date().getTime();
  }

  function isMenuKey(event) {
    var key, physical, identifier, code;
    if (!event) { return false; }

    /* Si el navegador informa un nombre moderno, evitamos confundir Tab
       (keyCode 9) con el digito crudo 9 de algunos controles antiguos. */
    key = event.key;
    if (typeof key === "string" && key.length) {
      if (key === "9") { return true; }
      if (key === "Tab" || (key.length === 1 && key >= "0" && key <= "9")) {
        return false;
      }
      /* "Unidentified" es comun en controles TV: permite usar keyCode. */
    }

    physical = event.code;
    if (typeof physical === "string" && physical.length) {
      if (physical === "Digit9" || physical === "Numpad9") { return true; }
      if (physical === "Tab" || physical.indexOf("Digit") === 0 ||
          physical.indexOf("Numpad") === 0) { return false; }
    }

    identifier = event.keyIdentifier;
    if (typeof identifier === "string" && identifier.length) {
      if (identifier === "U+0039") { return true; }
      if (identifier === "U+0009" || identifier.indexOf("U+003") === 0) {
        return false;
      }
    }

    code = event.keyCode;
    if (typeof code !== "number") { code = event.which; }
    /* keyCode 9 tambien es Tab en navegadores antiguos y no hay informacion
       adicional para distinguirlo de un control que entregue el digito crudo.
       El hotspot conserva acceso para esos controles sin secuestrar el foco. */
    return code === 57 || code === 105;
  }

  function validToken(token) {
    return typeof token === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(token);
  }

  function readToken(storage, key) {
    var token;
    if (!storage || !storage.getItem) { return ""; }
    try { token = storage.getItem(key); }
    catch (ignored) { return ""; }
    return validToken(token) ? token : "";
  }

  function writeToken(storage, key, token) {
    if (!storage || !storage.setItem) { return false; }
    try {
      storage.setItem(key, token);
      return true;
    } catch (ignored) { return false; }
  }

  function createToken(now, random) {
    var stamp, value, suffix;
    stamp = typeof now === "function" ? now() : clockNow();
    if (typeof stamp !== "number" || !isFinite(stamp) || stamp < 0) {
      stamp = clockNow();
    }
    value = typeof random === "function" ? random() : Math.random();
    if (typeof value !== "number" || !isFinite(value) || value < 0) { value = 0; }
    if (value >= 1) { value = 0.999999999; }
    suffix = Math.floor(value * 4294967296);
    return "v" + Math.floor(stamp).toString(36) + "-" + suffix.toString(36);
  }

  function appendToken(source, parameter, token) {
    var hashAt, fragment, base, separator;
    if (!validToken(token)) { return source; }
    hashAt = source.indexOf("#");
    fragment = hashAt >= 0 ? source.substr(hashAt) : "";
    base = hashAt >= 0 ? source.substr(0, hashAt) : source;
    separator = base.indexOf("?") >= 0 ? "&" : "?";
    return base + separator + encodeURIComponent(parameter) + "=" +
      encodeURIComponent(token) + fragment;
  }

  function createTokenStore(options) {
    options = options || {};
    var source = options.source || "";
    var parameter = options.parameter || "asclv_refresh";
    var storageKey = options.storageKey || "ASCILINE_ASCLV_REFRESH_V1";
    var storage = options.storage || null;
    var token = readToken(storage, storageKey);

    function rotate() {
      token = createToken(options.now, options.random);
      /* Si storage esta bloqueado, el token sigue siendo valido en memoria. */
      writeToken(storage, storageKey, token);
      return token;
    }

    return {
      rotate: rotate,
      url: function (forceRefresh) {
        if (forceRefresh) { rotate(); }
        return token ? appendToken(source, parameter, token) : source;
      },
      currentToken: function () { return token; }
    };
  }

  function GestureGuard(guardMs) {
    this.guardMs = typeof guardMs === "number" ? guardMs : 800;
    this.lastTouch = -1;
  }

  GestureGuard.prototype.accept = function (type, time) {
    if (type === "click" && this.lastTouch >= 0 && time >= this.lastTouch &&
        time - this.lastTouch < this.guardMs) {
      return false;
    }
    if (type === "touchend") { this.lastTouch = time; }
    return true;
  };

  return {
    isMenuKey: isMenuKey,
    validToken: validToken,
    readToken: readToken,
    writeToken: writeToken,
    createToken: createToken,
    appendToken: appendToken,
    createTokenStore: createTokenStore,
    GestureGuard: GestureGuard
  };
}));
