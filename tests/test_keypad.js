"use strict";

/* keypad.js: el mando numerico de las paginas de diagnostico.
 * Lo que importa probar es la regla del retardo: solo se espera cuando el
 * digito PUEDE ser el comienzo de un codigo mas largo. Si esa regla se rompe,
 * en un control remoto todo se vuelve lento sin motivo. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var source = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "keypad.js"), "utf8");
var sandbox = { window: undefined, document: undefined };
new Function("window", "document", source + "\nwindow.ASCLKeypad = ASCLKeypad;")
  (sandbox, undefined);
var ASCLKeypad = sandbox.ASCLKeypad;

function fakeHost() {
  var pending = null;
  return {
    setTimeout: function (fn) { pending = fn; return 1; },
    clearTimeout: function () { pending = null; },
    run: function () { var fn = pending; pending = null; if (fn) { fn(); } },
    waiting: function () { return pending !== null; }
  };
}

function build(codes) {
  var fired = [];
  var host = fakeHost();
  var actions = codes.map(function (code) {
    return { code: code, run: function () { fired.push(code); } };
  });
  var pad = ASCLKeypad.create({ actions: actions, attach: false, host: host,
                                delay: 900 });
  return { pad: pad, fired: fired, host: host };
}

/* Un digito que no puede crecer dispara AL INSTANTE. */
var simple = build(["1", "2", "3"]);
assert.strictEqual(simple.pad.push("2"), "ok");
assert.deepStrictEqual(simple.fired, ["2"]);
assert.strictEqual(simple.host.waiting(), false,
  "sin codigos largos no hay razon para esperar");

/* Un digito que SI puede crecer espera, y al vencer el plazo dispara el corto. */
var mixed = build(["1", "5", "90", "91"]);
assert.strictEqual(mixed.pad.push("5"), "ok", "el 5 no es prefijo de nada");
assert.deepStrictEqual(mixed.fired, ["5"]);
assert.strictEqual(mixed.pad.push("9"), "espera", "el 9 puede volverse 90 o 91");
assert.strictEqual(mixed.host.waiting(), true);
assert.strictEqual(mixed.pad.push("1"), "ok", "9 + 1 completa un codigo");
assert.deepStrictEqual(mixed.fired, ["5", "91"]);

/* Dos digitos compuestos, como pidio el operador: 9 y luego 0. */
var compuesto = build(["1", "90", "91"]);
compuesto.pad.push("9");
compuesto.pad.push("0");
assert.deepStrictEqual(compuesto.fired, ["90"]);

/* OK dispara sin esperar el plazo. */
var okKey = build(["1", "10"]);
assert.strictEqual(okKey.pad.push("1"), "espera");
assert.strictEqual(okKey.pad.flush(), "ok", "OK no espera al reloj");
assert.deepStrictEqual(okKey.fired, ["1"]);

/* Volver/Escape limpia el buffer sin disparar nada. */
var cancel = build(["1", "10"]);
cancel.pad.push("1");
cancel.pad.clear();
assert.deepStrictEqual(cancel.fired, []);
assert.strictEqual(cancel.host.waiting(), false);

/* Un codigo inexistente no rompe ni deja basura en el buffer. */
var unknown = build(["1"]);
assert.strictEqual(unknown.pad.push("7"), "nada");
assert.deepStrictEqual(unknown.fired, []);

/* Los remotos mandan los digitos por keyCode; tambien se aceptan los del pad. */
assert.strictEqual(ASCLKeypad.digitOf({ keyCode: 55 }), "7");
assert.strictEqual(ASCLKeypad.digitOf({ keyCode: 103 }), "7");
assert.strictEqual(ASCLKeypad.digitOf({ keyCode: 65 }), "");

/* Con el foco en un campo de texto, los numeros son texto y no ordenes. */
var typing = build(["1", "2"]);
typing.pad.onKeyDown({ keyCode: 50, target: { nodeName: "input" } });
assert.deepStrictEqual(typing.fired, [],
  "escribir en un campo no debe disparar acciones");
typing.pad.onKeyDown({ keyCode: 50, target: { nodeName: "BODY" },
                       preventDefault: function () {} });
assert.deepStrictEqual(typing.fired, ["2"]);

console.log("keypad tests: OK");
