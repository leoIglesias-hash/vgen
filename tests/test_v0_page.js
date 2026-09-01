"use strict";

/* H-10: la pagina que reproduce el pack v0 y reporta lo que el aparato hizo.
 * Se ejecuta su script inline contra un DOM minimo: interesa que lea el
 * manifiesto TABULADO (nunca JSON), que arme una fila por pieza y que el
 * reporte salga en texto plano copiable desde una TV. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var pagePath = path.join(__dirname, "..", "frontend", "v0.html");
var page = fs.readFileSync(pagePath, "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "v0.html debe contener su controlador inline");
assert(page.indexOf("MANIFEST.tsv") >= 0,
  "la pagina lee el manifiesto tabulado del pack");
assert.strictEqual(/\bJSON\s*\./.test(page), false,
  "el manifiesto de runtime no puede ser JSON: el gate ES5 lo prohibe");

var MANIFEST = [
  "# pack v0 - ASCILINE-hybrid - docs/EMISION-V0.md",
  "# master\t" + new Array(65).join("a"),
  "# base\t1280x720\t15 fps\t225 cuadros",
  "# id\trole\tmime\tfile\tbytes\tsha256\tnote",
  ["v0-h264-baseline", "base", 'video/mp4; codecs="avc1.42E01F"',
   "v0-h264-baseline.mp4", "4130240", "aa", "piso"].join("\t"),
  ["v0-h264-main", "base", 'video/mp4; codecs="avc1.4D401F"',
   "v0-h264-main.mp4", "3900000", "bb", "detector"].join("\t"),
  ["v0-vp9", "base", 'video/webm; codecs="vp9"',
   "v0-vp9.webm", "2400000", "cc", "banda"].join("\t"),
  ["v0-vp9-alpha", "alpha", 'video/webm; codecs="vp9"',
   "v0-vp9-alpha.webm", "900000", "dd", "alfa"].join("\t")
].join("\n") + "\n";

function makeNode(name) {
  var node = {
    nodeName: name,
    childNodes: [],
    style: {},
    className: "",
    value: "",
    firstChild: null,
    onclick: null,
    currentTime: 0,
    src: ""
  };
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
  node.addEventListener = function () {};
  node.removeEventListener = function () {};
  node.canPlayType = function (mime) {
    return mime.indexOf("vp9") >= 0 ? "" : "probably";
  };
  node.load = function () {};
  node.play = function () {};
  node.pause = function () {};
  return node;
}

var nodes = {};
function byId(id) {
  if (!nodes[id]) { nodes[id] = makeNode(id); }
  return nodes[id];
}

var requested = [];
function FakeXHR() {
  this.readyState = 0;
  this.status = 0;
  this.responseText = "";
}
FakeXHR.prototype.open = function (method, url) { this.url = url; };
FakeXHR.prototype.send = function () {
  requested.push(this.url);
  this.readyState = 4;
  this.status = 200;
  this.responseText = MANIFEST;
  if (this.onreadystatechange) { this.onreadystatechange(); }
};

var documentStub = {
  documentElement: makeNode("html"),
  getElementById: byId,
  createElement: makeNode,
  createTextNode: function (value) {
    var node = makeNode("#text");
    node.data = value;
    return node;
  }
};

var windowStub = {
  innerWidth: 3840,
  innerHeight: 2160,
  devicePixelRatio: 1,
  location: { search: "" },
  setTimeout: function () { return 0; },
  clearTimeout: function () {},
  indexedDB: {},
  URL: null,
  MediaSource: null,
  onresize: null
};

var navigatorStub = { userAgent: "fake-tv-box" };
var screenStub = { width: 1280, height: 720 };

var run = new Function("window", "document", "navigator", "screen",
                       "XMLHttpRequest", inline[1]);
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR);

assert.strictEqual(requested.length, 1, "la pagina pide el manifiesto una vez");
assert(/MANIFEST\.tsv$/.test(requested[0]), "pide MANIFEST.tsv");

var filas = byId("filas");
assert.strictEqual(filas.childNodes.length, 4,
  "una fila por pieza del pack, incluida la de alfa");

var reporte = byId("report").value;
assert(reporte.indexOf("# pack v0") === 0, "el reporte arranca identificandose");
assert(reporte.indexOf("panel\t1280x720") >= 0,
  "el reporte distingue el panel real de la superficie del WebView");
assert(reporte.indexOf("superficie 3840x2160") >= 0,
  "la superficie que el WebView entrega es parte del diagnostico");
assert(reporte.indexOf("{") < 0 && reporte.indexOf("[") < 0,
  "el reporte es texto plano: se lee y se copia desde una TV");

/* HUD proporcional: sin esto el texto es ilegible en una superficie 4K sobre
 * un panel de 720p (medido en DIAG-003). */
assert(/px$/.test(documentStub.documentElement.style.fontSize),
  "la pagina escala su tipografia a la superficie del WebView");

/* La pieza de alfa NO entra en la corrida automatica: se mira, y el veredicto
 * de imagen lo firma el operador. */
assert(page.indexOf("alphaBg") >= 0 && page.indexOf("runAlpha") >= 0,
  "la prueba de alfa tiene su propio disparador y su fondo de color");

console.log("v0 page tests: OK");
