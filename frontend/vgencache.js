"use strict";

/* vgencache.js - el paquete residente en el aparato (H-12).
 *
 * El reporte de la caja (H-13) dijo que el arranque lo mandan los BYTES: 305 ms
 * a VP9 y mas de un segundo a Baseline por red, 517 ms desde blob:. Asi que la
 * pieza que se pide a demanda -el incentivador- tiene que estar RESIDENTE, y
 * residente quiere decir que sobrevive a un reinicio: IndexedDB. Este modulo
 * es la unica puerta a esa base: bajar con progreso, guardar pineado por
 * contenido, leer, listar, borrar lo viejo y medir el techo.
 *
 *   download(url, hooks, cb)   XHR arraybuffer con onprogress
 *   open(hooks, cb)            abre (o crea) la base "vgen" con un solo store
 *   put / get / remove / list / clear / prune
 *   keyFor(id, sha256)         id + "." + sha12: dos versiones de la misma
 *                              pieza nunca comparten clave (CACHE-001)
 *   noise(mb)                  bytes pseudoaleatorios para la prueba de techo
 *   quota(hooks, cb)           lo que el aparato dice tener (API con callback)
 *
 * Se guardan ArrayBuffers, no Blobs: el clon estructurado de un ArrayBuffer lo
 * soporta todo IndexedDB que exista, el de un Blob recien desde Chrome 37. El
 * Blob se arma al leer (VGenFeed.concat), que cuesta una copia y nada mas.
 *
 * ES5.1 estricto (gate tests/test_frontend_compatibility.js): IndexedDB es
 * una API de eventos y por eso entra en el piso; sin Promise, sin JSON. Todo
 * lo que toca al mundo se inyecta por hooks (idb, XHR, navigator), y el test
 * corre entero sin navegador.
 */

var VGenCache = (function () {

  var DB_NAME = "vgen";
  var DB_VERSION = 1;
  var STORE = "piezas";

  function hostOf(hooks) {
    if (hooks && hooks.host) { return hooks.host; }
    return typeof window !== "undefined" ? window : null;
  }

  function idbOf(hooks) {
    var host;
    if (hooks && hooks.idb !== undefined) { return hooks.idb; }
    host = hostOf(hooks);
    if (!host) { return null; }
    return host.indexedDB || host.webkitIndexedDB || host.mozIndexedDB || null;
  }

  function xhrOf(hooks) {
    if (hooks && hooks.XHR) { return hooks.XHR; }
    return typeof XMLHttpRequest !== "undefined" ? XMLHttpRequest : null;
  }

  function nowOf(hooks) {
    if (hooks && hooks.now) { return hooks.now; }
    return function () { return new Date().getTime(); };
  }

  /* El nombre del error, que es lo que va al reporte: QuotaExceededError es la
   * respuesta a la prueba de techo, no una excepcion. */
  function why(source, fallback) {
    var e = source ? source.error : null;
    if (e && e.name) { return e.name; }
    if (e) { return String(e); }
    return fallback || "error";
  }

  function available(hooks) {
    var idb = idbOf(hooks);
    return (idb && typeof idb.open === "function") ? "si" : "no";
  }

  /* Bajada entera a memoria con progreso: onProgress(loaded, total) cada vez
   * que el navegador avisa (total puede ser 0 si no hay Content-Length).
   * cb(error, ArrayBuffer, ms). */
  function download(url, hooks, cb) {
    var XHR = xhrOf(hooks);
    var now = nowOf(hooks);
    var xhr, t0, done = false;
    if (!XHR) { cb("sin XMLHttpRequest", null, 0); return null; }
    xhr = new XHR();
    t0 = now();
    xhr.open("GET", url, true);
    xhr.responseType = "arraybuffer";
    if (hooks && hooks.onProgress) {
      xhr.onprogress = function (event) {
        hooks.onProgress(event && event.loaded ? event.loaded : 0,
                         event && event.lengthComputable ? event.total : 0);
      };
    }
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4 || done) { return; }
      done = true;
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
        cb(null, xhr.response, now() - t0);
      } else {
        cb("HTTP " + xhr.status + " " + url, null, now() - t0);
      }
    };
    xhr.send(null);
    return xhr;
  }

  /* Abre la base; la crea con su unico store la primera vez. cb(error, db). */
  function open(hooks, cb) {
    var idb = idbOf(hooks);
    var request, settled = false;
    function settle(error, db) {
      if (settled) { return; }
      settled = true;
      cb(error, db || null);
    }
    if (!idb || typeof idb.open !== "function") {
      settle("sin indexedDB"); return null;
    }
    try {
      request = idb.open(DB_NAME, DB_VERSION);
    } catch (e) {
      settle("open: " + e); return null;
    }
    request.onupgradeneeded = function () {
      var db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = function () { settle(null, request.result); };
    request.onerror = function () { settle("open: " + why(request)); };
    request.onblocked = function () { settle("open: bloqueada"); };
    return request;
  }

  function storeOf(db, mode, cb) {
    var tx;
    try {
      tx = db.transaction([STORE], mode);
    } catch (e) {
      cb("transaction: " + e, null, null); return;
    }
    cb(null, tx, tx.objectStore(STORE));
  }

  /* Escritura: la respuesta llega por la TRANSACCION, no por el request. Un
   * QuotaExceededError aborta la transaccion (onabort) aunque el put haya
   * dicho que si; escuchar solo el request es no enterarse. cb(error). */
  function write(db, run, cb) {
    storeOf(db, "readwrite", function (error, tx, store) {
      var settled = false;
      function settle(e) { if (!settled) { settled = true; cb(e); } }
      if (error) { settle(error); return; }
      tx.oncomplete = function () { settle(null); };
      tx.onerror = function () { settle(why(tx, "transaction error")); };
      tx.onabort = function () { settle(why(tx, "abort")); };
      try {
        run(store);
      } catch (e) {
        settle("write: " + e);
      }
    });
  }

  /* record: { key, id, sha, mime, bytes (numero), data (ArrayBuffer), at } */
  function put(db, record, cb) {
    write(db, function (store) { store.put(record); }, cb);
  }

  function remove(db, key, cb) {
    write(db, function (store) { store["delete"](key); }, cb);
  }

  function clear(db, cb) {
    write(db, function (store) { store.clear(); }, cb);
  }

  /* cb(error, record | null) */
  function get(db, key, cb) {
    storeOf(db, "readonly", function (error, tx, store) {
      var request;
      if (error) { cb(error, null); return; }
      try {
        request = store.get(key);
      } catch (e) { cb("get: " + e, null); return; }
      request.onsuccess = function () {
        cb(null, request.result === undefined ? null : request.result);
      };
      request.onerror = function () { cb("get: " + why(request), null); };
    });
  }

  /* Lista lo guardado SIN los bytes: clave, id, sha, mime, tamano y fecha.
   * cb(error, rows[]). */
  function list(db, cb) {
    storeOf(db, "readonly", function (error, tx, store) {
      var request, rows = [];
      if (error) { cb(error, rows); return; }
      try {
        request = store.openCursor();
      } catch (e) { cb("cursor: " + e, rows); return; }
      request.onsuccess = function (event) {
        var cursor = (event && event.target) ? event.target.result : request.result;
        var v;
        if (!cursor) { cb(null, rows); return; }
        v = cursor.value || {};
        rows.push({ key: v.key, id: v.id, sha: v.sha, mime: v.mime,
                    bytes: v.bytes || 0, at: v.at || 0 });
        cursor["continue"]();
      };
      request.onerror = function () { cb("cursor: " + why(request), rows); };
    });
  }

  /* Pineo por contenido: la clave lleva el sha, asi que una pieza re-emitida
   * es una clave NUEVA y la vieja queda huerfana hasta que prune() la borre. */
  function keyFor(id, sha) {
    return id + "." + String(sha || "").substring(0, 12);
  }

  /* Borra todo lo que no este en keep[]. cb(error, removedKeys[]). */
  function prune(db, keep, cb) {
    list(db, function (error, rows) {
      var doomed = [], i;
      if (error) { cb(error, []); return; }
      for (i = 0; i < rows.length; i++) {
        if (keep.indexOf(rows[i].key) < 0) { doomed.push(rows[i].key); }
      }
      if (!doomed.length) { cb(null, []); return; }
      write(db, function (store) {
        var j;
        for (j = 0; j < doomed.length; j++) { store["delete"](doomed[j]); }
      }, function (e) { cb(e, e ? [] : doomed); });
    });
  }

  /* Bytes para la prueba de techo. Pseudoaleatorios a proposito: la base
   * comprime lo que guarda (LevelDB + Snappy en Chromium), y 50 MB de ceros
   * entrarian donde 50 MB de video no entran. Un megabyte de ruido repetido
   * mb veces alcanza: la compresion trabaja por bloques mucho mas chicos. */
  function noise(mb) {
    var MB = 1048576;
    var chunk, big, i, x = 2463534242;
    if (typeof Uint8Array === "undefined" || !(mb > 0)) { return null; }
    chunk = new Uint8Array(MB);
    for (i = 0; i < MB; i++) {
      x = (x * 1103515245 + 12345) & 0x7fffffff;
      chunk[i] = (x >>> 16) & 255;
    }
    big = new Uint8Array(mb * MB);
    for (i = 0; i < mb; i++) { big.set(chunk, i * MB); }
    return big.buffer;
  }

  /* Lo que el aparato dice tener. La unica API con callback es la de WebKit
   * (queryUsageAndQuota); la moderna (navigator.storage.estimate) devuelve una
   * Promise y queda fuera del piso. cb(error, usedBytes, grantedBytes). */
  function quota(hooks, cb) {
    var host = hostOf(hooks);
    var nav = (hooks && hooks.navigator) ? hooks.navigator :
              (host ? host.navigator : null);
    var api = nav ? (nav.webkitTemporaryStorage || nav.webkitPersistentStorage) : null;
    if (!api || typeof api.queryUsageAndQuota !== "function") {
      cb("sin API de cuota", 0, 0); return;
    }
    try {
      api.queryUsageAndQuota(function (used, granted) {
        cb(null, used || 0, granted || 0);
      }, function (e) { cb("cuota: " + (e && e.name ? e.name : e), 0, 0); });
    } catch (e2) {
      cb("cuota: " + e2, 0, 0);
    }
  }

  return {
    DB_NAME: DB_NAME,
    STORE: STORE,
    available: available,
    download: download,
    open: open,
    put: put,
    get: get,
    remove: remove,
    list: list,
    clear: clear,
    prune: prune,
    keyFor: keyFor,
    noise: noise,
    quota: quota
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = VGenCache;
}
