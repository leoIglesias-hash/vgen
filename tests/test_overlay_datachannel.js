"use strict";
/* F7-3: canal de datos del overlay (frontend/datachannel.js).
 * Cubre la lista de INT-001 §13: longitud incorrecta, caracteres no
 * numericos, serial repetido, serial retrocedido, campo fuera de rango,
 * respuesta vacia, respuesta gigante; mas backoff acotado, token anti-cache
 * y stop() con abort del request en vuelo. */

var assert = require("assert");
var CHANNEL = require("../frontend/datachannel.js");

/* ---------- dobles de prueba deterministas ---------- */
function FakeOverlay() {
  this.digitCount = 4;
  this.applied = [];
  /* simula la validacion por campo del overlay real: "9934" con campo 9
   * de max 42 seria invalido; aca el patron "99" al final rechaza */
  this.setValues = function (digits) {
    if (digits.substring(2) === "99") return false;
    this.applied.push(digits);
    return true;
  };
}

function FakeXhr() {
  this.openedUrl = null;
  this.sent = false;
  this.aborted = false;
  this.readyState = 0;
  this.status = 0;
  this.responseText = "";
  this.onreadystatechange = null;
}
FakeXhr.prototype.open = function (method, url, async) {
  assert.strictEqual(method, "GET");
  assert.strictEqual(async, true);
  this.openedUrl = url;
};
FakeXhr.prototype.send = function () { this.sent = true; };
FakeXhr.prototype.abort = function () { this.aborted = true; };
FakeXhr.prototype.respond = function (status, text) {
  this.status = status;
  this.responseText = text;
  this.readyState = 4;
  this.onreadystatechange();
};

function Harness(options) {
  var self = this;
  this.overlay = new FakeOverlay();
  this.xhrs = [];
  this.timers = [];
  this.clock = 1000;
  var base = {
    intervalMs: 100,
    maxBackoffMs: 500,
    createXhr: function () {
      var xhr = new FakeXhr();
      self.xhrs.push(xhr);
      return xhr;
    },
    setTimer: function (fn, ms) {
      self.timers.push({ fn: fn, ms: ms, cleared: false });
      return self.timers.length - 1;
    },
    clearTimer: function (id) { self.timers[id].cleared = true; },
    now: function () { return self.clock++; }
  };
  var key;
  for (key in options || {}) base[key] = options[key];
  this.channel = CHANNEL.create("http://tv.local/data.txt", this.overlay, base);
}
Harness.prototype.lastXhr = function () {
  return this.xhrs[this.xhrs.length - 1];
};
Harness.prototype.lastTimer = function () {
  return this.timers[this.timers.length - 1];
};
Harness.prototype.fireTimer = function () {
  var timer = this.lastTimer();
  assert.ok(timer && !timer.cleared, "hay un timer pendiente");
  timer.fn();
};

/* ---------- create: argumentos insuficientes ---------- */
(function testCreateRejections() {
  assert.strictEqual(CHANNEL.create("", new FakeOverlay(), {}), null);
  assert.strictEqual(CHANNEL.create("http://x/", null, {}), null);
  assert.strictEqual(CHANNEL.create("http://x/", { digitCount: 4 }, {}), null,
    "overlay sin setValues");
  assert.strictEqual(
    CHANNEL.create("http://x/", { setValues: function () { return true; },
      digitCount: 0 }, {}), null, "sin digitos declarados");
}());

/* ---------- carga valida y cadencia normal ---------- */
(function testValidLoad() {
  var h = new Harness();
  h.channel.start();
  assert.strictEqual(h.xhrs.length, 1);
  assert.ok(h.lastXhr().openedUrl.indexOf("http://tv.local/data.txt?t=") === 0,
    "token anti-cache en URL limpia");
  h.lastXhr().respond(200, "00000001|0512\n");
  assert.deepStrictEqual(h.overlay.applied, ["0512"]);
  assert.strictEqual(h.channel.lastSerial, 1);
  assert.strictEqual(h.channel.lastError, "");
  assert.strictEqual(h.lastTimer().ms, 100, "cadencia normal tras exito");

  /* el proximo poll usa un token distinto */
  var firstUrl = h.lastXhr().openedUrl;
  h.fireTimer();
  assert.strictEqual(h.xhrs.length, 2);
  assert.notStrictEqual(h.lastXhr().openedUrl, firstUrl);

  /* serial repetido: se conserva el ultimo estado valido */
  h.lastXhr().respond(200, "00000001|0713\n");
  assert.deepStrictEqual(h.overlay.applied, ["0512"], "repetido no aplica");
  assert.ok(/repetido/.test(h.channel.lastError));
  assert.strictEqual(h.lastTimer().ms, 100,
    "contenido invalido mantiene cadencia normal, sin backoff");

  /* serial retrocedido */
  h.fireTimer();
  h.lastXhr().respond(200, "00000000|0713\n");
  assert.deepStrictEqual(h.overlay.applied, ["0512"]);
  assert.ok(/retrocedido|repetido/.test(h.channel.lastError));

  /* serial nuevo con campo fuera de rango: el serial NO se consume */
  h.fireTimer();
  h.lastXhr().respond(200, "00000002|0599\n");
  assert.deepStrictEqual(h.overlay.applied, ["0512"]);
  assert.ok(/fuera de rango/.test(h.channel.lastError));
  assert.strictEqual(h.channel.lastSerial, 1,
    "solo un dato aceptado avanza el serial");

  /* el mismo serial 2, ahora valido, entra */
  h.fireTimer();
  h.lastXhr().respond(200, "00000002|0713\n");
  assert.deepStrictEqual(h.overlay.applied, ["0512", "0713"]);
  assert.strictEqual(h.channel.lastSerial, 2);
}());

/* ---------- corpus de respuestas corruptas ---------- */
(function testCorruptResponses() {
  var giant = "", i;
  for (i = 0; i < 4096; i++) giant += "9";
  var cases = [
    ["", /longitud/],
    ["00000003|051\n", /longitud/],
    ["00000003|05123\n", /longitud/],
    [giant, /longitud/],
    ["00000003x0512\n", /forma/],
    ["00000003|0512x", /forma/],
    ["0000000a|0512\n", /serial no numerico/],
    ["00000003|05a2\n", /digito/],
    ["00000003|05 2\n", /digito/]
  ];
  var h = new Harness();
  h.channel.start();
  h.lastXhr().respond(200, "00000001|0512\n");
  for (i = 0; i < cases.length; i++) {
    h.fireTimer();
    h.lastXhr().respond(200, cases[i][0]);
    assert.ok(cases[i][1].test(h.channel.lastError),
      "caso " + i + ": " + h.channel.lastError);
    assert.deepStrictEqual(h.overlay.applied, ["0512"],
      "caso " + i + " no aplica nada");
    assert.strictEqual(h.channel.lastSerial, 1);
    assert.strictEqual(h.lastTimer().ms, 100);
  }
}());

/* ---------- backoff exponencial acotado ante error de red ---------- */
(function testNetworkBackoff() {
  var h = new Harness();
  h.channel.start();
  h.lastXhr().respond(500, "");
  assert.strictEqual(h.lastTimer().ms, 200, "primer fallo: 2x");
  h.fireTimer();
  h.lastXhr().respond(500, "");
  assert.strictEqual(h.lastTimer().ms, 400, "segundo fallo: 4x");
  h.fireTimer();
  h.lastXhr().respond(404, "");
  assert.strictEqual(h.lastTimer().ms, 500, "tercer fallo: techo");
  h.fireTimer();
  h.lastXhr().respond(500, "");
  assert.strictEqual(h.lastTimer().ms, 500, "el techo no se supera");
  assert.strictEqual(h.overlay.applied.length, 0);

  /* recuperacion: exito resetea el backoff */
  h.fireTimer();
  h.lastXhr().respond(200, "00000009|0512\n");
  assert.strictEqual(h.channel.failures, 0);
  assert.strictEqual(h.lastTimer().ms, 100);
  assert.deepStrictEqual(h.overlay.applied, ["0512"]);

  /* un send() que lanza cuenta como error de red */
  var h2 = new Harness({
    createXhr: function () {
      var xhr = new FakeXhr();
      xhr.send = function () { throw new Error("red caida"); };
      h2.xhrs.push(xhr);
      return xhr;
    }
  });
  h2.channel.start();
  assert.ok(/send fallo/.test(h2.channel.lastError));
  assert.strictEqual(h2.lastTimer().ms, 200);
}());

/* ---------- stop(): timer limpio y request en vuelo abortado ---------- */
(function testStop() {
  var h = new Harness();
  h.channel.start();
  h.lastXhr().respond(200, "00000001|0512\n");
  h.channel.stop();
  assert.strictEqual(h.lastTimer().cleared, true, "timer cancelado");

  var h2 = new Harness();
  h2.channel.start();
  assert.strictEqual(h2.lastXhr().sent, true);
  h2.channel.stop();
  assert.strictEqual(h2.lastXhr().aborted, true, "request en vuelo abortado");
  /* una respuesta tardia tras stop() no aplica nada ni re-agenda */
  h2.lastXhr().respond(200, "00000005|0512\n");
  assert.strictEqual(h2.overlay.applied.length, 0);
  assert.strictEqual(h2.timers.length, 0);

  /* start tras stop vuelve a operar */
  h2.channel.start();
  h2.lastXhr().respond(200, "00000006|0512\n");
  assert.deepStrictEqual(h2.overlay.applied, ["0512"]);
}());

/* ---------- URL con query existente usa & ---------- */
(function testQuerySeparator() {
  var overlay = new FakeOverlay();
  var xhrs = [];
  var channel = CHANNEL.create("http://tv.local/d.txt?v=2", overlay, {
    intervalMs: 100,
    createXhr: function () {
      var xhr = new FakeXhr();
      xhrs.push(xhr);
      return xhr;
    },
    setTimer: function () { return 0; },
    clearTimer: function () { return 0; },
    now: function () { return 7; }
  });
  channel.start();
  assert.strictEqual(xhrs[0].openedUrl, "http://tv.local/d.txt?v=2&t=7");
  channel.stop();
}());

console.log("OK test_overlay_datachannel");
