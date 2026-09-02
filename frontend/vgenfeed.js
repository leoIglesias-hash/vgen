"use strict";

/* vgenfeed.js - por donde entra el paquete al <video> (H-13).
 *
 * Un formato propio de video que corre en el <video> de un WebView tiene tres
 * puertas, y este modulo las abre todas con la misma forma:
 *
 *   A. concat()   init + segmentos en un Blob -> blob: -> video.src
 *                 (la pieza entera desde memoria; el piso de la cache)
 *   B. feedMse()  init + segmentos anexados a un SourceBuffer, uno detras del
 *                 otro, encadenados por `updateend` (la puerta viva)
 *   C. switchTo() cambio de pieza por `src`, midiendo pedido -> primer cuadro
 *                 (el incentivador que entra y sale a demanda)
 *
 * H-13 lo usa desde v0.html para preguntarle al aparato cual de las tres se
 * sostiene; el muxer de H-8 reusa la que quede en pie. Por eso no sabe nada del
 * pack: recibe URLs y un mime, nada mas.
 *
 * ES5.1 estricto (gate tests/test_frontend_compatibility.js): sin Promise,
 * sin fetch, sin JSON, sin arrow. Todo son callbacks encadenados, que es lo que
 * un WebView de 2018 con Chrome 70 ejecuta sin pensar. Sin dependencias.
 *
 * Todo lo que toca al mundo (window, XMLHttpRequest, setTimeout, Blob, URL)
 * se puede inyectar por `hooks`, y asi el test lo corre entero sin navegador.
 */

var VGenFeed = (function () {

  function hostOf(hooks) {
    if (hooks && hooks.host) { return hooks.host; }
    return typeof window !== "undefined" ? window : null;
  }

  function xhrOf(hooks) {
    if (hooks && hooks.XHR) { return hooks.XHR; }
    return typeof XMLHttpRequest !== "undefined" ? XMLHttpRequest : null;
  }

  function nowOf(hooks) {
    if (hooks && hooks.now) { return hooks.now; }
    return function () { return new Date().getTime(); };
  }

  /* Baja un archivo entero a memoria. cb(error, ArrayBuffer): error es un
   * texto corto o null. Un solo XHR, sin reintentos: el que reintenta es quien
   * llama, que sabe si vale la pena. */
  function getBytes(url, cb, hooks) {
    var XHR = xhrOf(hooks);
    var xhr, done = false;
    if (!XHR) { cb("sin XMLHttpRequest", null); return null; }
    xhr = new XHR();
    xhr.open("GET", url, true);
    xhr.responseType = "arraybuffer";
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4 || done) { return; }
      done = true;
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
        cb(null, xhr.response);
      } else {
        cb("HTTP " + xhr.status + " " + url, null);
      }
    };
    xhr.send(null);
    return xhr;
  }

  /* Baja varias URLs EN ORDEN, una a la vez (un WebView viejo no gana nada
   * abriendo 17 conexiones, y asi el orden de llegada es el orden pedido).
   * cb(error, parts[]). */
  function getAll(urls, cb, hooks) {
    var parts = [];
    function next(index) {
      if (index >= urls.length) { cb(null, parts); return; }
      getBytes(urls[index], function (error, bytes) {
        if (error) { cb(error, parts); return; }
        parts.push(bytes);
        next(index + 1);
      }, hooks);
    }
    next(0);
  }

  /* Camino A: los pedazos, tal cual bajaron, pegados en un Blob. Un fMP4 es
   * exactamente eso -init + fragmentos-, asi que si S10 se sostiene el muxer
   * de A es esta linea. Devuelve null donde no hay Blob. */
  function concat(parts, mime, hooks) {
    var host = hostOf(hooks);
    var BlobCtor = hooks && hooks.Blob ? hooks.Blob :
                   (host && host.Blob ? host.Blob :
                    (typeof Blob !== "undefined" ? Blob : null));
    if (!BlobCtor) { return null; }
    try {
      return new BlobCtor(parts, { type: mime });
    } catch (e) {
      return null;
    }
  }

  function urlApi(hooks) {
    var host = hostOf(hooks);
    if (hooks && hooks.URL) { return hooks.URL; }
    if (!host) { return null; }
    return host.URL || host.webkitURL || null;
  }

  function objectUrl(thing, hooks) {
    var api = urlApi(hooks);
    if (!api || !api.createObjectURL) { return ""; }
    return api.createObjectURL(thing);
  }

  function revoke(url, hooks) {
    var api = urlApi(hooks);
    if (url && api && api.revokeObjectURL) { api.revokeObjectURL(url); }
  }

  /* Que dice el aparato de MSE, antes de intentar nada. */
  function mseSupport(mime, hooks) {
    var host = hostOf(hooks);
    var MS = host ? host.MediaSource : null;
    if (!MS) { return "no"; }
    if (!MS.isTypeSupported) { return "sin isTypeSupported"; }
    return MS.isTypeSupported(mime) ? "si" : "no";
  }

  /* SourceBuffer.changeType permite cambiar de codec sin recrear el buffer:
   * es la diferencia entre poder intercalar VP9 y H.264 por MSE o no. */
  function hasChangeType(hooks) {
    var host = hostOf(hooks);
    var SB = host ? host.SourceBuffer : null;
    return !!(SB && SB.prototype && typeof SB.prototype.changeType === "function");
  }

  /* Camino B: MSE. Un MediaSource, un SourceBuffer del mime dado, y las URLs
   * bajadas y anexadas UNA POR UNA: se baja la siguiente recien cuando el
   * buffer termino de digerir la anterior (`updateend`). Anexar mientras
   * `updating` es true lanza InvalidStateError; encadenar por evento es la
   * unica forma correcta, y es lo que el test verifica con un buffer falso.
   *
   * hooks:
   *   mode      "sequence" para que el buffer reescriba tiempos en orden de
   *             anexo (lo que un bucle o un intercambio de piezas necesita);
   *             si el aparato no lo soporta, se sigue en "segments" y se avisa
   *   onOpen()  sourceopen recibido y SourceBuffer creado
   *   onAppend(index, bytes)  antes de cada appendBuffer
   *   onDone()  todo anexado y endOfStream() llamado
   *   onError(mensaje)
   *   play      false para no llamar a video.play() (por defecto se llama)
   *
   * Devuelve un mango con abort() y el MediaSource, o null si no hay MSE. */
  function feedMse(video, mime, urls, hooks) {
    var host = hostOf(hooks);
    var MS = host ? host.MediaSource : null;
    var ms, sb = null, index = 0, stopped = false, url = "";
    var events = hooks || {};

    function fail(why) {
      if (stopped) { return; }
      stopped = true;
      if (events.onError) { events.onError(why); }
    }

    function appendNext() {
      if (stopped) { return; }
      if (index >= urls.length) {
        try {
          if (ms.readyState === "open") { ms.endOfStream(); }
        } catch (e1) { fail("endOfStream: " + e1); return; }
        if (events.onDone) { events.onDone(); }
        return;
      }
      getBytes(urls[index], function (error, bytes) {
        if (stopped) { return; }
        if (error) { fail(error); return; }
        if (events.onAppend) { events.onAppend(index, bytes); }
        index++;
        try {
          sb.appendBuffer(bytes);
        } catch (e2) {
          fail("appendBuffer: " + e2);
        }
      }, hooks);
    }

    function onUpdateEnd() { appendNext(); }

    function onSourceOpen() {
      if (stopped || sb) { return; }
      try {
        sb = ms.addSourceBuffer(mime);
      } catch (e3) { fail("addSourceBuffer: " + e3); return; }
      if (events.mode === "sequence") {
        try { sb.mode = "sequence"; } catch (e4) {
          if (events.onWarn) { events.onWarn("sin modo sequence"); }
        }
      }
      sb.addEventListener("updateend", onUpdateEnd, false);
      sb.addEventListener("error", function () { fail("SourceBuffer error"); },
                          false);
      if (events.onOpen) { events.onOpen(sb); }
      appendNext();
    }

    if (!MS) { return null; }
    ms = new MS();
    ms.addEventListener("sourceopen", onSourceOpen, false);
    url = objectUrl(ms, hooks);
    video.src = url;
    if (video.load) { video.load(); }
    if (events.play !== false && video.play) { video.play(); }
    return {
      mediaSource: ms,
      url: url,
      abort: function () {
        stopped = true;
        if (sb) { sb.removeEventListener("updateend", onUpdateEnd, false); }
        revoke(url, hooks);
      }
    };
  }

  /* Camino C: cambio de pieza a demanda. Pone `src`, arranca, y mide desde el
   * pedido hasta el primer avance de currentTime: ese es el numero que el
   * usuario siente cuando pide la ruleta. cb(ms) con -1 si no arranco en
   * `timeout` ms (15 s por defecto). Sondea cada `step` ms (20 por defecto). */
  function switchTo(video, src, hooks, cb) {
    var host = hostOf(hooks);
    var now = nowOf(hooks);
    var step = hooks && hooks.step > 0 ? hooks.step : 20;
    var limit = hooks && hooks.timeout > 0 ? hooks.timeout : 15000;
    var t0, timer = 0, finished = false;

    function finish(ms) {
      if (finished) { return; }
      finished = true;
      if (timer && host && host.clearTimeout) { host.clearTimeout(timer); }
      timer = 0;
      cb(ms);
    }

    function poll() {
      var elapsed;
      if (finished) { return; }
      elapsed = now() - t0;
      if (video.currentTime > 0) { finish(elapsed); return; }
      if (elapsed > limit) { finish(-1); return; }
      timer = host.setTimeout(poll, step);
    }

    if (!host || !host.setTimeout) { cb(-1); return null; }
    t0 = now();
    video.src = src;
    if (video.load) { video.load(); }
    if (video.play) { video.play(); }
    poll();
    return { abort: function () { finish(-1); } };
  }

  return {
    getBytes: getBytes,
    getAll: getAll,
    concat: concat,
    objectUrl: objectUrl,
    revoke: revoke,
    mseSupport: mseSupport,
    hasChangeType: hasChangeType,
    feedMse: feedMse,
    switchTo: switchTo
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = VGenFeed;
}
