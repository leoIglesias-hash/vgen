"use strict";

/* H-13: vgenfeed.js abre las tres puertas del paquete (Blob concatenado, MSE,
 * cambio por src). Se prueba entero sin navegador: XHR, MediaSource,
 * SourceBuffer, Blob, URL y el reloj son falsos e inyectados por hooks.
 *
 * Lo que importa verificar no es que "llame a appendBuffer" sino DOS reglas
 * que un WebView castiga si se rompen: nunca anexar mientras el buffer esta
 * `updating` (InvalidStateError), y anexar en el orden pedido. */

var assert = require("assert");
var Feed = require("../frontend/vgenfeed.js");

/* --- dobles --- */

var files = {};                 /* url -> "bytes" (un string alcanza) */
var fetched = [];               /* orden real de pedidos */
function FakeXHR() { this.readyState = 0; this.status = 0; this.response = null; }
FakeXHR.prototype.open = function (method, url) { this.url = url; };
FakeXHR.prototype.send = function () {
  fetched.push(this.url);
  this.readyState = 4;
  if (files[this.url] === undefined) {
    this.status = 404; this.response = null;
  } else {
    this.status = 200; this.response = files[this.url];
  }
  if (this.onreadystatechange) { this.onreadystatechange(); }
};

function FakeSourceBuffer(mime) {
  this.mime = mime;
  this.mode = "segments";
  this.updating = false;
  this.appended = [];
  this.listeners = {};
}
FakeSourceBuffer.prototype.addEventListener = function (name, fn) {
  this.listeners[name] = fn;
};
FakeSourceBuffer.prototype.removeEventListener = function (name) {
  delete this.listeners[name];
};
FakeSourceBuffer.prototype.appendBuffer = function (bytes) {
  if (this.updating) {
    throw new Error("InvalidStateError: appendBuffer mientras updating");
  }
  this.updating = true;
  this.appended.push(bytes);
};
/* El aparato termina de digerir: solo entonces se puede anexar otro. */
FakeSourceBuffer.prototype.digest = function () {
  assert(this.updating, "digest sin anexo pendiente");
  this.updating = false;
  if (this.listeners.updateend) { this.listeners.updateend(); }
};

function FakeMediaSource() {
  this.readyState = "closed";
  this.buffers = [];
  this.ended = false;
  this.listeners = {};
}
FakeMediaSource.isTypeSupported = function (mime) {
  return mime.indexOf("avc1") >= 0;
};
FakeMediaSource.prototype.addEventListener = function (name, fn) {
  this.listeners[name] = fn;
};
FakeMediaSource.prototype.addSourceBuffer = function (mime) {
  var sb = new FakeSourceBuffer(mime);
  this.buffers.push(sb);
  return sb;
};
FakeMediaSource.prototype.endOfStream = function () {
  assert.strictEqual(this.readyState, "open");
  this.ended = true;
  this.readyState = "ended";
};
FakeMediaSource.prototype.open = function () {
  this.readyState = "open";
  if (this.listeners.sourceopen) { this.listeners.sourceopen(); }
};

var created = [];
var revoked = [];
var fakeURL = {
  createObjectURL: function (thing) {
    var url = "blob:fake/" + created.length;
    created.push(thing);
    return url;
  },
  revokeObjectURL: function (url) { revoked.push(url); }
};

function FakeBlob(parts, options) {
  this.parts = parts;
  this.type = options ? options.type : "";
}

function fakeVideo() {
  var v = { src: "", currentTime: 0, loads: 0, plays: 0 };
  v.load = function () { v.loads++; };
  v.play = function () { v.plays++; };
  return v;
}

/* Reloj y setTimeout falsos: el test avanza el tiempo a mano. */
function fakeClock() {
  var t = 0, queue = [];
  return {
    now: function () { return t; },
    host: {
      setTimeout: function (fn, ms) {
        queue.push({ at: t + ms, fn: fn });
        return queue.length;
      },
      clearTimeout: function () {}
    },
    run: function (until) {
      var item;
      while (queue.length && queue[0].at <= until) {
        item = queue.shift();
        t = item.at;
        item.fn();
      }
      t = until;
    }
  };
}

var host = { MediaSource: FakeMediaSource, URL: fakeURL, Blob: FakeBlob,
             SourceBuffer: { prototype: { changeType: function () {} } } };
var hooks = { host: host, XHR: FakeXHR };

/* --- getBytes / getAll --- */

(function testGetBytesReportsHttpErrorsAsText() {
  var got = null;
  files["a"] = "AAA";
  Feed.getBytes("a", function (error, bytes) { got = [error, bytes]; }, hooks);
  assert.deepStrictEqual(got, [null, "AAA"]);
  Feed.getBytes("nada", function (error, bytes) { got = [error, bytes]; }, hooks);
  assert.strictEqual(got[1], null);
  assert(/^HTTP 404/.test(got[0]), "el error es un texto corto, no una excepcion");
  assert.strictEqual(Feed.getBytes("a", function () {}, { XHR: null }), null,
    "sin XMLHttpRequest devuelve null y avisa por el callback");
}());

(function testGetAllKeepsOrderAndStopsAtFirstError() {
  var got = null;
  files["init"] = "I"; files["s1"] = "1"; files["s2"] = "2";
  fetched = [];
  Feed.getAll(["init", "s1", "s2"], function (error, parts) {
    got = [error, parts];
  }, hooks);
  assert.deepStrictEqual(got, [null, ["I", "1", "2"]]);
  assert.deepStrictEqual(fetched, ["init", "s1", "s2"],
    "se piden en orden, uno a la vez");
  fetched = [];
  Feed.getAll(["init", "falta", "s2"], function (error, parts) {
    got = [error, parts];
  }, hooks);
  assert(/falta/.test(got[0]));
  assert.deepStrictEqual(got[1], ["I"], "lo bajado hasta el error se entrega");
  assert.deepStrictEqual(fetched, ["init", "falta"],
    "despues del error no se pide nada mas");
}());

/* --- camino A: concat --- */

(function testConcatBuildsOneBlobWithTheMime() {
  var blob = Feed.concat(["I", "1", "2"], 'video/mp4; codecs="avc1.42C01F"', hooks);
  assert(blob instanceof FakeBlob);
  assert.deepStrictEqual(blob.parts, ["I", "1", "2"],
    "init primero, segmentos despues, sin tocar los bytes");
  assert.strictEqual(blob.type, 'video/mp4; codecs="avc1.42C01F"');
  assert.strictEqual(Feed.concat(["I"], "video/mp4",
    { host: {}, Blob: function () { throw new Error("sin Blob"); } }),
    null, "si el Blob no se puede construir devuelve null, no explota");
  assert.strictEqual(Feed.objectUrl(blob, hooks), "blob:fake/0");
  Feed.revoke("blob:fake/0", hooks);
  assert.deepStrictEqual(revoked, ["blob:fake/0"]);
}());

/* --- deteccion --- */

(function testDetection() {
  assert.strictEqual(Feed.mseSupport('video/mp4; codecs="avc1.42C01F"', hooks), "si");
  assert.strictEqual(Feed.mseSupport('video/webm; codecs="vp9"', hooks), "no");
  assert.strictEqual(Feed.mseSupport("video/mp4", { host: {} }), "no",
    "sin MediaSource la respuesta es no, sin excepcion");
  assert.strictEqual(Feed.hasChangeType(hooks), true);
  assert.strictEqual(Feed.hasChangeType({ host: { SourceBuffer: {} } }), false);
  assert.strictEqual(Feed.hasChangeType({ host: {} }), false);
}());

/* --- camino B: feedMse encadenado por updateend --- */

(function testFeedMseAppendsOneAtATimeInOrder() {
  var video = fakeVideo();
  var log = [];
  var handle, ms, sb;
  files["init"] = "I"; files["s1"] = "1"; files["s2"] = "2"; files["s3"] = "3";
  fetched = [];
  created = [];
  handle = Feed.feedMse(video, 'video/mp4; codecs="avc1.42C01F"',
    ["init", "s1", "s2", "s3"], {
      host: host, XHR: FakeXHR,
      onOpen: function () { log.push("open"); },
      onAppend: function (index, bytes) { log.push("append " + index + "=" + bytes); },
      onDone: function () { log.push("done"); },
      onError: function (why) { log.push("error " + why); }
    });
  assert(handle && handle.mediaSource, "devuelve el MediaSource");
  ms = handle.mediaSource;
  assert.strictEqual(video.src, "blob:fake/0", "el <video> apunta al MediaSource");
  assert.strictEqual(video.loads, 1);
  assert.strictEqual(video.plays, 1, "arranca solo, salvo play:false");
  assert.deepStrictEqual(fetched, [], "nada se pide antes de sourceopen");

  ms.open();
  sb = ms.buffers[0];
  assert.strictEqual(sb.mime, 'video/mp4; codecs="avc1.42C01F"');
  assert.strictEqual(sb.mode, "segments", "sin pedirlo, el modo queda como esta");
  assert.deepStrictEqual(log, ["open", "append 0=I"]);
  assert.deepStrictEqual(fetched, ["init"],
    "el segmento siguiente NO se pide hasta que el buffer digiera el anterior");
  assert.deepStrictEqual(sb.appended, ["I"]);

  sb.digest();
  assert.deepStrictEqual(fetched, ["init", "s1"]);
  assert.deepStrictEqual(sb.appended, ["I", "1"]);
  sb.digest();
  sb.digest();
  assert.deepStrictEqual(sb.appended, ["I", "1", "2", "3"], "orden de anexo = orden pedido");
  assert.strictEqual(ms.ended, false, "endOfStream solo despues del ultimo updateend");
  sb.digest();
  assert.strictEqual(ms.ended, true);
  assert.strictEqual(log[log.length - 1], "done");
  assert.strictEqual(log.indexOf("error"), -1);
}());

(function testFeedMseSequenceModeAndAbort() {
  var video = fakeVideo();
  var handle, ms, sb, warned = "";
  fetched = [];
  handle = Feed.feedMse(video, 'video/mp4; codecs="avc1.42C01F"', ["init", "s1", "s2"],
    { host: host, XHR: FakeXHR, mode: "sequence", play: false,
      onWarn: function (w) { warned = w; } });
  assert.strictEqual(video.plays, 0, "play:false no arranca");
  ms = handle.mediaSource;
  ms.open();
  sb = ms.buffers[0];
  assert.strictEqual(sb.mode, "sequence",
    "mode:sequence reescribe tiempos en orden de anexo: es lo que un bucle o un intercambio necesita");
  assert.strictEqual(warned, "");
  sb.digest();
  assert.deepStrictEqual(sb.appended, ["I", "1"]);
  revoked = [];
  handle.abort();
  sb.digest();
  assert.deepStrictEqual(sb.appended, ["I", "1"], "despues de abort no se anexa mas");
  assert.strictEqual(ms.ended, false);
  assert.deepStrictEqual(revoked, [handle.url], "abort libera el object URL");
}());

(function testFeedMseSurfacesErrors() {
  var video = fakeVideo();
  var errors = [];
  var handle, ms, sb;
  files["rota"] = undefined; delete files["rota"];
  handle = Feed.feedMse(video, "video/mp4", ["init", "rota", "s2"],
    { host: host, XHR: FakeXHR, onError: function (w) { errors.push(w); } });
  ms = handle.mediaSource;
  ms.open();
  sb = ms.buffers[0];
  sb.digest();
  assert.strictEqual(errors.length, 1);
  assert(/HTTP 404 rota/.test(errors[0]), "un segmento que falta se reporta con su URL");
  assert.deepStrictEqual(sb.appended, ["I"]);
  assert.strictEqual(ms.ended, false, "no se cierra un stream a medias");

  assert.strictEqual(Feed.feedMse(video, "video/mp4", ["init"], { host: {} }), null,
    "sin MediaSource devuelve null: el que llama decide el otro camino");
}());

/* --- camino C: switchTo mide pedido -> primer avance --- */

(function testSwitchToMeasuresFirstAdvance() {
  var clock = fakeClock();
  var video = fakeVideo();
  var got = null;
  Feed.switchTo(video, "pieza.webm", { host: clock.host, now: clock.now, step: 20 },
    function (ms) { got = ms; });
  assert.strictEqual(video.src, "pieza.webm");
  assert.strictEqual(video.loads, 1);
  assert.strictEqual(video.plays, 1);
  clock.run(300);
  assert.strictEqual(got, null, "sin avance de currentTime no hay medicion");
  video.currentTime = 0.066;
  clock.run(400);
  assert.strictEqual(got, 320, "pedido -> primer avance, con la resolucion del sondeo");
}());

(function testSwitchToGivesUp() {
  var clock = fakeClock();
  var video = fakeVideo();
  var got = null;
  Feed.switchTo(video, "pieza.mp4", { host: clock.host, now: clock.now,
                                      step: 100, timeout: 1000 },
    function (ms) { got = ms; });
  clock.run(1500);
  assert.strictEqual(got, -1, "-1 cuando no arranca dentro del limite");
  assert.strictEqual(Feed.switchTo(video, "x", { host: {} }, function (ms) { got = ms; }),
    null);
  assert.strictEqual(got, -1, "sin setTimeout avisa -1 en el acto");
}());

console.log("vgenfeed tests: OK");
