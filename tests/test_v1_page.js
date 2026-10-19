"use strict";

/* H-27: v1.html, la pagina para mirar UN video por vez en la caja y decidir a
 * ojo si v2 puede ser fluido (15 fps, 512 colores, sin alt-ref). Lo que se
 * verifica son las reglas que el operador pidio: una tecla = un plano, en
 * bucle, en el UNICO <video>; el 0 pone y saca la pantalla entera sin cambiar
 * lo que suena; la misma tecla pausa y sigue; nada se corre solo; los planos
 * salen de PLANES.tsv (texto tabulado) y una tecla repetida o fuera de 1..9 no
 * entra. H-28: un plano puede traer un efecto con alfa ENCIMA (segundo
 * <video>), puesto en su rectangulo del lienzo y que se va con su plano. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var pagePath = path.join(__dirname, "..", "frontend", "v1.html");
var page = fs.readFileSync(pagePath, "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "v1.html debe contener su controlador inline");
assert(page.indexOf("PLANES.tsv") >= 0, "la pagina lee PLANES.tsv, tabulado");
assert.strictEqual(/\bJSON\s*\./.test(page), false, "sin JSON: el gate ES5 lo prohibe");
assert(/html,\s*body\s*\{[^}]*overflow:\s*hidden/.test(page),
  "la pagina no puede scrollear: todo tiene que entrar en una pantalla");
assert.strictEqual((page.match(/<video\s+id=/g) || []).length, 2,
  "dos <video>: el del plano y el de su efecto con alfa (H-28), nada mas");
assert(page.indexOf('<video id="video" muted playsinline></video>') >= 0);
assert(page.indexOf('<video id="efecto" muted playsinline></video>') >= 0);
assert(/#efecto\s*\{[^}]*display:\s*none/.test(page),
  "el efecto arranca escondido: solo lo prende un plano que lo trae");
assert.strictEqual(/#efecto\s*\{[^}]*background/.test(page), false,
  "el efecto no lleva fondo: lo transparente deja ver el plano");
assert(page.indexOf('<script src="keypad.js"></script>') >= 0,
  "el mando se comparte via keypad.js, no se copia en la pagina");
assert.strictEqual(/setInterval\([^)]*\)/.test(inline[1]) &&
                   /runSteps|everything|measure\(/.test(inline[1]), false,
  "nada mide en serie: no hay lotes ni reportes en esta pagina");

/* El archivo de planos que se publica al lado de la pagina, tal cual. */
var planesPath = path.join(__dirname, "..", "frontend", "v1-planes.tsv");
var PLANES_REAL = fs.readFileSync(planesPath, "utf8");

/* Y una version con trampas: un comentario, una linea corta, una tecla 0 y una
 * tecla repetida, que NO tienen que entrar. */
var PLANES = PLANES_REAL +
  "# una linea de comentario al final\n" +
  "corta\tsin\tcolumnas\n" +
  "0\tmalo\tel 0 es la pantalla entera\tx.webm\t1\t-\tno entra\n" +
  "3\trepetida\tla tecla 3 ya esta\ty.webm\t1\t-\tno entra\n";

function makeNode(name) {
  var node = {
    nodeName: name, childNodes: [], style: {}, className: "", value: "",
    firstChild: null, onclick: null, currentTime: 0, src: "", loop: false,
    paused: true, ended: false, attrs: {}
  };
  node.getAttribute = function (name) {
    return name === "src" ? (node.src || null) : (node.attrs[name] || null);
  };
  node.removeAttribute = function (name) {
    if (name === "src") { node.src = ""; }
    delete node.attrs[name];
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
  node.load = function () { node.loaded = (node.loaded || 0) + 1; };
  node.play = function () { node.paused = false; node.currentTime = 0.5; };
  node.pause = function () { node.paused = true; };
  return node;
}

var nodes = {};
function byId(id) {
  if (!nodes[id]) { nodes[id] = makeNode(id); }
  return nodes[id];
}

function textoDe(node) {
  return node.childNodes.length ? node.childNodes[0].data : "";
}

var requested = [];
var responder = function () { return { status: 200, body: PLANES }; };
function FakeXHR() { this.readyState = 0; this.status = 0; this.responseText = ""; }
FakeXHR.prototype.open = function (method, url) { this.url = url; };
FakeXHR.prototype.send = function () {
  var r = responder(this.url);
  requested.push(this.url);
  this.readyState = 4;
  this.status = r.status;
  this.responseText = r.body;
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

var intervals = [];
var windowStub = {
  innerWidth: 3840,
  innerHeight: 2160,
  location: { search: "" },
  setTimeout: function () { return 0; },
  clearTimeout: function () {},
  setInterval: function (fn) { intervals.push(fn); return intervals.length; },
  clearInterval: function () {},
  onresize: null
};
var screenStub = { width: 1280, height: 720 };

var registered = null;
var keypadStub = {
  create: function (options) { registered = options; return { codes: [] }; }
};
global.ASCLKeypad = keypadStub;
windowStub.ASCLKeypad = keypadStub;

function correr() {
  nodes = {};
  requested = [];
  registered = null;
  intervals = [];
  var run = new Function("window", "document", "screen", "XMLHttpRequest",
                         inline[1] + "\nwindow.__t = { parsePlanes: parsePlanes," +
                         " enteraOn: function () { return entera.on; }," +
                         " planes: function () { return planes; } };");
  run(windowStub, documentStub, screenStub, FakeXHR);
  return windowStub.__t;
}

function action(code) {
  var i;
  for (i = 0; i < registered.actions.length; i++) {
    if (registered.actions[i].code === code) { return registered.actions[i]; }
  }
  return null;
}

var api = correr();

/* --- PLANES.tsv --- */

assert.strictEqual(requested.length, 1, "pide UN archivo: PLANES.tsv");
assert(/PLANES\.tsv$/.test(requested[0]));
var planes = api.planes();
assert.strictEqual(planes.length, 9,
  "nueve planos: el 0, la repetida, la corta y el comentario no entran");
assert.deepStrictEqual(planes.map(function (p) { return p.tecla; }),
  ["1", "2", "3", "4", "5", "6", "7", "8", "9"]);
assert.strictEqual(planes[0].file, "../v0/v1-vp9.webm",
  "el de referencia es el v1 ya publicado, por ruta relativa");
assert.strictEqual(planes[1].id, "v2-crf18");
assert.strictEqual(planes[2].file, "crf18-15fps.webm");
assert.strictEqual(planes[6].file, "../v0/v2-h264.mp4");
assert.strictEqual(api.parsePlanes("# solo comentario\n").length, 0);
assert.strictEqual(api.parsePlanes("8\tid\tnombre\tarchivo.webm\n")[0].bytes, "",
  "bytes y sha256 son opcionales: se completan cuando la pieza existe");
assert.strictEqual(api.parsePlanes("8\tid\tnombre\tarchivo.webm\n")[0].encima, "",
  "sin columnas de efecto, el plano no trae efecto");
/* H-28: el efecto y su rectangulo. */
assert.strictEqual(planes[7].encima, "alfa-sintetico-vp9.webm");
assert.strictEqual(planes[8].encima, "alfa-sintetico-vp8.webm");
assert.deepStrictEqual(planes[7].rect, { x: 258, y: 180, w: 898, h: 360, lw: 1280, lh: 720 });
assert.strictEqual(planes[7].file, "../v0/v1-vp9.webm", "el efecto va encima del v1 fluido");
assert.strictEqual(planes[7].bytesEncima, "470532");
assert.strictEqual(planes[0].encima, "");
var raro = api.parsePlanes("8\ti\tn\ta.webm\t1\t-\tnota\te.webm\tbasura\n")[0];
assert.deepStrictEqual(raro.rect, { x: 0, y: 0, w: 1, h: 1, lw: 1, lh: 1 },
  "un rect ilegible pone el efecto sobre todo el plano, no lo pierde");
assert.strictEqual(api.parsePlanes("8\ti\tn\ta.webm\t1\t-\tnota\t-\n")[0].encima, "",
  "un guion en `encima` es sin efecto");

/* La lista dibuja una fila por plano, con su tecla, mas la del 0. */
var filas = byId("planos");
assert.strictEqual(filas.childNodes.length, 10, "nueve planos y la fila del 0");
assert.strictEqual(textoDe(filas.childNodes[0].childNodes[0]), "1");
assert.strictEqual(textoDe(filas.childNodes[9].childNodes[0]), "0");
assert(/\(2\.9 MB \+ 0\.5 MB\)/.test(textoDe(filas.childNodes[7].childNodes[1])),
  "la fila de un plano con efecto suma los dos pesos: " + textoDe(filas.childNodes[7].childNodes[1]));
assert(/2\.9 MB/.test(textoDe(filas.childNodes[0].childNodes[1])),
  "la fila dice los megas cuando los sabe: " + textoDe(filas.childNodes[0].childNodes[1]));
assert(/\(6 MB\)/.test(textoDe(filas.childNodes[2].childNodes[1])),
  "los planos emitidos el 2026-09-08 (noche) ya tienen bytes: " + textoDe(filas.childNodes[2].childNodes[1]));

/* --- El mando: 0 y una tecla de UNA cifra por plano; ninguna espera --- */

assert(registered, "la pagina registra el mando");
var codigos = registered.actions.map(function (a) { return a.code; });
assert.deepStrictEqual(codigos, ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]);
codigos.forEach(function (code) {
  assert.strictEqual(code.length, 1, "todas de una cifra: ninguna tecla espera");
});
assert(intervals.length === 1, "un solo reloj para el zocalo");

/* --- Una tecla, un plano, en bucle, en el unico <video> --- */

var video = byId("video");
assert(/elegi un plano: 1 2 3 4 5 6 7 8 9/.test(textoDe(byId("estado"))),
  "antes de elegir, el zocalo dice que teclas hay: " + textoDe(byId("estado")));
action("3").run();
assert.strictEqual(video.src, "crf18-15fps.webm");
assert.strictEqual(video.loop, true, "en bucle: se mira el rato que haga falta");
assert.strictEqual(video.paused, false);
assert.strictEqual(video.loaded, 1);
assert(/^plano 3: v2 crf 18 a 15 fps \(6 MB\) - 0 s - caidos -/.test(textoDe(byId("estado"))),
  "el zocalo dice que se esta mirando: " + textoDe(byId("estado")));
assert(/3 pausa\/sigue, 0 pantalla entera$/.test(textoDe(byId("estado"))));
assert.strictEqual(filas.childNodes[2].className, "op on", "la fila del plano se marca");
assert.strictEqual(filas.childNodes[0].className, "op");

/* La misma tecla pausa; otra vez, sigue. No recarga. */
action("3").run();
assert.strictEqual(video.paused, true);
assert(/EN PAUSA/.test(textoDe(byId("estado"))));
assert.strictEqual(video.loaded, 1, "pausar no recarga");
action("3").run();
assert.strictEqual(video.paused, false);
assert.strictEqual(/EN PAUSA/.test(textoDe(byId("estado"))), false);

/* Otra tecla cambia el src del MISMO video: nunca hay dos. */
action("2").run();
assert.strictEqual(video.src, "../v0/v2-vp9-crf18.webm");
assert.strictEqual(video.loaded, 2);
assert(/plano 2: v2 crf 18: la fuente, 20 fps \(7 MB\)/.test(textoDe(byId("estado"))),
  textoDe(byId("estado")));
assert.strictEqual(filas.childNodes[1].className, "op on");
assert.strictEqual(filas.childNodes[2].className, "op");
action("1").run();
assert.strictEqual(video.src, "../v0/v1-vp9.webm");
assert(/\(2\.9 MB\)/.test(textoDe(byId("estado"))));

/* --- H-28: el plano con efecto prende el segundo <video> encima --- */

var efecto = byId("efecto");
assert.strictEqual(efecto.style.display, undefined, "sin plano con efecto, nadie lo toco");
action("8").run();
assert.strictEqual(video.src, "../v0/v1-vp9.webm", "abajo, el plano");
assert.strictEqual(efecto.src, "alfa-sintetico-vp9.webm", "encima, el efecto");
assert.strictEqual(efecto.loop, true);
assert.strictEqual(efecto.paused, false);
assert.strictEqual(efecto.style.display, "block",
  "el efecto se ve: \"\" le devolveria el control al CSS, que lo esconde");
function n(v) { return parseInt(v, 10); }
var cx = n(video.style.left), cy = n(video.style.top);
var cw = n(video.style.width), ch = n(video.style.height);
assert.strictEqual(n(efecto.style.left), cx + Math.round(258 * cw / 1280),
  "el efecto va en su x del lienzo, escalada con el plano");
assert.strictEqual(n(efecto.style.top), cy + Math.round(180 * ch / 720));
assert.strictEqual(n(efecto.style.width), Math.round(898 * cw / 1280));
assert.strictEqual(n(efecto.style.height), Math.round(360 * ch / 720));
assert(/plano 8: v1 \+ efecto VP9 con alfa \(sintetico\) \(2\.9 MB \+ 0\.5 MB\) - 0 s - caidos .* - efecto /.test(textoDe(byId("estado"))),
  "el zocalo cuenta los caidos de los dos: " + textoDe(byId("estado")));
/* La misma tecla pausa y sigue a los dos. */
action("8").run();
assert.strictEqual(video.paused, true);
assert.strictEqual(efecto.paused, true, "el efecto se pausa con su plano");
action("8").run();
assert.strictEqual(efecto.paused, false);
/* Otro plano con efecto: cambia el efecto, el plano de abajo es el mismo archivo. */
action("9").run();
assert.strictEqual(efecto.src, "alfa-sintetico-vp8.webm");
/* Un plano sin efecto lo apaga: sin src, no decodifica nada. */
action("1").run();
assert.strictEqual(efecto.style.display, "none");
assert.strictEqual(efecto.src, "", "el efecto suelta su archivo");
assert.strictEqual(efecto.paused, true);
assert.strictEqual(/efecto/.test(textoDe(byId("estado"))), false);

/* --- El 0: pone y saca la pantalla entera sin tocar lo que suena --- */

assert.strictEqual(api.enteraOn(), false);
var anchoNormal = video.style.width;
assert(/px$/.test(anchoNormal), "el recuadro se dimensiona en JS, no con object-fit");
action("0").run();
assert.strictEqual(api.enteraOn(), true);
assert.strictEqual(byId("lista").style.display, "none", "la lista se esconde");
assert.strictEqual(byId("head").style.display, "none");
assert.strictEqual(video.style.width, "3840px", "el video ocupa la superficie entera");
action("8").run();
assert.strictEqual(efecto.style.left, Math.round(258 * 3840 / 1280) + "px",
  "a pantalla entera el efecto se re-ubica con el plano");
assert.strictEqual(efecto.style.width, Math.round(898 * 3840 / 1280) + "px");
action("1").run();
assert.strictEqual(video.style.height, "2160px");
assert.strictEqual(video.style.left, "0px");
assert.strictEqual(video.paused, false, "lo que sonaba sigue sonando");
assert.strictEqual(video.src, "../v0/v1-vp9.webm", "y es el mismo plano");
assert(/0 pantalla normal$/.test(textoDe(byId("estado"))),
  "el zocalo dice como se sale: " + textoDe(byId("estado")));
assert(/PANTALLA ENTERA \(api sin api\)/.test(textoDe(byId("pie"))),
  "el pie declara si la API se concedio: " + textoDe(byId("pie")));
action("0").run();
assert.strictEqual(api.enteraOn(), false);
assert.strictEqual(byId("lista").style.display, "");
assert.strictEqual(video.style.width, anchoNormal, "vuelve la geometria normal");
assert.strictEqual(video.paused, false);
/* El 0 anda tambien sin ningun plano elegido (la pantalla entera es del
 * aparato, no del video). */
api = correr();
action("0").run();
assert.strictEqual(api.enteraOn(), true);
assert(/PANTALLA ENTERA/.test(textoDe(byId("pie"))));
action("0").run();

/* --- El pie lleva la geometria de la caja y la ultima tecla (H-22) --- */

assert(/panel 1280x720 · superficie 3840x2160 · quality no/.test(textoDe(byId("pie"))),
  textoDe(byId("pie")));
registered.onKey("keydown kc=0 w=0 cc=0 key=3 code=Digit3 foco=BODY", 1);
assert(/tecla 1: keydown kc=0 .* key=3/.test(textoDe(byId("pie"))),
  "lo que el aparato mando queda escrito: " + textoDe(byId("pie")));

/* --- Sin PLANES.tsv la pagina lo dice y el 0 sigue andando --- */

responder = function () { return { status: 404, body: "" }; };
api = correr();
assert(/no se pudo leer PLANES\.tsv: HTTP 404/.test(textoDe(byId("estado"))),
  textoDe(byId("estado")));
assert.deepStrictEqual(registered.actions.map(function (a) { return a.code; }), ["0"]);
action("0").run();
assert.strictEqual(api.enteraOn(), true);

/* --- El archivo real de planos, sin trampas, tiene las nueve teclas --- */

responder = function () { return { status: 200, body: PLANES_REAL }; };
api = correr();
assert.strictEqual(api.planes().length, 9);
assert(/^# tecla\tid\tnombre\tarchivo\tbytes\tsha256\tnota\tencima\trect\tbytes_encima\tsha256_encima$/m.test(PLANES_REAL),
  "el archivo declara sus columnas");

console.log("v1 page tests (H-27 + H-28): OK");
