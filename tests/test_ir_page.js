"use strict";

/* ir.html: el lanzador para TV box. Es un ARCHIVO SUELTO que vive en otro
 * servidor, asi que lo critico es que (a) no dependa de nada al lado y (b) sus
 * destinos sean URLs absolutas: con rutas relativas, desde otro dominio, no
 * llega a ningun lado. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "ir.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "ir.html debe contener su script inline");
assert.strictEqual(/<script[^>]+src\s*=/i.test(page), false,
  "el lanzador es autocontenido: no puede cargar ningun archivo al lado");
assert(page.indexOf("https://iargen.com/player/") >= 0,
  "los destinos apuntan al player con URL absoluta");

function makeNode(name) {
  var node = { nodeName: name, childNodes: [], style: {}, className: "",
               value: "", firstChild: null, onclick: null, onkeydown: null,
               focused: false };
  node.appendChild = function (child) {
    node.childNodes.push(child);
    node.firstChild = node.childNodes[0];
    return child;
  };
  node.removeChild = function (child) {
    var index = node.childNodes.indexOf(child);
    if (index >= 0) { node.childNodes.splice(index, 1); }
    node.firstChild = node.childNodes.length ? node.childNodes[0] : null;
    return child;
  };
  node.focus = function () { node.focused = true; };
  node.blur = function () { node.focused = false; };
  return node;
}

var nodes = {};
function byId(id) {
  if (!nodes[id]) { nodes[id] = makeNode(id); }
  return nodes[id];
}

var listeners = [];
var documentStub = {
  documentElement: makeNode("html"),
  body: makeNode("BODY"),
  getElementById: byId,
  createElement: makeNode,
  createTextNode: function (value) {
    var node = makeNode("#text");
    node.data = value;
    return node;
  },
  addEventListener: function (name, fn) { listeners.push([name, fn]); }
};

var timers = [];
var windowStub = {
  innerWidth: 3840,
  location: { search: "", href: "" },
  setTimeout: function (fn) { timers.push(fn); return timers.length; },
  clearTimeout: function () { timers.pop(); },
  onresize: null
};

new Function("window", "document",
  inline[1] + "\nwindow.__t = { target: target, push: push, BASE: BASE," +
  " digitOf: digitOf, describe: describe, soltarCampo: soltarCampo," +
  " onKeyDown: onKeyDown, onKeyPress: onKeyPress };")
  (windowStub, documentStub);
var api = windowStub.__t;

/* La base es absoluta y termina en barra: es lo unico que hay que editar. */
assert.strictEqual(api.BASE, "https://iargen.com/player/");

/* Escribir una version se convierte en URL absoluta, con barra final. */
assert.strictEqual(api.target("v0"), "https://iargen.com/player/v0/");
assert.strictEqual(api.target("1280-15"), "https://iargen.com/player/1280-15/");
assert.strictEqual(api.target("/v0/"), "https://iargen.com/player/v0/");
assert.strictEqual(api.target("v0/?delay=400"),
  "https://iargen.com/player/v0/?delay=400");
assert.strictEqual(api.target("https://otro/lado/"), "https://otro/lado/",
  "una URL entera pasa tal cual");
assert.strictEqual(api.target("   "), "", "vacio no navega");

/* La leyenda se dibuja: 8 destinos mas la opcion de escribir. */
assert.strictEqual(byId("ops").childNodes.length, 9);

/* W-26: la raiz forzada a Canvas2D tiene tecla propia. Es un destino con
 * pregunta y sin ruta, asi que `target` no le puede pegar una barra final: si
 * lo hiciera saldria ".../?renderer=canvas2d/" y no llegaria a ningun lado. */
assert.strictEqual(api.target("?renderer=canvas2d"),
  "https://iargen.com/player/?renderer=canvas2d");

/* Un digito que no puede crecer navega al instante. */
api.push("3");
assert.strictEqual(windowStub.location.href,
  "https://iargen.com/player/1280-15/");

/* Y el 6 tambien: ningun codigo empieza con 6, asi que no espera. Esa es la
 * gracia del pedido -abrir la raiz sin WebGL de una tecla, sin escribir. */
windowStub.location.href = "";
api.push("6");
assert.strictEqual(windowStub.location.href,
  "https://iargen.com/player/?renderer=canvas2d");

/* Uno que si puede crecer espera, y el segundo digito completa el codigo:
 * es el caso de dos unidades que pidio el operador. */
windowStub.location.href = "";
api.push("9");
assert.strictEqual(windowStub.location.href, "", "el 9 solo no navega: espera");
api.push("0");
assert.strictEqual(windowStub.location.href,
  "https://iargen.com/player/v0/?delay=1600");

/* El 0 lleva el foco al campo de texto en vez de navegar. */
windowStub.location.href = "";
api.push("0");
assert.strictEqual(windowStub.location.href, "");
assert.strictEqual(byId("v").focused, true);

/* El teclado queda enganchado al documento (control remoto, sin mouse), por
 * los DOS eventos: H-22 sumo `keypress` como plan B. */
assert.strictEqual(listeners.length, 2);
assert.strictEqual(listeners[0][0], "keydown");
assert.strictEqual(listeners[1][0], "keypress");

/* --- H-22: el mando en un Smart TV con Android --- */

/* Cuatro caminos para leer un digito: hay WebViews que mandan keyCode 0 y solo
 * pueblan `key`, y del `keypress` a veces solo llega `charCode`. */
assert.strictEqual(api.digitOf({ keyCode: 51 }), "3");
assert.strictEqual(api.digitOf({ keyCode: 99 }), "3");
assert.strictEqual(api.digitOf({ keyCode: 0, key: "3" }), "3");
assert.strictEqual(api.digitOf({ keyCode: 0, code: "Digit3" }), "3");
assert.strictEqual(api.digitOf({ keyCode: 0, code: "Numpad3" }), "3");
assert.strictEqual(api.digitOf({ charCode: 51 }), "3");
assert.strictEqual(api.digitOf({ keyCode: 0, key: "Enter" }), "");

/* La pagina ESCRIBE lo que llego. Si el aparato no manda nada, la linea se
 * queda en 0 y eso ya es la respuesta. */
assert(/todavia no llego ninguna/.test(byId("tecla").firstChild.data),
  "antes de la primera tecla, la linea lo dice");
windowStub.location.href = "";
api.onKeyDown({ keyCode: 0, key: "3", target: { nodeName: "BODY" },
                preventDefault: function () {} });
assert(/key=3/.test(byId("tecla").firstChild.data),
  "y despues trae los campos crudos: " + byId("tecla").firstChild.data);
assert.strictEqual(windowStub.location.href,
  "https://iargen.com/player/1280-15/",
  "un digito que solo viene en `key` tiene que navegar igual");

/* El campo de texto se lleva TODOS los numeros mientras tenga el foco, y en un
 * Smart TV la navegacion espacial puede dejarselo sola al cargar (ya paso con
 * un <textarea> en H-20). Con el foco adentro no se dispara nada, pero la
 * pagina lo DICE en vez de quedarse muda. */
windowStub.location.href = "";
api.onKeyDown({ keyCode: 51, target: { nodeName: "INPUT" },
                preventDefault: function () {} });
assert.strictEqual(windowStub.location.href, "",
  "con el foco en el campo, los numeros son texto");
assert(/el foco esta en el campo/.test(byId("aviso").firstChild.data),
  "y la pagina lo avisa: " + byId("aviso").firstChild.data);

/* Volver saca el foco del campo. */
byId("v").focused = true;
api.onKeyDown({ keyCode: 8, target: { nodeName: "INPUT" },
                preventDefault: function () {} });
assert.strictEqual(byId("v").focused, false, "Volver suelta el campo");
assert.strictEqual(documentStub.body.focused, true, "y el foco vuelve al body");

/* Y arrancar la pagina ya lo suelta, sin que haya que apretar nada. */
byId("v").focused = true;
api.soltarCampo();
assert.strictEqual(byId("v").focused, false);

console.log("ir page tests (H-22): OK");
