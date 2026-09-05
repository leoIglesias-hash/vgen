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
 *                              (hasta TANDA_MB de una vez, ni un byte mas)
 *   quota(hooks, cb)           lo que el aparato dice tener (API con callback)
 *   budget / plan / ensure     H-15 (H-8a): presupuesto por navegador, que se
 *                              guarda por prioridad, y bajar-o-leer cada pieza
 *   join / part                un solo ArrayBuffer con rangos [offset, largo]
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

  /* Cuanto ruido se puede pedir DE UNA VEZ. No es un gusto: pedir 50 MB
   * contiguos y despues clonarlos para guardarlos cerro la app de la caja el
   * 2026-09-04 (H-12b). El techo se mide sumando tandas de este tamano, y el
   * limite se cumple aca -en el modulo- para que ningun llamador nuevo lo
   * pueda saltear sin darse cuenta. */
  var TANDA_MB = 5;

  /* Bytes para la prueba de techo. Pseudoaleatorios a proposito: la base
   * comprime lo que guarda (LevelDB + Snappy en Chromium), y 50 MB de ceros
   * entrarian donde 50 MB de video no entran. Un megabyte de ruido repetido
   * mb veces alcanza: la compresion trabaja por bloques mucho mas chicos. */
  function noise(mb) {
    var MB = 1048576;
    var chunk, big, i, x = 2463534242;
    if (typeof Uint8Array === "undefined" || !(mb > 0)) { return null; }
    if (mb > TANDA_MB) { return null; }
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

  /* --- H-15: residencia (H-8a, 2026-09-05) --- */

  /* Presupuesto fijo por navegador: min(tope absoluto, fraccion de la cuota
   * declarada). Los valores manuales del operador (hooks.tope, hooks.fraccion)
   * prevalecen sobre los defaults. La cuota declarada NO es un gate (la caja
   * dice 13/225 MB y despues 43/225 con la base vacia): por eso hay tope
   * absoluto, y si el aparato no declara cuota, el tope manda solo. */
  var TOPE_BYTES = 150 * 1048576;
  var FRACCION = 0.5;

  function budget(quotaBytes, hooks) {
    var tope = (hooks && hooks.tope > 0) ? hooks.tope : TOPE_BYTES;
    var fraccion = (hooks && hooks.fraccion > 0) ? hooks.fraccion : FRACCION;
    var porCuota;
    if (!(quotaBytes > 0)) { return tope; }
    porCuota = Math.floor(quotaBytes * fraccion);
    return porCuota < tope ? porCuota : tope;
  }

  /* Que se guarda y que va por red. `pieces` trae {id, residente ("si"|"no"),
   * prioridad (entero, menor = antes), bytes}. Se ordena por prioridad -orden
   * de llegada a igual prioridad- y se toma mientras entre en el presupuesto;
   * lo que no entra se marca "por red". Nunca se pasa por alto una pieza chica
   * porque una grande no entro antes: el orden lo fijo el operador a mano y se
   * respeta, asi que lo que sigue a la primera que no entra tampoco entra. */
  function plan(pieces, budgetBytes) {
    var orden = [], keep = [], porRed = [], suma = 0, i, p, lleno = false;
    for (i = 0; i < pieces.length; i++) {
      p = pieces[i];
      if (String(p.residente) !== "si") { porRed.push(p); continue; }
      orden.push({ p: p, n: i });
    }
    orden.sort(function (a, b) {
      var pa = parseInt(a.p.prioridad, 10), pb = parseInt(b.p.prioridad, 10);
      if (isNaN(pa)) { pa = 1e9; }
      if (isNaN(pb)) { pb = 1e9; }
      if (pa !== pb) { return pa - pb; }
      return a.n - b.n;
    });
    for (i = 0; i < orden.length; i++) {
      p = orden[i].p;
      if (!lleno && suma + (parseInt(p.bytes, 10) || 0) <= budgetBytes) {
        suma += parseInt(p.bytes, 10) || 0;
        keep.push(p);
      } else {
        lleno = true;
        porRed.push(p);
      }
    }
    return { keep: keep, porRed: porRed, bytes: suma };
  }

  /* Junta varios ArrayBuffers en uno, con la tabla de rangos [offset, largo]
   * de cada parte. Es el "archivo unico con segmentos direccionados por rango"
   * del formato: los mismos bytes sirven enteros (Blob, camino A) o de a
   * pedazos (anillo MSE, camino B), sin copiar nada mas al reproducir. */
  function join(parts) {
    var total = 0, i, out, offset = 0, rangos = [];
    for (i = 0; i < parts.length; i++) { total += parts[i].byteLength; }
    out = new Uint8Array(total);
    for (i = 0; i < parts.length; i++) {
      out.set(new Uint8Array(parts[i]), offset);
      rangos.push([offset, parts[i].byteLength]);
      offset += parts[i].byteLength;
    }
    return { data: out.buffer, rangos: rangos };
  }

  /* Una vista sobre el rango `index` de un registro guardado con rangos. Sin
   * rangos, la vista es el registro entero. Devuelve un Uint8Array (lo que
   * appendBuffer acepta) sin copiar. */
  function part(record, index) {
    var r;
    if (!record || !record.data) { return null; }
    if (!record.rangos || !record.rangos.length) {
      return new Uint8Array(record.data);
    }
    r = record.rangos[index];
    if (!r) { return null; }
    return new Uint8Array(record.data, r[0], r[1]);
  }

  /* Asegura que cada pieza de `list` este en la base; lo que falta se baja
   * (todas sus partes, en orden) y se guarda. Secuencial: un WebView viejo no
   * gana nada con 17 conexiones y asi el progreso es legible.
   *
   * list[i]: { key, id, sha, mime, urls: [..], bytes }
   * hooks:   onPiece(id, origen "cache"|"red"|"error", ms, bytes, detalle),
   *          onProgress(id, loaded, total) durante la bajada, + los de download
   * cb(summary): { hits, downloaded, failed: [ids], bytes, ms } */
  function ensure(db, list, hooks, cb) {
    var now = nowOf(hooks);
    var t0 = now();
    var summary = { hits: 0, downloaded: 0, failed: [], bytes: 0, ms: 0 };
    var events = hooks || {};

    function tell(id, origen, ms, bytes, detalle) {
      if (events.onPiece) { events.onPiece(id, origen, ms, bytes, detalle || ""); }
    }

    function fetchAll(item, cb2) {
      var parts = [], i = 0, tStart = now();
      function nextPart() {
        if (i >= item.urls.length) { cb2(null, parts, now() - tStart); return; }
        download(item.urls[i], {
          XHR: events.XHR, now: events.now,
          onProgress: function (loaded, total) {
            if (events.onProgress) { events.onProgress(item.id, loaded, total, i, item.urls.length); }
          }
        }, function (error, bytes) {
          if (error) { cb2(error, parts, now() - tStart); return; }
          parts.push(bytes);
          i++;
          nextPart();
        });
      }
      nextPart();
    }

    function one(index) {
      var item, tGet;
      if (index >= list.length) {
        summary.ms = now() - t0;
        cb(summary);
        return;
      }
      item = list[index];
      tGet = now();
      get(db, item.key, function (error, record) {
        if (!error && record && record.data) {
          summary.hits++;
          summary.bytes += record.bytes || 0;
          tell(item.id, "cache", now() - tGet, record.bytes || 0);
          one(index + 1);
          return;
        }
        fetchAll(item, function (error2, parts, ms) {
          var joined, record2;
          if (error2) {
            summary.failed.push(item.id);
            tell(item.id, "error", ms, 0, error2);
            one(index + 1);
            return;
          }
          joined = join(parts);
          record2 = { key: item.key, id: item.id, sha: item.sha, mime: item.mime,
                      bytes: joined.data.byteLength, data: joined.data,
                      rangos: joined.rangos, at: now() };
          put(db, record2, function (error3) {
            if (error3) {
              /* No entro (cuota o lo que sea): se dice, y la pieza va por red. */
              summary.failed.push(item.id);
              tell(item.id, "error", ms, joined.data.byteLength, "guardar: " + error3);
            } else {
              summary.downloaded++;
              summary.bytes += joined.data.byteLength;
              tell(item.id, "red", ms, joined.data.byteLength);
            }
            one(index + 1);
          });
        });
      });
    }
    if (!db) { cb(summary); return; }
    one(0);
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
    TANDA_MB: TANDA_MB,
    noise: noise,
    quota: quota,
    TOPE_BYTES: TOPE_BYTES,
    FRACCION: FRACCION,
    budget: budget,
    plan: plan,
    join: join,
    part: part,
    ensure: ensure
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = VGenCache;
}
