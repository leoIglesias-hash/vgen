"use strict";

/* H-8a: producto.html es la FORMA DEL PRODUCTO, no una pagina de pruebas: el
 * loop en bucle con los numeros encima, la publicidad que reemplaza y vuelve,
 * el incentivador a demanda y la radio aparte, todo desde el aparato (H-15).
 * Se ejecuta su script inline contra un DOM minimo, con el guion REAL
 * (frontend/GUION.tsv) y manifiestos falsos que llevan los mismos ids que los
 * publicados. Lo que se verifica son las reglas que la hacen producto en un
 * TV BOX: una sola pantalla, una accion por tecla de UNA cifra, el loop elegido
 * por lo que el <video> declara reproducible, la residencia planificada por
 * prioridad, y que sin IndexedDB o sin MSE la pagina siga sonando igual. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var VGenFeed = require("../frontend/vgenfeed.js");
var VGenCache = require("../frontend/vgencache.js");

var pagePath = path.join(__dirname, "..", "frontend", "producto.html");
var page = fs.readFileSync(pagePath, "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);
var guionPath = path.join(__dirname, "..", "frontend", "GUION.tsv");
var GUION = fs.readFileSync(guionPath, "utf8");

assert(inline, "producto.html debe contener su controlador inline");
assert.strictEqual(/\bJSON\s*\./.test(page), false,
  "ni el guion ni los manifiestos son JSON: el gate ES5 lo prohibe");
assert(/html,\s*body\s*\{[^}]*overflow:\s*hidden/.test(page),
  "la pagina no puede scrollear: una sola pantalla");
assert.strictEqual((page.match(/<video\s+id="video"/g) || []).length, 1,
  "un solo <video> para el loop y la publicidad");
assert.strictEqual((page.match(/<video\s+id=/g) || []).length, 2,
  "y exactamente uno mas, el del efecto con alfa (H-18b)");
assert.strictEqual((page.match(/<canvas/g) || []).length, 1,
  "UN canvas de intervencion, nunca dos");
assert.strictEqual((page.match(/<audio\s+id="radio"/g) || []).length, 1,
  "la radio es un <audio> aparte (S14)");
["keypad.js", "vgenfeed.js", "vgencache.js"].forEach(function (name) {
  assert(page.indexOf('<script src="' + name + '"></script>') >= 0,
    "el producto reusa " + name + ", no lo copia");
});
assert(inline[1].indexOf("VGenFeed.ring(") >= 0,
  "el bucle del producto es el anillo MSE en modo sequence (H-13: loop refutado, S12 en pie)");
assert(inline[1].indexOf("VGenCache.ensure(") >= 0 && inline[1].indexOf("VGenCache.plan(") >= 0,
  "la residencia se planifica por prioridad y se asegura al abrir (H-15)");
assert(/video\.currentTime/.test(inline[1].slice(inline[1].indexOf("function paintCapa"))),
  "la capa lee el reloj del video en cada pintada (H-11)");
assert.strictEqual((inline[1].match(/\bvideo\.pause\(\)/g) || []).length, 1,
  "el unico pause del <video> de abajo es el del 0");
assert(/setInterval\(/.test(inline[1]) && /volume/.test(inline[1]),
  "la radio baja y sube con una rampa de volumen (DISENO 7)");
assert.strictEqual(/PIE_MS = 1000/.test(inline[1]), true,
  "el zocalo se reescribe a 1 Hz, nunca por cuadro (regla 3)");

/* --- el guion real --- */

var guionIds = GUION.split("\n").filter(function (line) {
  return line.length && line.charAt(0) !== "#";
}).map(function (line) { return line.split("\t"); });
assert(guionIds.length >= 5, "el guion trae los cinco papeles del producto");
var roles = guionIds.map(function (f) { return f[0]; });
["loop", "incentivador", "publicidad", "radio"].forEach(function (rol) {
  assert(roles.indexOf(rol) >= 0, "el guion tiene el papel " + rol);
});
assert(roles.filter(function (r) { return r === "loop"; }).length >= 2,
  "hay mas de un candidato a loop: VP9 base y el piso H.264 (E13)");
guionIds.forEach(function (f) {
  assert.strictEqual(f.length, 8, "ocho columnas en la fila " + f[1]);
  assert(f[2] === "si" || f[2] === "no", "residente si|no en " + f[1]);
  assert(/^\d+$/.test(f[3]), "prioridad entera en " + f[1]);
});

/* --- DOM minimo --- */

var MANIFEST = [
  "# pack v0",
  "# id\trole\tmime\tfile\tbytes\tsha256\tnote",
  ["v0-h264-baseline", "base", 'video/mp4; codecs="avc1.42E01F"',
   "v0-h264-baseline.mp4", "9551715", "cf927d578ab993d4", "piso"].join("\t"),
  ["v0-vp9", "base", 'video/webm; codecs="vp9"', "v0-vp9.webm", "4411693", "5be46507", ""].join("\t"),
  ["v0-vp9-alpha", "alpha", 'video/webm; codecs="vp9"',
   "v0-vp9-alpha.webm", "2434369", "2b1fe6c3bfdee0cd", "alfa"].join("\t"),
  ["v0-dash", "stream", "application/dash+xml", "dash/manifest.mpd", "9555712", "728afaae5867b2ef", "16 segmentos"].join("\t")
].join("\n") + "\n";
var MANIFEST_V1 = [
  "# pack v1",
  "# id\trole\tmime\tfile\tbytes\tsha256\tnote",
  ["v1-vp9", "v1", 'video/webm; codecs="vp9, opus"', "v1-vp9.webm", "2941449", "86014f1751052", ""].join("\t"),
  ["v1-h264", "v1", 'video/mp4; codecs="avc1.64001F, mp4a.40.2"', "v1-h264.mp4", "5254272", "7992b0cc75a248", ""].join("\t"),
  ["v1-ambiente", "radio", "audio/mpeg", "v1-ambiente.mp3", "183353", "c886263508da44", ""].join("\t"),
  ["v1-dash-vp9", "stream-v1", 'video/webm; codecs="vp9"', "dash-vp9/manifest.mpd", "2831164", "a61bde6c1a8a63", "16 segmentos"].join("\t")
].join("\n") + "\n";

function makeNode(name) {
  var node = {
    nodeName: name, childNodes: [], style: {}, className: "", value: "",
    firstChild: null, onclick: null, currentTime: 0, src: "", loop: false,
    paused: true, ended: false, muted: true, volume: 1, duration: NaN,
    width: 0, height: 0, listeners: {}, pauses: 0, plays: 0, loads: 0
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
  node.addEventListener = function (name, fn) { node.listeners[name] = fn; };
  node.removeEventListener = function () {};
  node.canPlayType = function (mime) { return canPlay(mime); };
  node.load = function () { node.loads++; };
  node.play = function () { node.plays++; node.paused = false; };
  node.pause = function () { node.pauses++; node.paused = true; };
  node.getContext = function () { return null; };
  return node;
}

/* Un aparato SIN VP9 primero: el loop tiene que caer al piso H.264. */
var canPlay = function (mime) { return mime.indexOf("vp9") >= 0 ? "" : "probably"; };

var nodes = {};
function byId(id) {
  if (!nodes[id]) { nodes[id] = makeNode(id); }
  return nodes[id];
}

var requested = [];
function FakeXHR() { this.readyState = 0; this.status = 0; this.responseText = ""; }
FakeXHR.prototype.open = function (method, url) { this.url = url; };
FakeXHR.prototype.send = function () {
  requested.push(this.url);
  this.readyState = 4;
  this.status = 200;
  if (/GUION.tsv$/.test(this.url)) { this.responseText = GUION; }
  else if (/MANIFEST-v1/.test(this.url)) { this.responseText = MANIFEST_V1; }
  else { this.responseText = MANIFEST; }
  this.response = this.responseText;
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
  innerWidth: 3840, innerHeight: 2160, devicePixelRatio: 1,
  location: { search: "" },
  setTimeout: function () { return 0; }, clearTimeout: function () {},
  setInterval: function () { return 0; }, clearInterval: function () {},
  indexedDB: {},          /* sin open(): "sin indexedDB" -> todo por red */
  URL: null, MediaSource: null, onresize: null
};
var navigatorStub = { userAgent: "fake-tv-box" };
var screenStub = { width: 1280, height: 720 };

var registered = null;
var keypadStub = { create: function (options) { registered = options; return { codes: [] }; } };
global.ASCLKeypad = keypadStub;
windowStub.ASCLKeypad = keypadStub;

function action(code) {
  var i;
  for (i = 0; i < registered.actions.length; i++) {
    if (registered.actions[i].code === code) { return registered.actions[i]; }
  }
  return null;
}

function textoDe(node) { return node.childNodes.length ? node.childNodes[0].data : ""; }

function reporteTexto() {
  var arriba, abajo;
  action("9").run();
  arriba = textoDe(byId("colA"));
  abajo = textoDe(byId("colB"));
  action("9").run();
  return abajo ? arriba + "\n" + abajo : arriba;
}

var run = new Function("window", "document", "navigator", "screen",
                       "XMLHttpRequest", "VGenFeed", "VGenCache", inline[1]);
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR, VGenFeed, VGenCache);

/* --- arranque sin base y sin VP9 --- */

assert.strictEqual(requested.length, 3, "pide los dos manifiestos y el guion");
assert(/MANIFEST\.tsv$/.test(requested[0]) && /MANIFEST-v1\.tsv$/.test(requested[1]) &&
       /GUION\.tsv$/.test(requested[2]), "en ese orden: v0, v1, guion");

var video = byId("video");
assert.strictEqual(video.src, "v0-h264-baseline.mp4",
  "sin VP9 el loop cae al piso H.264 del guion, por red (sin base)");
assert.strictEqual(video.muted, true, "el loop suena mudo: la radio va aparte");
assert.strictEqual(video.plays, 1, "y arranca solo al abrir: es el producto");
assert.strictEqual(video.loop, false, "sin MSE el bucle es por blob con costura medida, no loop nativo");
assert.strictEqual(byId("radio").src, "v1-ambiente.mp3", "la radio arranca sola al abrir");
assert.strictEqual(byId("radio").loop, true, "en bucle");
assert(page.indexOf('<video id="efecto" class="off"') >= 0, "el efecto esta escondido hasta que se pida");
assert(page.indexOf('<canvas id="capa" class="off"') >= 0, "la capa arranca apagada");

/* Geometria en JS, al panel y no a la superficie. */
assert(/px$/.test(documentStub.documentElement.style.fontSize));
assert.strictEqual(video.style.top, byId("efecto").style.top,
  "el efecto va exactamente sobre el loop (H-18b)");
assert.strictEqual(video.style.width, byId("capa").style.width,
  "y la capa cubre el mismo recuadro");
assert.strictEqual(byId("capa").width, 1280, "el buffer del canvas es del PANEL (1280), no de la superficie 4K");

var pie = textoDe(byId("pie"));
assert(/loop v0-h264-baseline por blob \(red\)/.test(pie), "el zocalo dice que suena y de donde: " + pie);
assert(/residente 0\//.test(pie), "y cuantas piezas estan residentes");
assert(/0 corta/.test(pie), "y como se corta");

/* --- el mando: diez teclas, todas de UNA cifra --- */

assert(registered, "la pagina registra el mando");
var codigos = registered.actions.map(function (a) { return a.code; });
assert.deepStrictEqual(codigos.slice().sort(), ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
  "diez teclas de una cifra: en el producto ninguna espera");
assert(/MSE/.test(action("1").label) && /blob/.test(action("2").label) && /nativo/.test(action("3").label),
  "1, 2 y 3 son los tres modos de bucle, del que el diseno eligio al refutado");
assert(/incentivador/.test(action("4").label) && /publicidad/.test(action("5").label));
assert(/radio/.test(action("6").label) && /capa/.test(action("7").label));
assert(/reporte/.test(action("9").label) && /cortar/.test(action("0").label));

/* --- el reporte es texto plano y dice de donde salio cada pieza --- */

var reporte = reporteTexto();
assert(reporte.indexOf("# vgen producto") === 0, "el reporte se identifica");
assert(reporte.indexOf("panel\t1280x720") >= 0);
assert(reporte.indexOf("{") < 0 && reporte.indexOf("[") < 0, "texto plano, para la foto");
assert(/loop\tv0-h264-baseline\tsin base/.test(reporte), "cada papel con su origen: " + reporte);
assert(/loop\tv1-vp9\tno elegido/.test(reporte), "el candidato VP9 queda marcado como no elegido");
assert(/loop-segs\tv0-dash\tsin base/.test(reporte), "y los segmentos del loop elegido tambien");
assert(/radio\tv1-ambiente\tprendida/.test(reporte), "la radio se reporta prendida");

/* --- las teclas hacen lo que dicen --- */

action("7").run();
assert.strictEqual(byId("capa").className, "", "7 prende la capa");
assert(/capa\tnumeros\t/.test(reporteTexto()), "con los numeros solos");
action("7").run();
assert.strictEqual(byId("capa").className, "", "el segundo 7 la deja prendida");
reporte = reporteTexto();
assert(/capa\tnumeros\+imagen\t/.test(reporte), "y suma la imagen que gira (H-23)");
assert(/imagen\tsin imagen \(sin Image\)/.test(reporte),
  "sin Image ni canvas el reporte dice que no hubo imagen: " + reporte);
action("7").run();
assert.strictEqual(byId("capa").className, "off", "y el tercero la apaga");

action("4").run();
assert.strictEqual(byId("efecto").className, "", "4 muestra el efecto encima");
assert.strictEqual(byId("efecto").src, "v0-vp9-alpha.webm", "con la pieza alfa del guion");
assert.strictEqual(byId("efecto").loop, false, "una sola vez: sale solo");

action("5").run();
assert.strictEqual(video.src, "v1-h264.mp4", "5 reemplaza el loop por la publicidad");
assert.strictEqual(video.muted, false, "que suena con su propio audio (S13)");
video.ended = true;
video.listeners.ended();
assert.strictEqual(video.src, "v0-h264-baseline.mp4", "y al terminar vuelve sola al loop");
assert.strictEqual(video.muted, true, "mudo otra vez");

action("6").run();
assert.strictEqual(byId("radio").paused, true, "6 apaga la radio");
action("6").run();
assert.strictEqual(byId("radio").paused, false, "y la prende");

var pausasAntes = video.pauses;
action("0").run();
assert.strictEqual(video.pauses, pausasAntes + 1, "0 pausa el loop");
assert.strictEqual(byId("radio").paused, true, "calla la radio");
assert.strictEqual(byId("efecto").className, "off", "esconde el efecto");
assert.strictEqual(byId("capa").className, "off", "y apaga la capa");
assert(/^loop parado/.test(textoDe(byId("pie"))), "y el zocalo lo dice");

/* --- un aparato CON VP9 elige la base y el bucle por MSE --- */

nodes = {};
requested = [];
registered = null;
canPlay = function () { return "probably"; };
function FakeSourceBuffer() { this.mode = "segments"; this.updating = false; this.appended = []; this.listeners = {}; }
FakeSourceBuffer.prototype.addEventListener = function (n, fn) { this.listeners[n] = fn; };
FakeSourceBuffer.prototype.removeEventListener = function () {};
FakeSourceBuffer.prototype.appendBuffer = function (b) { this.appended.push(b); this.updating = true; };
function FakeMediaSource() { this.readyState = "closed"; this.listeners = {}; this.buffers = []; }
FakeMediaSource.isTypeSupported = function (mime) { return mime.indexOf("vp9") >= 0; };
FakeMediaSource.prototype.addEventListener = function (n, fn) { this.listeners[n] = fn; };
FakeMediaSource.prototype.addSourceBuffer = function () {
  var sb = new FakeSourceBuffer(); this.buffers.push(sb); return sb;
};
var created = [];
var imagenes = [];
function FakeImage() { this.src = ""; this.onload = null; this.onerror = null; imagenes.push(this); }
windowStub.Image = FakeImage;
var rafs = [];
windowStub.requestAnimationFrame = function (fn) { rafs.push(fn); return rafs.length; };
windowStub.cancelAnimationFrame = function () {};
windowStub.MediaSource = FakeMediaSource;
windowStub.URL = { createObjectURL: function (thing) { created.push(thing); return "blob:fake/" + created.length; },
                   revokeObjectURL: function () {} };
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR, VGenFeed, VGenCache);
video = byId("video");
assert.strictEqual(created.length, 1, "con MSE el loop arranca por el anillo: un MediaSource");
assert(created[0] instanceof FakeMediaSource);
assert.strictEqual(video.src, "blob:fake/1", "colgado del <video>");
assert.strictEqual(video.plays, 1);
created[0].readyState = "open";
created[0].listeners.sourceopen();
assert.strictEqual(created[0].buffers.length, 1, "un SourceBuffer");
assert.strictEqual(created[0].buffers[0].mode, "sequence", "en modo sequence (S12)");
assert.strictEqual(requested.length, 4, "y pidio el init por red (sin base)");
assert(/dash-vp9\/init\.webm$/.test(requested[3]), "el init de la representacion segmentada del loop VP9: " + requested[3]);
assert(/loop v1-vp9 por mse/.test(textoDe(byId("pie"))), "el zocalo lo dice: " + textoDe(byId("pie")));
reporte = reporteTexto();
assert(/loop\tv1-vp9\tsin base/.test(reporte), "VP9 elegido");
assert(/loop\tv0-h264-baseline\tno elegido/.test(reporte), "y el piso, no elegido");
assert(/mse\.loop\tsi/.test(reporte), "la cabecera dice que el MIME del anillo se sostiene");

/* --- H-23: la imagen que gira se pide una vez y se mide --- */

action("7").run();
assert.strictEqual(imagenes.length, 0, "los numeros solos no piden ninguna imagen");
action("7").run();
assert.strictEqual(imagenes.length, 1, "la imagen se pide UNA vez, al primer 7 que la necesita");
assert.strictEqual(imagenes[0].src, "logo.png", "el logo, al lado de la pagina");
assert(/imagen\tcargando/.test(reporteTexto()), "y el reporte dice que viene");
imagenes[0].naturalWidth = 210; imagenes[0].naturalHeight = 150;
imagenes[0].onload();
reporte = reporteTexto();
assert(/imagen\tlista\tlogo\.png\t210x150\tllego \d+ ms/.test(reporte),
  "cuando llega, el reporte la mide: " + reporte);
action("7").run();
assert.strictEqual(byId("capa").className, "off", "el tercer 7 apaga");
action("7").run(); action("7").run();
assert.strictEqual(imagenes.length, 1, "y al volver a pedirla no se baja de nuevo");

/* --- H-23c: con requestAnimationFrame la capa se pinta en el vsync, 1 de 4 --- */

assert(rafs.length >= 1, "la capa pidio un frame al vsync");
var antes = rafs.length;
rafs[rafs.length - 1](); rafs[rafs.length - 1](); rafs[rafs.length - 1]();
assert.strictEqual(rafs.length, antes + 3, "cada vsync vuelve a pedir el siguiente");
assert(/capa\tnumeros\+imagen\t.*\treloj raf\t/.test(reporteTexto()), "y el reporte dice reloj raf");

console.log("producto page tests (H-8a): OK");
