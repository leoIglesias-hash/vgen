"use strict";
/* INT-006-B: feed de texto standalone (frontend/textfeed.js).
 *  - create() todo-o-nada: capa sin setText, campos malformados, ids
 *    duplicados o no declarados en la capa -> null;
 *  - create() prueba cada id con setText(id, "") -> campos arrancan vacios;
 *  - digitCount = suma de anchos en orden de declaracion;
 *  - setValues() valida TODO antes de escribir (tipo, longitud exacta,
 *    solo digitos ASCII): un payload invalido no toca la capa (INV-7);
 *  - setValues() reparte el payload por tramos consecutivos via setText;
 *  - el feed satisface la interfaz que consume datachannel.js SIN tocarlo
 *    (digitCount + setValues, mismo contrato que un overlay). */

var assert = require("assert");
var TF = require("../frontend/textfeed.js");
var TL = require("../frontend/textlayer.js");
var DC = require("../frontend/datachannel.js");

/* ---- capa sintetica: registra cada setText y conoce sus ids ---- */
function MockCapa(ids) {
  var i;
  this.known = {};
  this.calls = [];
  for (i = 0; i < ids.length; i++) this.known["t" + ids[i]] = true;
}
MockCapa.prototype.setText = function (id, str) {
  if (!Object.prototype.hasOwnProperty.call(this.known, "t" + id)) {
    return false;
  }
  this.calls.push({ id: id, str: str });
  return true;
};

function fields3() {
  return [{ id: 1, width: 2 }, { id: 2, width: 3 }, { id: "x", width: 1 }];
}

/* ---- create(): rechazos todo-o-nada ---- */
(function () {
  var capa = new MockCapa([1, 2, "x"]);
  assert.strictEqual(TF.create(null, fields3()), null, "capa null");
  assert.strictEqual(TF.create({}, fields3()), null, "capa sin setText");
  assert.strictEqual(TF.create(capa, null), null, "campos null");
  assert.strictEqual(TF.create(capa, []), null, "campos vacios");
  assert.strictEqual(TF.create(capa, "12"), null, "campos no lista");
  (function () {
    var muchos = [], i;
    for (i = 0; i < 65; i++) muchos.push({ id: i, width: 1 });
    assert.strictEqual(TF.create(capa, muchos), null, "mas de 64 campos");
  })();
  assert.strictEqual(TF.create(capa, [null]), null, "campo null");
  assert.strictEqual(TF.create(capa, [{ id: -1, width: 2 }]), null,
    "id negativo");
  assert.strictEqual(TF.create(capa, [{ id: 1.5, width: 2 }]), null,
    "id no entero");
  assert.strictEqual(TF.create(capa, [{ id: "", width: 2 }]), null,
    "id string vacio");
  assert.strictEqual(TF.create(capa, [{ id: "a\u0007b", width: 2 }]), null,
    "id con caracter de control");
  assert.strictEqual(
    TF.create(capa, [{ id: 1, width: 2 }, { id: 1, width: 3 }]), null,
    "id duplicado");
  assert.strictEqual(TF.create(capa, [{ id: 1, width: 0 }]), null,
    "width 0");
  assert.strictEqual(TF.create(capa, [{ id: 1, width: 2.5 }]), null,
    "width no entero");
  assert.strictEqual(TF.create(capa, [{ id: 1, width: 17 }]), null,
    "width sobre el techo");
  assert.strictEqual(TF.create(capa, [{ id: 1, width: "2" }]), null,
    "width string");
  assert.strictEqual(capa.calls.length, 0,
    "una forma invalida no llega a probar la capa");
  assert.strictEqual(TF.create(capa, [{ id: 9, width: 2 }]), null,
    "id no declarado en la capa");
})();

/* ---- create(): probe determinista y digitCount ---- */
(function () {
  var capa = new MockCapa([1, 2, "x"]);
  var feed = TF.create(capa, fields3());
  assert(feed, "campos validos crean el feed");
  assert.strictEqual(feed.digitCount, 6, "digitCount = 2+3+1");
  assert.strictEqual(capa.calls.length, 3, "un probe por campo");
  assert.deepStrictEqual(capa.calls[0], { id: 1, str: "" });
  assert.deepStrictEqual(capa.calls[1], { id: 2, str: "" });
  assert.deepStrictEqual(capa.calls[2], { id: "x", str: "" },
    "create deja los campos declarados vacios");
})();

/* ---- setValues(): validacion completa ANTES de escribir ---- */
(function () {
  var capa = new MockCapa([1, 2, "x"]);
  var feed = TF.create(capa, fields3());
  capa.calls.length = 0;
  assert.strictEqual(feed.setValues(123456), false, "no string");
  assert.strictEqual(feed.setValues(null), false, "null");
  assert.strictEqual(feed.setValues("12345"), false, "corto");
  assert.strictEqual(feed.setValues("1234567"), false, "largo");
  assert.strictEqual(feed.setValues("12345a"), false, "letra");
  assert.strictEqual(feed.setValues("12 456"), false, "espacio");
  assert.strictEqual(feed.setValues("12345٠"), false,
    "digito no ASCII (arabe)");
  assert.strictEqual(feed.setValues("-12345"), false, "signo");
  assert.strictEqual(capa.calls.length, 0,
    "ningun rechazo escribio en la capa (todo-o-nada)");
  assert.strictEqual(feed.setValues("123456"), true, "payload valido");
  assert.strictEqual(capa.calls.length, 3);
  assert.deepStrictEqual(capa.calls[0], { id: 1, str: "12" });
  assert.deepStrictEqual(capa.calls[1], { id: 2, str: "345" });
  assert.deepStrictEqual(capa.calls[2], { id: "x", str: "6" },
    "el payload se reparte por tramos consecutivos en orden");
  assert.strictEqual(feed.setValues("000000"), true, "ceros validos");
})();

/* ---- integracion con la capa REAL de textlayer.js ---- */
(function () {
  var capa = TL.create([
    { id: 1, x: 0, y: 0, w: 8, h: 4, size: 2, color: "#fff", text: "VIEJO" },
    { id: 2, x: 10, y: 0, w: 8, h: 4, size: 2, color: "#fff" },
    { id: 3, x: 20, y: 0, w: 8, h: 4, size: 2, color: "#fff" }
  ]);
  assert(capa, "capa real creada");
  var feed = TF.create(capa, [
    { id: 1, width: 2 }, { id: 2, width: 2 }, { id: 3, width: 2 }
  ]);
  assert(feed, "feed sobre la capa real");
  assert.strictEqual(capa._text[0], "",
    "create vacio el texto inicial (estado determinista)");
  assert.strictEqual(feed.digitCount, 6);
  assert.strictEqual(feed.setValues("420733"), true);
  assert.strictEqual(capa._text[0], "42");
  assert.strictEqual(capa._text[1], "07");
  assert.strictEqual(capa._text[2], "33");
  assert.strictEqual(feed.setValues("42x733"), false);
  assert.strictEqual(capa._text[1], "07", "el rechazo conservo el estado");
  assert.strictEqual(TF.create(capa, [{ id: 4, width: 2 }]), null,
    "id ausente en la capa real -> null");
})();

/* ---- compatibilidad con datachannel.js (que NO se toca) ---- */
(function () {
  var capa = new MockCapa([1, 2, "x"]);
  var feed = TF.create(capa, fields3());
  var canal = DC.create("data.txt", feed, {
    createXhr: function () { return {}; },
    setTimer: function () { return 1; },
    clearTimer: function () {},
    now: function () { return 0; }
  });
  assert(canal, "el canal acepta el feed como overlay");
  capa.calls.length = 0;
  assert.strictEqual(canal._handleText("00000001|123456\n"), true,
    "payload valido del canal escribe via el feed");
  assert.strictEqual(capa.calls.length, 3);
  assert.strictEqual(canal.lastSerial, 1);
  assert.strictEqual(canal._handleText("00000002|12345a\n"), false,
    "digito invalido: el canal lo corta antes del feed");
  assert.strictEqual(canal._handleText("00000001|654321\n"), false,
    "serial repetido rechazado");
  assert.strictEqual(capa.calls.length, 3,
    "los rechazos del canal no tocaron la capa");
})();

console.log("textfeed tests: OK");
