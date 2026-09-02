"use strict";

/* H-10 + H-13: la pagina que reproduce el pack v0 y reporta lo que el aparato
 * hizo. Se ejecuta su script inline contra un DOM minimo. Lo que se verifica
 * no es "que exista un boton" sino las reglas que la hacen usable en un TV
 * BOX: una sola pantalla sin scroll, una accion por tecla numerica, y (H-13)
 * que las cinco pruebas de paquete existan, que la medicion tenga la columna
 * congel, que no pause al terminar y que ningun digito suelto se demore.
 * H-11: que exista UN canvas encima del video, dimensionado al panel y no a
 * la superficie, con sus teclas y apagado por defecto. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var VGenFeed = require("../frontend/vgenfeed.js");

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
  "correr todo tiene que incluir progresivas, alfa, empaquetados y paquete");

/* --- H-13: la medicion --- */

assert(page.indexOf('<script src="vgenfeed.js"></script>') >= 0,
  "las puertas del paquete viven en vgenfeed.js (lo reusa H-8), no en la pagina");
assert(/<th>congel<\/th>/.test(page), "existe la columna congel en la tabla");
assert(inline[1].indexOf("\\tatascos\\tcongel\\tcambio_ms\\tnota") >= 0,
  "el reporte lleva las columnas congel y cambio_ms");
assert(/if \(row\.started\) \{ row\.stalls\+\+; \}/.test(inline[1]),
  "atascos cuenta el waiting solo despues de arrancar");
assert.strictEqual((inline[1].match(/\.pause\(\)/g) || []).length, 1,
  "no se pausa al terminar una medicion: la unica pausa es la del 0 (cortar)");
assert(inline[1].indexOf('"ciego"') >= 0,
  "la fila dice ciego cuando el contador de cuadros no se movio");
assert(inline[1].indexOf("dash/init.m4s") >= 0 && inline[1].indexOf("dash/chunk-") >= 0,
  "las pruebas de paquete usan los segmentos CMAF ya publicados: cero emision nueva");
assert(/hasChangeType\(\)/.test(inline[1]),
  "la cabecera del reporte detecta SourceBuffer.changeType");
["function stepMse", "function stepBlob", "function stepSwitch",
 "function stepLoop", "function orderSteps", "function packageSteps"]
  .forEach(function (name) {
    assert(inline[1].indexOf(name) >= 0, "falta " + name);
  });

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
    firstChild: null, onclick: null, currentTime: 0, src: "", loop: false,
    paused: true, ended: false, duration: NaN
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
  node.play = function () { node.paused = false; };
  node.pause = function () { node.paused = true; };
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
                       "XMLHttpRequest", "VGenFeed", inline[1]);
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR, VGenFeed);

assert.strictEqual(requested.length, 1, "la pagina pide el manifiesto una vez");
assert(/MANIFEST\.tsv$/.test(requested[0]), "pide MANIFEST.tsv");

var filas = byId("filas");
assert.strictEqual(filas.childNodes.length, 7,
  "una fila por pieza del pack: 3 progresivas + alfa + 3 empaquetados");
assert.strictEqual(filas.childNodes[0].childNodes.length, 6,
  "seis columnas: pieza, ok, caidos/total, 1er, congel, cambio");

var reporte = byId("report").value;
assert(reporte.indexOf("# pack v0") === 0, "el reporte arranca identificandose");
assert(reporte.indexOf("panel\t1280x720") >= 0,
  "el reporte distingue el panel real de la superficie del WebView");
assert(reporte.indexOf("superficie 3840x2160") >= 0,
  "la superficie que el WebView entrega es parte del diagnostico");
assert(reporte.indexOf("changeType\tno") >= 0,
  "la cabecera dice si existe SourceBuffer.changeType");
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
assert.strictEqual(codigos.length, 23);
["0", "1", "2", "3", "4", "5", "6", "7", "8"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta la tecla " + code);
});
["90", "91", "92", "93", "94", "95", "96", "97", "98", "99",
 "930", "931", "932", "933"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta el codigo compuesto " + code);
});
assert.strictEqual(registered.actions[0].code, "1");
assert.strictEqual(registered.actions[0].label, "correr todo",
  "el 1 es correr todo: es la accion que mas se usa");

function action(code) {
  var i;
  for (i = 0; i < registered.actions.length; i++) {
    if (registered.actions[i].code === code) { return registered.actions[i]; }
  }
  return null;
}

/* Las cinco pruebas de paquete (H-13), cada una con su tecla, y el 5 que las
 * corre juntas. El 8 dejo de ser "solo hls-ts" (sigue dentro del 4). */
assert(/paquete/.test(action("5").label), "el 5 corre las cinco de paquete");
assert(/MSE/.test(action("96").label), "96 = MSE H.264");
assert(/blob/i.test(action("97").label), "97 = Blob concatenado");
assert(/orden/.test(action("98").label), "98 = intercambio de orden");
assert(/cambio/.test(action("8").label), "8 = cambio a demanda");
assert(/bucle/.test(action("99").label), "99 = bucle 60 s");

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
assert.strictEqual(byId("teclas").childNodes.length, 23,
  "la leyenda de teclas se dibuja en pantalla: en una TV no hay donde mirarla");

/* La misma leyenda es el boton: en el celular no hay teclado numerico. */
var conClick = 0;
byId("teclas").childNodes.forEach(function (row) {
  if (typeof row.onclick === "function") { conClick++; }
});
assert.strictEqual(conClick, 23,
  "cada entrada de la leyenda tiene que poder tocarse en un celular");

/* --- Correr el 5 en un aparato sin MSE: la fila aparece con su error y el
 * resto no explota; el 0 la limpia. --- */
action("5").run();
assert.strictEqual(filas.childNodes.length, 8,
  "la primera prueba de paquete agrega su fila sintetica");
reporte = byId("report").value;
assert(/\nmse:h264\t.*sin MSE/.test(reporte),
  "sin MediaSource la fila mse:h264 dice por que no corrio");
assert(/\n# id\tdice\tarranco\t1er_ms\tcaidos\ttotal\tderiva_ms\tatascos\tcongel\tcambio_ms\tnota\n/.test(reporte),
  "cabecera de columnas del reporte (PLAN-IMPLEMENTACION-VGEN §3.1)");
action("0").run();
assert.strictEqual(filas.childNodes.length, 7, "el 0 limpia las filas sinteticas");
assert.strictEqual(byId("video").loop, false, "el 0 apaga el loop del bucle");

/* --- H-11: la capa de intervencion encima del video --- */

assert.strictEqual((page.match(/<canvas\s+id="capa"/g) || []).length, 1,
  "un solo canvas de intervencion (dos capas: video + canvas, no mas)");
assert(page.indexOf('<canvas id="capa"') > page.indexOf('<video id="video"'),
  "el canvas va DESPUES del video en el DOM: queda encima, no debajo");
assert(/#capa\s*\{[^}]*position:\s*absolute/.test(page),
  "el canvas se posiciona sobre el recuadro del video");
assert.strictEqual(byId("capa").style.top, byId("video").style.top,
  "el canvas ocupa exactamente el recuadro del video (alto)");
assert.strictEqual(byId("capa").style.width, byId("video").style.width,
  "el canvas ocupa exactamente el recuadro del video (ancho)");
var cssW = parseInt(byId("video").style.width, 10);
var cssH = parseInt(byId("video").style.height, 10);
assert.strictEqual(byId("capa").width, Math.round(cssW * 1280 / 3840),
  "el buffer del canvas se dimensiona al PANEL (1280), nunca a la superficie (3840)");
assert.strictEqual(byId("capa").height, Math.round(cssH * 1280 / 3840),
  "idem en alto");
assert(byId("report").value.indexOf("\ncapa\t" + byId("capa").width + "x" +
       byId("capa").height + "\tk 0.333") >= 0,
  "el reporte dice el tamano del buffer del canvas y la escala panel/superficie");
["function setCapa", "function paintCapa", "function stepCapa",
 "function capaSteps", "function capaAll", "function h11Batch"]
  .forEach(function (name) {
    assert(inline[1].indexOf(name) >= 0, "falta " + name);
  });
assert(/fillText\(/.test(inline[1]),
  "la capa dibuja numero y texto con la API nativa de Canvas2D (INT-004)");
assert(/\.arc\(/.test(inline[1]), "la capa dibuja la ruleta");
assert(/packageSteps\(\), capaAll\(\)/.test(inline[1]),
  "correr todo (1) incluye las seis mediciones de capa");
assert(/H-11/.test(action("930").label), "930 = el lote de la visita H-11");
assert(/blob/.test(action("930").detail),
  "el lote lleva blob: y blob concat seguidos (arranque desde memoria)");
assert(/capa/.test(action("931").label) && /baseline/.test(action("931").label),
  "931 = capa sobre Baseline");
assert(/capa/.test(action("932").label) && /vp9/.test(action("932").label),
  "932 = capa sobre VP9");
assert(/ojo/.test(action("933").label), "933 = la capa a ojo, para el operador");

/* Sin medir, el canvas no existe (display none): la linea de base es sin capa.
 * El 933 la alterna y el 0 la apaga. */
assert.strictEqual(byId("capa").className, "off",
  "antes de medir el canvas no existe: la linea de base es sin capa");
action("933").run();
assert.strictEqual(byId("capa").className, "", "933 enciende el rectangulo");
action("933").run();
assert.strictEqual(byId("capa").className, "off", "933 otra vez lo apaga");
action("933").run();
action("0").run();
assert.strictEqual(byId("capa").className, "off", "el 0 apaga la capa");

console.log("v0 page tests: OK");
