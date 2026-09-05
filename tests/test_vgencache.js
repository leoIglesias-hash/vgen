"use strict";

/* H-12: vgencache.js guarda el paquete en IndexedDB pineado por contenido y lo
 * devuelve para reproducir desde blob:. Se prueba entero sin navegador con una
 * IndexedDB falsa que respeta lo que la de verdad hace y que un WebView
 * castiga si se ignora: las respuestas llegan por EVENTOS y despues (nunca en
 * la misma pila), la escritura se confirma por la TRANSACCION (oncomplete) y
 * un exceso de cuota la ABORTA aunque el put haya salido bien. */

var assert = require("assert");
var Cache = require("../frontend/vgencache.js");

/* --- IndexedDB falsa: asincronia a mano con flush() --- */

var queue = [];
function later(fn) { queue.push(fn); }
function flush() {
  var fn;
  while (queue.length) { fn = queue.shift(); fn(); }
}

function FakeDB(limitBytes) {
  this.records = {};
  this.limit = limitBytes || Infinity;
  this.stores = [];
  var self = this;
  /* Como la de verdad: contains() dice lo que HAY, no lo que deberia haber. */
  this.objectStoreNames = { contains: function (name) {
    var i;
    for (i = 0; i < self.stores.length; i++) { if (self.stores[i].name === name) { return true; } }
    return false;
  } };
  this.closed = false;
}
FakeDB.prototype.createObjectStore = function (name, options) {
  this.stores.push({ name: name, keyPath: options.keyPath });
};
FakeDB.prototype.used = function () {
  var total = 0, k;
  for (k in this.records) {
    if (this.records.hasOwnProperty(k)) { total += this.records[k].bytes || 0; }
  }
  return total;
};
FakeDB.prototype.transaction = function (names, mode) {
  var db = this;
  var tx = { mode: mode, pending: 0, error: null, aborted: false };
  function settle() {
    if (tx.pending > 0) { return; }
    later(function () {
      if (tx.aborted) { if (tx.onabort) { tx.onabort(); } }
      else if (tx.oncomplete) { tx.oncomplete(); }
    });
  }
  function request(work) {
    var req = { result: undefined, error: null };
    tx.pending++;
    later(function () {
      var outcome;
      tx.pending--;
      if (tx.aborted) { return; }
      try {
        outcome = work();
        req.result = outcome;
        if (req.onsuccess) { req.onsuccess({ target: { result: outcome } }); }
      } catch (e) {
        req.error = { name: e.message };
        tx.error = req.error;
        tx.aborted = true;
        if (req.onerror) { req.onerror(); }
      }
      settle();
    });
    return req;
  }
  var store = {
    put: function (record) {
      if (mode !== "readwrite") { throw new Error("ReadOnlyError"); }
      return request(function () {
        var others = db.used() - (db.records[record.key] ? db.records[record.key].bytes : 0);
        if (others + (record.bytes || 0) > db.limit) {
          throw new Error("QuotaExceededError");
        }
        db.records[record.key] = record;
        return record.key;
      });
    },
    get: function (key) {
      return request(function () { return db.records[key]; });
    },
    "delete": function (key) {
      return request(function () { delete db.records[key]; return undefined; });
    },
    clear: function () {
      return request(function () { db.records = {}; return undefined; });
    },
    openCursor: function () {
      var keys = [], k, at = 0, req;
      for (k in db.records) { if (db.records.hasOwnProperty(k)) { keys.push(k); } }
      keys.sort();
      function step() {
        var cursor;
        if (at >= keys.length) {
          if (req.onsuccess) { req.onsuccess({ target: { result: null } }); }
          return;
        }
        cursor = { value: db.records[keys[at]] };
        cursor["continue"] = function () { at++; later(step); };
        if (req.onsuccess) { req.onsuccess({ target: { result: cursor } }); }
      }
      req = { result: undefined, error: null };
      tx.pending++;
      later(function () { tx.pending--; step(); settle(); });
      return req;
    }
  };
  tx.objectStore = function () { return store; };
  return tx;
};

function fakeIdb(options) {
  var opts = options || {};
  var api = { opened: [], db: null };
  api.open = function (name, version) {
    var req = { result: null, error: null };
    api.opened.push(name + "@" + version);
    later(function () {
      var fresh = !api.db;
      if (opts.fail) {
        req.error = { name: opts.fail };
        if (req.onerror) { req.onerror(); }
        return;
      }
      if (fresh) {
        api.db = new FakeDB(opts.limit);
        req.result = api.db;
        if (req.onupgradeneeded) { req.onupgradeneeded(); }
      }
      req.result = api.db;
      if (req.onsuccess) { req.onsuccess(); }
    });
    return req;
  };
  return api;
}

function buffer(n) { return { byteLength: n, tag: "buf" + n }; }

/* --- deteccion y apertura --- */

(function testAvailability() {
  assert.strictEqual(Cache.available({ idb: fakeIdb() }), "si");
  assert.strictEqual(Cache.available({ idb: {} }), "no",
    "un objeto sin open() no es una IndexedDB: la caja falsa del test de pagina");
  assert.strictEqual(Cache.available({ idb: null }), "no");
  assert.strictEqual(Cache.available({ host: { webkitIndexedDB: fakeIdb() } }), "si",
    "el prefijo webkit vale: es lo que traen los WebViews viejos");
}());

(function testOpenCreatesTheStoreOnceAndReportsErrorsAsText() {
  var idb = fakeIdb();
  var got = null;
  Cache.open({ idb: idb }, function (error, db) { got = [error, db]; });
  assert.strictEqual(got, null, "la apertura es asincrona: nada llega en la misma pila");
  flush();
  assert.strictEqual(got[0], null);
  assert.deepStrictEqual(got[1].stores, [{ name: "piezas", keyPath: "key" }],
    "la primera apertura crea el unico store, con la clave adentro del registro");
  assert.deepStrictEqual(idb.opened, ["vgen@1"]);
  Cache.open({ idb: idb }, function (error, db) { got = [error, db]; });
  flush();
  assert.strictEqual(got[1].stores.length, 1, "la segunda apertura no recrea nada");

  Cache.open({ idb: {} }, function (error, db) { got = [error, db]; });
  assert.deepStrictEqual(got, ["sin indexedDB", null],
    "sin IndexedDB avisa en el acto y con texto, no con excepcion");
  Cache.open({ idb: fakeIdb({ fail: "UnknownError" }) }, function (error, db) { got = [error, db]; });
  flush();
  assert.deepStrictEqual(got, ["open: UnknownError", null],
    "el nombre del error es lo que va al reporte");
}());

/* --- put / get / list / remove / clear --- */

(function testRoundTripKeepsTheBytesAndListsWithoutThem() {
  var idb = fakeIdb();
  var db = null, got = null, rows = null;
  Cache.open({ idb: idb }, function (e, d) { db = d; });
  flush();
  Cache.put(db, { key: "a.111111111111", id: "a", sha: "111111111111ff", mime: "video/mp4",
                  bytes: 3, data: buffer(3), at: 10 }, function (e) { got = e; });
  assert.strictEqual(got, null, "todavia nada: la confirmacion llega por oncomplete");
  flush();
  assert.strictEqual(got, null);
  Cache.get(db, "a.111111111111", function (e, r) { got = [e, r]; });
  flush();
  assert.strictEqual(got[0], null);
  assert.deepStrictEqual(got[1].data, buffer(3), "vuelven los mismos bytes");
  Cache.get(db, "no-esta", function (e, r) { got = [e, r]; });
  flush();
  assert.deepStrictEqual(got, [null, null], "lo que no esta es null, no un error");

  Cache.put(db, { key: "b.222222222222", id: "b", sha: "222222222222", mime: "video/webm",
                  bytes: 5, data: buffer(5), at: 11 }, function () {});
  flush();
  Cache.list(db, function (e, r) { rows = [e, r]; });
  flush();
  assert.strictEqual(rows[0], null);
  assert.deepStrictEqual(rows[1], [
    { key: "a.111111111111", id: "a", sha: "111111111111ff", mime: "video/mp4", bytes: 3, at: 10 },
    { key: "b.222222222222", id: "b", sha: "222222222222", mime: "video/webm", bytes: 5, at: 11 }
  ], "la lista trae los metadatos y NO los bytes: es para la cabecera del reporte");

  Cache.remove(db, "a.111111111111", function (e) { got = e; });
  flush();
  assert.strictEqual(got, null);
  Cache.list(db, function (e, r) { rows = r; });
  flush();
  assert.strictEqual(rows.length, 1);
  Cache.clear(db, function (e) { got = e; });
  flush();
  Cache.list(db, function (e, r) { rows = r; });
  flush();
  assert.deepStrictEqual(rows, [], "clear deja la base vacia");
}());

/* --- la cuota: el aparato dice hasta donde --- */

(function testQuotaExceededArrivesThroughTheTransaction() {
  var idb = fakeIdb({ limit: 10 });
  var db = null, got = null, rows = null;
  Cache.open({ idb: idb }, function (e, d) { db = d; });
  flush();
  Cache.put(db, { key: "chica", bytes: 8, data: buffer(8) }, function (e) { got = e; });
  flush();
  assert.strictEqual(got, null, "8 de 10 entra");
  Cache.put(db, { key: "grande", bytes: 4, data: buffer(4) }, function (e) { got = e; });
  flush();
  assert.strictEqual(got, "QuotaExceededError",
    "el exceso de cuota llega como abort de la transaccion, con su nombre");
  Cache.list(db, function (e, r) { rows = r; });
  flush();
  assert.strictEqual(rows.length, 1, "lo que no entro no quedo a medias");
}());

/* --- pineo por contenido y poda --- */

(function testKeyForPinsByContentAndPruneDropsTheRest() {
  var idb = fakeIdb();
  var db = null, got = null, rows = null;
  assert.strictEqual(Cache.keyFor("v0-vp9", "abcdef0123456789abcdef"), "v0-vp9.abcdef012345",
    "la clave lleva el sha corto: una re-emision es otra clave (CACHE-001)");
  assert.notStrictEqual(Cache.keyFor("v0-vp9", "aaaa"), Cache.keyFor("v0-vp9", "bbbb"));
  Cache.open({ idb: idb }, function (e, d) { db = d; });
  flush();
  ["v0-vp9.aaaa", "v0-vp9.bbbb", "v0-h264-baseline.cccc", "techo.10"].forEach(function (key) {
    Cache.put(db, { key: key, bytes: 1, data: buffer(1) }, function () {});
    flush();
  });
  Cache.prune(db, ["v0-vp9.bbbb", "v0-h264-baseline.cccc"], function (e, removed) {
    got = [e, removed];
  });
  flush();
  assert.strictEqual(got[0], null);
  assert.deepStrictEqual(got[1].sort(), ["techo.10", "v0-vp9.aaaa"],
    "se borra todo lo que no esta en el manifiesto vigente: versiones viejas y restos de pruebas");
  Cache.list(db, function (e, r) { rows = r; });
  flush();
  assert.deepStrictEqual(rows.map(function (r) { return r.key; }),
    ["v0-h264-baseline.cccc", "v0-vp9.bbbb"]);
  Cache.prune(db, ["v0-h264-baseline.cccc", "v0-vp9.bbbb"], function (e, removed) {
    got = [e, removed];
  });
  flush();
  assert.deepStrictEqual(got, [null, []], "sin huerfanas no se abre una escritura");
}());

/* --- bajada con progreso --- */

(function testDownloadReportsProgressAndTime() {
  var progress = [];
  var got = null;
  var t = 100;
  function FakeXHR() { this.readyState = 0; this.status = 0; this.response = null; }
  FakeXHR.prototype.open = function (method, url) { this.url = url; };
  FakeXHR.prototype.send = function () {
    var self = this;
    assert.strictEqual(self.responseType, "arraybuffer");
    if (self.onprogress) {
      self.onprogress({ loaded: 4, total: 9, lengthComputable: true });
      self.onprogress({ loaded: 9, total: 9, lengthComputable: true });
    }
    t = 350;
    self.readyState = 4;
    self.status = self.url === "rota" ? 404 : 200;
    self.response = self.status === 200 ? buffer(9) : null;
    self.onreadystatechange();
  };
  Cache.download("pieza.webm", {
    XHR: FakeXHR, now: function () { return t; },
    onProgress: function (loaded, total) { progress.push(loaded + "/" + total); }
  }, function (error, bytes, ms) { got = [error, bytes, ms]; });
  assert.deepStrictEqual(progress, ["4/9", "9/9"],
    "el progreso se reporta: en la TV una bajada de 9 MB sin progreso parece colgada");
  assert.deepStrictEqual(got, [null, buffer(9), 250]);
  Cache.download("rota", { XHR: FakeXHR, now: function () { return t; } },
    function (error, bytes) { got = [error, bytes]; });
  assert.deepStrictEqual(got, ["HTTP 404 rota", null]);
  Cache.download("x", { XHR: null }, function (error) { got = error; });
  assert.strictEqual(got, "sin XMLHttpRequest");
}());

/* --- relleno para el techo --- */

(function testNoiseIsNoisyAndSized() {
  var buf = Cache.noise(2);
  var view, i, zeros = 0, half = 1048576;
  assert.strictEqual(buf.byteLength, 2 * 1048576, "2 MB exactos");
  view = new Uint8Array(buf);
  for (i = 0; i < 4096; i++) { if (view[i] === 0) { zeros++; } }
  assert(zeros < 64, "ruido, no ceros: la base comprime y 50 MB de ceros no miden nada");
  assert.strictEqual(view[half + 7], view[7], "un megabyte de ruido repetido");
  assert.strictEqual(Cache.noise(0), null);
}());

/* H-12b: el limite de una tanda lo cumple el modulo, no la disciplina del que
 * llama. Pedir 50 MB contiguos y clonarlos para guardarlos cerro la app de la
 * caja el 2026-09-04, y una app cerrada no informa ningun techo. */
(function testNoiseRefusesMoreThanOneTanda() {
  assert.strictEqual(Cache.TANDA_MB, 5, "la tanda son 5 MB");
  assert(Cache.noise(Cache.TANDA_MB), "una tanda entera si");
  assert.strictEqual(Cache.noise(Cache.TANDA_MB + 1), null, "una tanda y media no");
  assert.strictEqual(Cache.noise(50), null, "el salto que cerro la app, jamas");
}());

/* --- cuota --- */

(function testQuotaUsesTheCallbackApiOnly() {
  var got = null;
  Cache.quota({ navigator: {} }, function (e, used, granted) { got = [e, used, granted]; });
  assert.deepStrictEqual(got, ["sin API de cuota", 0, 0]);
  Cache.quota({ navigator: { webkitTemporaryStorage: {
    queryUsageAndQuota: function (ok) { ok(1234, 99999); }
  } } }, function (e, used, granted) { got = [e, used, granted]; });
  assert.deepStrictEqual(got, [null, 1234, 99999],
    "queryUsageAndQuota es la unica API de cuota con callback: la moderna es Promise");
}());


/* --- H-15: presupuesto, plan, rangos y ensure (H-8a) --- */

(function testBudgetIsMinOfCapAndFractionWithManualOverrides() {
  var MB = 1048576;
  assert.strictEqual(Cache.budget(0), Cache.TOPE_BYTES,
    "sin cuota declarada manda el tope absoluto");
  assert.strictEqual(Cache.budget(225 * MB), Math.floor(225 * MB * 0.5),
    "la caja declara 225 MB: la mitad, 112,5 MB, que es menos que el tope");
  assert.strictEqual(Cache.budget(2637 * MB), Cache.TOPE_BYTES,
    "el Smart TV declara 2.637 MB: manda el tope, no la mitad");
  assert.strictEqual(Cache.budget(225 * MB, { tope: 40 * MB }), 40 * MB,
    "el tope manual del operador prevalece");
  assert.strictEqual(Cache.budget(225 * MB, { fraccion: 0.1 }), Math.floor(22.5 * MB),
    "y la fraccion manual tambien");
}());

(function testPlanKeepsByPriorityAndStopsAtTheFirstThatDoesNotFit() {
  var pieces = [
    { id: "loop", residente: "si", prioridad: "2", bytes: "5" },
    { id: "stream", residente: "no", prioridad: "1", bytes: "1" },
    { id: "ruleta", residente: "si", prioridad: "1", bytes: "3" },
    { id: "pub", residente: "si", prioridad: "4", bytes: "6" },
    { id: "radio", residente: "si", prioridad: "5", bytes: "1" }
  ];
  var p = Cache.plan(pieces, 9);
  assert.deepStrictEqual(p.keep.map(function (x) { return x.id; }), ["ruleta", "loop"],
    "por prioridad: el incentivador antes que el loop, y la publicidad no entra");
  assert.deepStrictEqual(p.porRed.map(function (x) { return x.id; }), ["stream", "pub", "radio"],
    "lo no residente y lo que no entro van por red; la radio chica NO se cuela: el orden es del operador");
  assert.strictEqual(p.bytes, 8);
  p = Cache.plan(pieces, 100);
  assert.strictEqual(p.keep.length, 4, "con presupuesto entra todo lo residente");
  assert.deepStrictEqual(p.porRed.map(function (x) { return x.id; }), ["stream"]);
  p = Cache.plan([{ id: "a", residente: "si", prioridad: "x", bytes: "1" },
                  { id: "b", residente: "si", prioridad: "3", bytes: "1" }], 10);
  assert.deepStrictEqual(p.keep.map(function (x) { return x.id; }), ["b", "a"],
    "una prioridad ilegible va al final, no rompe el plan");
}());

(function testJoinAndPartAddressSegmentsByRange() {
  var a = new Uint8Array([1, 2, 3]).buffer;
  var b = new Uint8Array([4]).buffer;
  var c = new Uint8Array([5, 6]).buffer;
  var joined = Cache.join([a, b, c]);
  var record = { data: joined.data, rangos: joined.rangos };
  var v;
  assert.strictEqual(joined.data.byteLength, 6, "un solo ArrayBuffer con todo");
  assert.deepStrictEqual(joined.rangos, [[0, 3], [3, 1], [4, 2]], "y la tabla de rangos");
  v = Cache.part(record, 1);
  assert.strictEqual(v.length, 1);
  assert.strictEqual(v[0], 4, "la parte 1 es el segmento 1, sin copiar");
  assert.strictEqual(v.buffer, joined.data, "es una vista sobre el mismo buffer");
  v = Cache.part(record, 2);
  assert.deepStrictEqual([v[0], v[1]], [5, 6]);
  assert.strictEqual(Cache.part(record, 3), null, "fuera de rango: null");
  v = Cache.part({ data: a }, 0);
  assert.strictEqual(v.length, 3, "sin rangos, la vista es el registro entero (los guardados por v0)");
  assert.strictEqual(Cache.part(null, 0), null);
}());

/* Un XHR que devuelve ArrayBuffers de verdad, para que join() los pueda pegar. */
var ensureFiles = {};
var ensureFetched = [];
function EnsureXHR() { this.readyState = 0; this.status = 0; this.response = null; }
EnsureXHR.prototype.open = function (method, url) { this.url = url; };
EnsureXHR.prototype.send = function () {
  ensureFetched.push(this.url);
  this.readyState = 4;
  if (ensureFiles[this.url] === undefined) {
    this.status = 404; this.response = null;
  } else {
    this.status = 200; this.response = new Uint8Array(ensureFiles[this.url]).buffer;
  }
  if (this.onreadystatechange) { this.onreadystatechange(); }
};

(function testEnsureReadsWhatIsThereAndDownloadsTheRest() {
  var idb = fakeIdb();
  var db = null, told = [], summary = null, t = 100, got = null;
  ensureFiles["init.webm"] = [9, 9];
  ensureFiles["c1.webm"] = [1];
  ensureFiles["c2.webm"] = [2, 2];
  ensureFiles["loop.webm"] = [7, 7, 7];
  Cache.open({ idb: idb }, function (e, d) { db = d; });
  flush();
  /* El loop ya esta guardado (lo dejo la pagina de pruebas con el 84). */
  Cache.put(db, { key: "loop.aaaa", id: "loop", sha: "aaaa", mime: "video/webm",
                  bytes: 3, data: new Uint8Array([7, 7, 7]).buffer, at: 1 }, function () {});
  flush();
  Cache.ensure(db, [
    { id: "loop", key: "loop.aaaa", sha: "aaaa", mime: "video/webm", urls: ["loop.webm"], bytes: 3 },
    { id: "segs", key: "segs.bbbb", sha: "bbbb", mime: "video/webm",
      urls: ["init.webm", "c1.webm", "c2.webm"], bytes: 5 },
    { id: "rota", key: "rota.cccc", sha: "cccc", mime: "video/mp4", urls: ["no-esta.mp4"], bytes: 1 }
  ], { XHR: EnsureXHR, now: function () { return t; },
       onPiece: function (id, origen, ms, bytes, detalle) { told.push(id + ":" + origen + ":" + bytes + (detalle ? ":" + detalle : "")); } },
    function (s) { summary = s; });
  flush();
  assert(summary, "termina");
  assert.deepStrictEqual(told, ["loop:cache:3", "segs:red:5", "rota:error:0:HTTP 404 no-esta.mp4"],
    "cada pieza dice de donde salio: la guardada no toca la red, la nueva se baja, la rota se declara");
  assert.deepStrictEqual(ensureFetched, ["init.webm", "c1.webm", "c2.webm", "no-esta.mp4"],
    "las partes se bajan en orden y una a la vez; loop.webm no se pide");
  assert.deepStrictEqual([summary.hits, summary.downloaded, summary.failed, summary.bytes],
    [1, 1, ["rota"], 8]);
  Cache.get(db, "segs.bbbb", function (e, r) { got = r; });
  flush();
  assert.deepStrictEqual(got.rangos, [[0, 2], [2, 1], [3, 2]],
    "la representacion segmentada se guarda como UN registro con rangos");
  assert.strictEqual(got.bytes, 5);
  assert.deepStrictEqual(Array.prototype.slice.call(Cache.part(got, 2)), [2, 2],
    "y el rango 2 devuelve el segmento 2");
  /* Segunda pasada: todo desde la base, cero red. */
  told = []; ensureFetched = [];
  Cache.ensure(db, [
    { id: "loop", key: "loop.aaaa", sha: "aaaa", mime: "video/webm", urls: ["loop.webm"], bytes: 3 },
    { id: "segs", key: "segs.bbbb", sha: "bbbb", mime: "video/webm",
      urls: ["init.webm", "c1.webm", "c2.webm"], bytes: 5 }
  ], { XHR: EnsureXHR, now: function () { return t; },
       onPiece: function (id, origen) { told.push(id + ":" + origen); } },
    function (s) { summary = s; });
  flush();
  assert.deepStrictEqual(told, ["loop:cache", "segs:cache"], "la segunda vez nada sale de la red");
  assert.deepStrictEqual(ensureFetched, [], "ni un pedido");
  Cache.ensure(null, [{ id: "x", key: "x", urls: ["x"] }], {}, function (s) { summary = s; });
  assert.deepStrictEqual([summary.hits, summary.downloaded], [0, 0], "sin base, termina en el acto");
}());

(function testEnsureReportsAWriteThatDoesNotFit() {
  var idb = fakeIdb({ limit: 2 });
  var db = null, told = [], summary = null;
  ensureFiles["grande.webm"] = [1, 2, 3, 4];
  Cache.open({ idb: idb }, function (e, d) { db = d; });
  flush();
  Cache.ensure(db, [{ id: "grande", key: "grande.dddd", sha: "dddd", mime: "video/webm",
                      urls: ["grande.webm"], bytes: 4 }],
    { XHR: EnsureXHR, onPiece: function (id, origen, ms, bytes, detalle) { told.push(origen + ":" + detalle); } },
    function (s) { summary = s; });
  flush();
  assert.deepStrictEqual(told, ["error:guardar: QuotaExceededError"],
    "lo que no entra en la base se dice con el nombre del error, y la pieza va por red");
  assert.deepStrictEqual(summary.failed, ["grande"]);
}());

console.log("vgencache tests: OK");
