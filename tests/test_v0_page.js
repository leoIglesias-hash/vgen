"use strict";

/* H-10 + H-13: la pagina que reproduce el pack v0 y reporta lo que el aparato
 * hizo. Se ejecuta su script inline contra un DOM minimo. Lo que se verifica
 * no es "que exista un boton" sino las reglas que la hacen usable en un TV
 * BOX: una sola pantalla sin scroll, una accion por tecla numerica, y (H-13)
 * que las cinco pruebas de paquete existan, que la medicion tenga la columna
 * congel, que no pause al terminar y que ningun digito suelto se demore.
 * H-11: que exista UN canvas encima del video, dimensionado al panel y no a
 * la superficie, con sus teclas y apagado por defecto.
 * H-12: que la cache viva en vgencache.js, que sus teclas existan, que las
 * filas que no reproducen no se marquen ciegas y que sin IndexedDB la fila
 * diga por que. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var VGenFeed = require("../frontend/vgenfeed.js");
var VGenCache = require("../frontend/vgencache.js");

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
                       "XMLHttpRequest", "VGenFeed", "VGenCache", inline[1]);
run(windowStub, documentStub, navigatorStub, screenStub, FakeXHR, VGenFeed,
    VGenCache);

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
assert.strictEqual(codigos.length, 26);
["0", "1", "2", "3", "4", "5", "6", "7", "8"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta la tecla " + code);
});
["80", "81", "82", "83", "84", "85", "86",
 "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta el codigo compuesto " + code);
});
assert.strictEqual(action("1").label, "correr todo",
  "el 1 sigue siendo correr todo: es la accion que mas se usa");

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

/* Techo de dos cifras (decision del operador, 2026-09-02): antes de llegar a
 * tres hay cien numeros. Las puertas son el 9 (sin accion propia) y el 8 (que
 * conserva la suya y por eso espera). Ningun otro digito suelto se demora. */
codigos.forEach(function (code) {
  assert(code.length <= 2, "la tecla " + code + " tiene tres cifras");
});
var PUERTAS = ["8", "9"];
codigos.forEach(function (code) {
  if (code.length !== 1) { return; }
  codigos.forEach(function (other) {
    if (other.length > 1 && other.charAt(0) === code &&
        PUERTAS.indexOf(code) < 0) {
      assert.fail("la tecla " + code + " se demora por culpa de " + other);
    }
  });
});
assert(codigos.indexOf("9") < 0,
  "el 9 queda reservado como prefijo de los compuestos");
assert(codigos.indexOf("8") >= 0,
  "el 8 es puerta pero conserva su accion: espera, no se pierde");

/* La leyenda ordena y dimensiona por tier: lo que hay que probar va primero y
 * grande, lo ya medido al final y chico. El tamano es el mensaje. */
var TIERS_OK = ["now", "tool", "done"];
registered.actions.forEach(function (item) {
  assert(TIERS_OK.indexOf(item.tier) >= 0,
    "la tecla " + item.code + " no declara tier");
});
var ahora = registered.actions.filter(function (item) {
  return item.tier === "now";
}).map(function (item) { return item.code; }).sort();
assert.deepStrictEqual(ahora, ["80", "81", "82", "83", "84", "85", "86"],
  "lo pendiente de probar es la capa de H-11 y la cache de H-12, y nada mas");

function emDe(sel) {
  var m = page.match(new RegExp("#teclas \\." + sel +
                                "\\s*\\{[^}]*font-size:\\s*([0-9.]+)em"));
  assert(m, "la leyenda no define el tamano de ." + sel);
  return parseFloat(m[1]);
}
assert(emDe("now") > emDe("tool") && emDe("tool") > emDe("done"),
  "lo ya probado tiene que verse mas chico que lo que falta probar");
assert(/#keys\s*\{[^}]*overflow:\s*hidden/.test(page),
  "la franja de teclas no puede desbordar sobre el zocalo");

assert.strictEqual(byId("teclas").childNodes.length, 26,
  "la leyenda de teclas se dibuja en pantalla: en una TV no hay donde mirarla");

/* La misma leyenda es el boton: en el celular no hay teclado numerico. */
var conClick = 0;
byId("teclas").childNodes.forEach(function (row) {
  if (typeof row.onclick === "function") { conClick++; }
});
assert.strictEqual(conClick, 26,
  "cada entrada de la leyenda tiene que poder tocarse en un celular");

/* Se dibuja agrupada por tier, no en el orden del arreglo. */
var pintadas = byId("teclas").childNodes.map(function (row) {
  return row.className;
});
assert.strictEqual(pintadas[0], "op now",
  "la primera de la leyenda es lo que hay que probar");
assert.strictEqual(
  byId("teclas").childNodes[0].childNodes[0].childNodes[0].data, "80",
  "y esa primera es el lote de la visita");
var orden = pintadas.join(" ");
assert(orden.indexOf("op tool") > orden.lastIndexOf("op now"),
  "las herramientas van despues de lo que hay que probar");
assert(orden.indexOf("op done") > orden.lastIndexOf("op tool"),
  "lo ya medido va al final");

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
assert(/packageSteps\(\), capaAll\(\), cacheBatch\(\)/.test(inline[1]),
  "correr todo (1) incluye las seis mediciones de capa y la cache");
/* Las cuatro teclas de la capa, ya en dos cifras detras del 8. */
assert(/lote/.test(action("80").label), "80 = el lote de la visita H-11");
assert(/H-11/.test(action("80").detail) && /blob/.test(action("80").detail),
  "el lote lleva blob: y blob concat seguidos (arranque desde memoria)");
assert(/capa/.test(action("81").label) && /baseline/.test(action("81").label),
  "81 = capa sobre Baseline");
assert(/capa/.test(action("82").label) && /vp9/.test(action("82").label),
  "82 = capa sobre VP9");
assert(/ojo/.test(action("83").label), "83 = la capa a ojo, para el operador");

/* Sin medir, el canvas no existe (display none): la linea de base es sin capa.
 * El 83 la alterna y el 0 la apaga. */
assert.strictEqual(byId("capa").className, "off",
  "antes de medir el canvas no existe: la linea de base es sin capa");
action("83").run();
assert.strictEqual(byId("capa").className, "", "83 enciende el rectangulo");
action("83").run();
assert.strictEqual(byId("capa").className, "off", "83 otra vez lo apaga");
action("83").run();
action("0").run();
assert.strictEqual(byId("capa").className, "off", "el 0 apaga la capa");

/* --- H-12: la cache, el paquete residente --- */

assert(page.indexOf('<script src="vgencache.js"></script>') >= 0,
  "la puerta a IndexedDB vive en vgencache.js (lo reusa H-8), no en la pagina");
assert(page.indexOf('src="vgenfeed.js"') < page.indexOf('src="vgencache.js"'),
  "la cache se carga despues de las puertas del paquete");
["function stepCacheStore", "function stepCachePlay", "function stepTecho",
 "function cacheBatch", "function refreshCacheInfo", "function clearCache",
 "function manifestKeys"]
  .forEach(function (name) {
    assert(inline[1].indexOf(name) >= 0, "falta " + name);
  });
assert(/VGenCache\.keyFor\(src\.id, src\.sha256\)/.test(inline[1]),
  "la clave de cada pieza lleva su sha: pineo por contenido (CACHE-001)");
assert(/VGenCache\.prune\(db, manifestKeys\(\)/.test(inline[1]),
  "al guardar se borra lo que no este en el manifiesto vigente");
assert(/onProgress: function \(loaded, total\)/.test(inline[1]),
  "la bajada muestra progreso: en la TV una bajada muda parece colgada");
/* H-12b: el techo se mide sumando tandas chicas. Pedir 50 MB de una vez cerro
 * la app de la caja el 2026-09-04, y una app cerrada no informa ningun techo. */
assert(/TECHO_TANDA_MB = 5/.test(inline[1]),
  "el techo se mide en tandas de 5 MB, nunca de un salto (H-12b)");
assert(/TECHO_TOPE_MB = 50/.test(inline[1]),
  "se intenta hasta 50 MB acumulados y ahi se da por bueno");
assert(/VGenCache\.noise\(TECHO_TANDA_MB\)/.test(inline[1]),
  "cada tanda pide UNA tanda de ruido: nunca hay mas de 5 MB vivos");
assert(!/VGenCache\.noise\(TECHO_TOPE_MB\)/.test(inline[1]),
  "jamas se pide el tope entero de una vez");
assert(/VGenCache\.quota\(\{\}, function \(qError, used, granted\)/.test(inline[1]),
  "la cuota declarada se reporta ANTES de escribir: es el primer techo");
assert(/VGenCache\.remove\(db, "techo\." \+ i/.test(inline[1]),
  "el ruido del techo se borra despues de medir, entre o no");
assert(/r\.total === 0 && !r\.noVideo/.test(inline[1]),
  "una fila que no reproduce (guardar, techo) no puede decir ciego");

/* Las tres teclas, detras del 8 como las de la capa. */
assert(/guardar/.test(action("84").label), "84 = bajar y guardar (+ desde cache + techo)");
assert(/techo/.test(action("84").detail) && /H-12/.test(action("84").detail));
assert(/tandas de 5 MB/.test(action("84").detail),
  "la leyenda del 84 dice como se mide el techo ahora");

/* H-12b: el 83 solo prendia el canvas; en la caja quedaba el cartel de play. */
assert(/arranca VP9/.test(action("83").detail),
  "la leyenda del 83 avisa que arranca el video si no hay nada sonando");
assert(/video\.play\(\);/.test(inline[1].slice(inline[1].indexOf("function toggleCapa"))),
  "el 83 arranca el video por el mismo camino que el lote");
assert(/pide un gesto/.test(inline[1]),
  "si el WebView exige gesto, la pagina lo dice en vez de quedarse muda");
assert(/desde cache/.test(action("85").label), "85 = reproducir desde la cache");
assert(/REINICIAR/.test(action("85").detail),
  "el 85 es la tecla de despues de reiniciar: la leyenda lo dice");
assert(/borrar/.test(action("86").label), "86 = borrar la cache");

/* Sin IndexedDB (este stub no la tiene), la cabecera lo dice y la fila del 85
 * explica por que no corrio, sin explotar. */
reporte = byId("report").value;
assert(reporte.indexOf("\ncache\tno\tguardadas 0\t0 B") >= 0,
  "la cabecera del reporte dice si hay IndexedDB y cuanto hay guardado");
action("85").run();
assert.strictEqual(filas.childNodes.length, 8,
  "la primera fila de cache aparece aunque no haya base");
reporte = byId("report").value;
assert(/\ncache:base\t.*sin indexedDB/.test(reporte),
  "sin IndexedDB la fila cache:base dice por que");
action("0").run();
assert.strictEqual(filas.childNodes.length, 7);

console.log("v0 page tests: OK");
