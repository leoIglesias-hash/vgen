"use strict";

/* H-10: la pagina que reproduce el pack v0 y reporta lo que el aparato hizo.
 * Se ejecuta su script inline contra un DOM minimo. Lo que se verifica no es
 * "que exista un boton" sino las dos reglas que la hacen usable en un TV BOX:
 * una sola pantalla sin scroll, y una accion por tecla numerica. */

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

/* --- Reglas de pantalla (pedido del operador: en una TV el scroll se pierde) */

assert(/html,\s*body\s*\{[^}]*overflow:\s*hidden/.test(page),
  "la pagina no puede scrollear: todo tiene que entrar en una pantalla");
assert.strictEqual((page.match(/<video\s+id=/g) || []).length, 1,
  "una sola etiqueta <video>: todas las piezas se reproducen en el mismo lugar");
assert(page.indexOf('<div id="side">') >= 0,
  "la tabla va AL LADO del video, no debajo, o hay que scrollear para verla");
assert(page.indexOf("function everything()") >= 0,
  "correr todo tiene que incluir progresivas, alfa y empaquetados");

var MANIFEST = [
  "# pack v0 - ASCILINE-hybrid - docs/EMISION-V0.md",
  "# master\t" + new Array(65).join("a"),
  "# base\t1280x720\t15 fps\t231 cuadros",
  "# id\trole\tmime\tfile\tbytes\tsha256\tnote",
  ["v0-h264-baseline", "base", 'video/mp4; codecs="avc1.42E01F"',
   "v0-h264-baseline.mp4", "9551715", "aa", "piso"].join("\t"),
  ["v0-h264-main", "base", 'video/mp4; codecs="avc1.4D401F"',
   "v0-h264-main.mp4", "8686438", "bb", "detector"].join("\t"),
  ["v0-vp9", "base", 'video/webm; codecs="vp9"',
   "v0-vp9.webm", "4411693", "cc", "banda"].join("\t"),
  ["v0-vp9-alpha", "alpha", 'video/webm; codecs="vp9"',
   "v0-vp9-alpha.webm", "4664676", "dd", "alfa"].join("\t"),
  ["v0-hls-ts", "stream", "application/vnd.apple.mpegurl",
   "hls-ts/stream.m3u8", "9795953", "ee", "HLS TS; 16 segmentos"].join("\t"),
  ["v0-hls-fmp4", "stream", "application/vnd.apple.mpegurl",
   "hls-fmp4/stream.m3u8", "9555175", "ff", "HLS CMAF; 16 segmentos"].join("\t"),
  ["v0-dash", "stream", "application/dash+xml",
   "dash/manifest.mpd", "9555712", "aa11", "DASH; 16 segmentos"].join("\t")
].join("\n") + "\n";

function makeNode(name) {
  var node = {
    nodeName: name, childNodes: [], style: {}, className: "", value: "",
    firstChild: null, onclick: null, currentTime: 0, src: ""
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
  history: { back: function () {} },
  onresize: null
};

var navigatorStub = { userAgent: "fake-tv-box" };
var screenStub = { width: 1280, height: 720 };

/* El mando numerico vive en keypad.js (cargado con <script src>), asi que aca
 * se lo suplanta para poder mirar QUE acciones registro la pagina. */
var registered = null;
var keypadStub = {
  create: function (options) { registered = options; return { codes: [] }; }
};
global.ASCLKeypad = keypadStub;
windowStub.ASCLKeypad = keypadStub;

var run = new Function("window", "document", "navigator", "screen",
                       "XMLHttpRequest", inline[1]);
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR);

assert.strictEqual(requested.length, 1, "la pagina pide el manifiesto una vez");
assert(/MANIFEST\.tsv$/.test(requested[0]), "pide MANIFEST.tsv");

var filas = byId("filas");
assert.strictEqual(filas.childNodes.length, 7,
  "una fila por pieza del pack: 3 progresivas + alfa + 3 empaquetados");

var reporte = byId("report").value;
assert(reporte.indexOf("# pack v0") === 0, "el reporte arranca identificandose");
assert(reporte.indexOf("panel\t1280x720") >= 0,
  "el reporte distingue el panel real de la superficie del WebView");
assert(reporte.indexOf("superficie 3840x2160") >= 0,
  "la superficie que el WebView entrega es parte del diagnostico");
assert(reporte.indexOf("{") < 0 && reporte.indexOf("[") < 0,
  "el reporte es texto plano: se lee y se copia desde una TV");

/* La geometria se calcula en JS porque object-fit no existe en WebViews viejos
 * y porque la caja entrega una superficie 4K sobre un panel de 720p. */
assert(/px$/.test(documentStub.documentElement.style.fontSize),
  "la pagina escala su tipografia a la superficie del WebView");
assert(/px$/.test(byId("video").style.height),
  "el recuadro de video se dimensiona en JS, no con object-fit");
assert.strictEqual(byId("video").style.top, byId("alphaBg").style.top,
  "el fondo de alfa ocupa exactamente el mismo recuadro que el video");

/* --- El mando numerico --- */

assert(registered, "la pagina registra un mando numerico");
assert(page.indexOf('<script src="keypad.js"></script>') >= 0,
  "el mando se comparte via keypad.js, no se copia en la pagina");
var codigos = registered.actions.map(function (action) { return action.code; });
assert.strictEqual(codigos.length, 15);
["0", "1", "2", "3", "4", "5", "6", "7", "8"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta la tecla " + code);
});
["90", "91", "92", "93", "94", "95"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta el codigo compuesto " + code);
});
assert.strictEqual(registered.actions[0].code, "1");
assert.strictEqual(registered.actions[0].label, "correr todo",
  "el 1 es correr todo: es la accion que mas se usa");

/* Regla de usabilidad: lo comun no debe esperar. Ningun digito suelto usado
 * puede ser prefijo de un codigo largo, salvo el 9, que es la puerta a los
 * compuestos y a proposito no tiene accion propia. */
codigos.forEach(function (code) {
  if (code.length !== 1) { return; }
  codigos.forEach(function (other) {
    if (other.length > 1 && other.charAt(0) === code) {
      assert.fail("la tecla " + code + " se demora por culpa de " + other);
    }
  });
});
assert(codigos.indexOf("9") < 0,
  "el 9 queda reservado como prefijo de los compuestos");
assert.strictEqual(byId("teclas").childNodes.length, 15,
  "la leyenda de teclas se dibuja en pantalla: en una TV no hay donde mirarla");

/* La misma leyenda es el boton: en el celular no hay teclado numerico. */
var conClick = 0;
byId("teclas").childNodes.forEach(function (row) {
  if (typeof row.onclick === "function") { conClick++; }
});
assert.strictEqual(conClick, 15,
  "cada entrada de la leyenda tiene que poder tocarse en un celular");

console.log("v0 page tests: OK");
