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
/* La regla sigue siendo que TODAS LAS PIEZAS suenan en el mismo <video>: nunca
 * uno por pieza. H-18 (2026-09-04) suma UN segundo <video> y solo uno, el del
 * efecto con alfa que va encima, porque la pregunta del operador era
 * justamente si el aparato sostiene dos planos de video a la vez. */
assert.strictEqual((page.match(/<video\s+id="video"/g) || []).length, 1,
  "un solo <video> para las piezas: todas se reproducen en el mismo lugar");
assert.strictEqual((page.match(/<video\s+id=/g) || []).length, 2,
  "y exactamente uno mas, el del efecto de H-18: dos planos, no N");
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
/* La regla es que UNA MEDICION NO PAUSA lo que mide: la pieza sigue sonando
 * hasta que la proxima la reemplace, para que se vea si de verdad seguia. La
 * unica pausa del <video> de las piezas es la del 0 (cortar). H-18 agrega la
 * del segundo <video>, y esa SI corresponde: un efecto que quedara sonando
 * encima de las mediciones siguientes las ensuciaria. */
assert.strictEqual((inline[1].match(/video\.pause\(\)/g) || []).length, 1,
  "no se pausa al terminar una medicion: la unica pausa del video es la del 0");
assert.strictEqual((inline[1].match(/\.pause\(\)/g) || []).length, 2,
  "y la unica otra pausa es la del efecto de H-18, cuando su prueba termina");
assert(/node\.pause\(\);\n  node\.className = "off";/.test(inline[1]),
  "esa pausa es la del efecto: se corta y se esconde en el mismo lugar");
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

var reporte = reporteTexto();
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
assert.strictEqual(codigos.length, 32);
["0", "1", "2", "3", "4", "5", "6", "7", "8"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta la tecla " + code);
});
["70", "71", "73", "80", "81", "82", "83", "84", "85", "86", "87", "88", "89",
 "90", "91", "92", "93", "94", "95", "96", "97", "98", "99"].forEach(function (code) {
  assert(codigos.indexOf(code) >= 0, "falta el codigo compuesto " + code);
});
/* H-16: el 1 dejo de correr todo. Corre SOLO lo no consagrado; lo que corria
 * antes sigue entero en el 89. El operador lo pidio asi: "si ya tuvimos
 * claridad sobre ciertos elementos, ya quitalos de la prueba general". */
assert.strictEqual(action("1").label, "lo que falta",
  "el 1 corre solo lo que la caja todavia no consagro");
assert(/pendingSteps\(\)/.test(String(action("1").run)),
  "y lo hace con pendingSteps(), no con everything()");
assert.strictEqual(action("89").label, "correr todo",
  "correr todo no desaparece: se muda al 89");
assert(/everything\(\)/.test(String(action("89").run)),
  "el 89 es el que corre todo, consagrado incluido");
assert.strictEqual(action("89").tier, "done",
  "y por eso vive en el manual, no en la pantalla");

/* H-20: el reporte ya no vive en un <textarea>: son DOS COLUMNAS que se pintan
 * al abrirlo (95) y se cierran con el 88. Se lee abriendolo y juntando las dos,
 * que es exactamente lo que el operador ve en la foto. */
function textoDe(node) {
  return node.childNodes.length ? node.childNodes[0].data : "";
}

function reporteTexto() {
  var arriba, abajo;
  action("95").run();
  arriba = textoDe(byId("colA"));
  abajo = textoDe(byId("colB"));
  action("88").run();
  return abajo ? arriba + "\n" + abajo : arriba;
}

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
/* H-20 abre la TERCERA puerta, el 7, para el bloque de pantalla entera: el 9
 * estaba lleno (90..99) y en el 8 quedaba un solo numero. Lo que el operador
 * fijo el 2026-09-02 fue el TECHO -dos cifras, no tres-, no la cantidad de
 * puertas; y el 7 ("solo vp9") es una tecla consagrada que no se ve, asi que
 * los 900 ms que ahora espera no se los cobra a nadie. */
var PUERTAS = ["7", "8", "9"];
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
assert.deepStrictEqual(ahora,
  ["1", "70", "71", "84", "85", "87"],
  "lo pendiente: la cache, los dos videos, la pantalla entera, el bucle a ojo y el 1");

function emDe(sel) {
  var m = page.match(new RegExp("#teclas \\." + sel +
                                "\\s*\\{[^}]*font-size:\\s*([0-9.]+)em"));
  assert(m, "la leyenda no define el tamano de ." + sel);
  return parseFloat(m[1]);
}
assert(emDe("now") > emDe("tool"),
  "las herramientas se ven mas chicas que lo que falta probar");
assert(/#teclas \.done\s*\{/.test(page) === false,
  "el tier consagrado ya no se dibuja: no necesita tamano propio");
assert(/#keys\s*\{[^}]*overflow:\s*hidden/.test(page),
  "la columna de teclas no puede desbordar");

/* H-16: la leyenda es una COLUMNA A LA IZQUIERDA y la tabla se queda con el
 * alto entero, para que los renglones bajen mientras se prueba (pedido del
 * operador, 2026-09-04). */
assert(/#keys\s*\{[^}]*left:\s*0/.test(page),
  "la columna de teclas va pegada a la izquierda");
assert(/#teclas \.op\s*\{[^}]*display:\s*block/.test(page),
  "cada tecla ocupa su propio renglon: es una columna, no una franja");
assert(/byId\("keys"\)\.style\.width/.test(inline[1]),
  "el layout le da a la columna un ancho propio");
assert(/byId\("keys"\)\.style\.top = midTop/.test(inline[1]),
  "la columna arranca arriba, no debajo del video");
assert(/px\(byId\("side"\), sideX, midTop, w - sideX - 12, midH\)/.test(inline[1]),
  "la tabla toma el alto entero de la franja del medio");

/* Al menos 10 teclas a la vista: menos que eso obliga a mirar el manual para
 * lo de todos los dias, y el operador prueba con el control en la mano. */
var visibles = byId("teclas").childNodes.length;
assert(visibles >= 10,
  "tienen que quedar al menos 10 teclas a la vista, y hay " + visibles);
assert.strictEqual(visibles, 14,
  "hoy son 14: las 6 de ahora y las 8 herramientas");
var ocultas = registered.actions.filter(function (item) {
  return item.tier === "done";
}).length;
assert.strictEqual(visibles + ocultas, codigos.length,
  "ninguna tecla se pierde: la que no se ve, sigue andando");

/* La misma leyenda es el boton: en el celular no hay teclado numerico. */
var conClick = 0;
byId("teclas").childNodes.forEach(function (row) {
  if (typeof row.onclick === "function") { conClick++; }
});
assert.strictEqual(conClick, visibles,
  "cada entrada de la leyenda tiene que poder tocarse en un celular");

/* Se dibuja agrupada por tier, no en el orden del arreglo. */
var pintadas = byId("teclas").childNodes.map(function (row) {
  return row.className;
});
assert.strictEqual(pintadas[0], "op now",
  "la primera de la leyenda es lo que hay que probar");
assert.strictEqual(
  byId("teclas").childNodes[0].childNodes[0].childNodes[0].data, "84",
  "y esa primera es la cache, que es lo que la caja todavia debe");
var orden = pintadas.join(" ");
assert(orden.indexOf("op tool") > orden.lastIndexOf("op now"),
  "las herramientas van despues de lo que hay que probar");
assert(orden.indexOf("op done") < 0,
  "lo ya consagrado no se dibuja: se busca en el manual");

/* --- H-16: el manual de teclas --- */

var manual = fs.readFileSync(
  path.join(__dirname, "..", "docs", "MANUAL-TECLAS-V0.md"), "utf8");
registered.actions.forEach(function (item) {
  if (item.tier !== "done") { return; }
  assert(manual.indexOf("`" + item.code + "`") >= 0,
    "la tecla oculta " + item.code + " no esta en el manual: quedaria perdida");
});
assert(/`83`/.test(manual) && /`1`/.test(manual),
  "el manual tambien lista lo que se ve, para poder leerlo todo de una");

/* --- H-16: Hobo, la fuente de la capa --- */

/* El operador la eligio por defecto el 2026-09-04 ("que sea la fuente por
 * defecto asi no agrego mas funciones") y ya la habia probado en ESE WebView
 * desde CSS. Lo que estas pruebas cuidan es que no se pueda mentir sobre con
 * que letra se dibujo, y que la falta de la fuente no rompa nada. */

assert(/@font-face\s*\{[^}]*font-family:\s*"Hobo"/.test(page),
  "la capa declara la fuente Hobo con @font-face");
assert(/url\("HoboStd\.ttf"\)\s*format\("opentype"\)/.test(page),
  "el archivo es OpenType con contornos CFF aunque diga .ttf: declararlo " +
  "como truetype es la forma facil de que un WebView viejo lo descarte");
assert(/#hobo\s*\{[^}]*font-family:\s*"Hobo"/.test(page),
  "un nodo del documento usa la fuente: en Chromium 70 un canvas no siempre " +
  "alcanza para disparar la descarga");
/* La prohibicion es sobre el CODIGO, no sobre la prosa: los comentarios de la
 * pagina nombran la API para explicar por que no se usa, y eso hay que poder
 * escribirlo. Se mide contra el texto sin comentarios. */
var pageCode = page.replace(/\/\*[\s\S]*?\*\//g, " ");
assert.strictEqual(/document\.fonts/.test(pageCode), false,
  "document.fonts devuelve Promise y el piso ES5 la prohibe");

assert(/CAPA_FUENTE_MS = 3000/.test(inline[1]),
  "se espera hasta 3 s a que llegue la fuente, y ni un ms mas");
assert(/measureText\(texto\)/.test(inline[1]),
  "la llegada de la fuente se detecta MIDIENDO, no preguntando");
/* Monospace le da a toda letra el mismo avance; cualquier proporcional no. Por
 * eso la prueba es M contra i EN LA MISMA familia, y no una frase contra un
 * ancho de referencia: medido el 2026-09-04, "ASCILINE 0123" difiere apenas
 * 1,5 px de 285 entre Hobo y monospace, y en otro aparato podian coincidir. */
assert(/anchoDe\("MMMMM"\)/.test(inline[1]) && /anchoDe\("iiiii"\)/.test(inline[1]),
  "se comparan dos letras de ancho muy distinto, en la misma familia");
assert(/ctx\.font = "40px \\"Hobo\\", monospace"/.test(inline[1]),
  "las dos medidas se toman pidiendo la fuente, no monospace pelado");
assert.strictEqual(/anchoDe\("ASCILINE 0123"\)/.test(inline[1]), false,
  "la deteccion por frase quedo atras: el margen era de 1,5 px");
assert(/ctx\.font = "bold " \+ Math\.round\(h \* 0\.5\) \+ "px " \+ capaFuenteFamily\(\)/
  .test(inline[1]),
  "la capa dibuja con la fuente elegida, no con monospace fijo");
assert.strictEqual(/px monospace"/.test(inline[1]), false,
  "no puede quedar ninguna pintada clavada en monospace");
assert(/"; fuente: " \+\s*\n?\s*capaFuente\.name/.test(inline[1]) ||
       /fuente: " \+/.test(inline[1]),
  "cada fila de capa declara con que fuente se dibujo");
assert(/"\\tfuente " \+ capaFuente\.name/.test(inline[1]),
  "y la cabecera del reporte tambien, que es lo que sale en la foto");

/* El archivo servido, tal cual se publica. */
var fuentePath = path.join(__dirname, "..", "frontend", "HoboStd.ttf");
assert(fs.existsSync(fuentePath),
  "la fuente vive en el repo: lo desplegado se guarda antes de subirlo");
var fuenteBuf = fs.readFileSync(fuentePath);
assert.strictEqual(fuenteBuf.length, 31444, "la fuente que paso el operador");
assert.strictEqual(fuenteBuf.slice(0, 4).toString("latin1"), "OTTO",
  "OpenType con contornos CFF: por eso el format() dice opentype");

/* --- Correr el 5 en un aparato sin MSE: la fila aparece con su error y el
 * resto no explota; el 0 la limpia. --- */
action("5").run();
assert.strictEqual(filas.childNodes.length, 8,
  "la primera prueba de paquete agrega su fila sintetica");
reporte = reporteTexto();
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
assert(reporteTexto().indexOf("\ncapa\t" + byId("capa").width + "x" +
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
reporte = reporteTexto();
assert(reporte.indexOf("\ncache\tno\tguardadas 0\t0 B") >= 0,
  "la cabecera del reporte dice si hay IndexedDB y cuanto hay guardado");
action("85").run();
assert.strictEqual(filas.childNodes.length, 8,
  "la primera fila de cache aparece aunque no haya base");
reporte = reporteTexto();
assert(/\ncache:base\t.*sin indexedDB/.test(reporte),
  "sin IndexedDB la fila cache:base dice por que");
action("0").run();
assert.strictEqual(filas.childNodes.length, 7);

console.log("v0 page tests: OK");

/* H-16: la tabla es lo que el operador mira mientras prueba, y los renglones
 * tienen que BAJAR solos: en una TV no hay como scrollear a mano. */
assert(/#side\s*\{[^}]*overflow-y:\s*auto/.test(page),
  "la tabla puede desplazarse: una corrida larga no entra en ningun alto");
assert(/function scrollAlFinal\(\)/.test(inline[1]) &&
       /scrollAlFinal\(\);\n  writeReport\(\)/.test(inline[1]),
  "cada redibujado deja a la vista el ultimo renglon, no el primero");

/* H-16: la columna de teclas no puede partir una etiqueta. Medido en el
 * navegador el 2026-09-04: a 399 px de ancho, el 19 % dejaba "cache: gua...". */
assert(/keysW = Math\.max\(Math\.round\(w \* 0\.19\),/.test(inline[1]),
  "la columna tiene un piso de ancho, no solo un porcentaje");
assert(/Math\.min\(200, Math\.round\(w \* 0\.34\)\)/.test(inline[1]),
  "y ese piso no puede comerse mas de un tercio de una pantalla angosta");
assert(/#keys\s*\{[^}]*box-sizing:\s*border-box/.test(page),
  "el ancho de la columna incluye su relleno: si no, se monta sobre el video");

/* H-12b/H-16: el 83 apretado apenas abre la pagina. Probado en el navegador el
 * 2026-09-04: si el manifiesto todavia no llego, la capa quedaba encendida
 * sobre un <video> vacio, que es el mismo sintoma que el operador reporto en la
 * caja. Reintentar es mas util que avisar: el operador aprieta una vez. */
assert(/CAPA_OJO_ESPERA_MS = 6000/.test(inline[1]),
  "el 83 espera al manifiesto en vez de rendirse");
assert(/capaOjoArranca\(desde\)/.test(inline[1]),
  "y reintenta hasta que la pieza base este");
assert(/if \(capa\.load !== "rect"\) \{ return; \}/.test(inline[1]),
  "si mientras tanto se apago la capa, el reintento se corta solo");

/* --- H-18: dos <video> a la vez --- */

/* La pregunta del operador (2026-09-04) fue si un efecto puede SER video: una
 * pieza con alfa encima del loop, compuesta por el navegador, en vez de
 * horneada o dibujada a mano. Lo que estas pruebas cuidan es que el segundo
 * <video> exista de verdad, vaya ENCIMA sin crecer hacia abajo, y que la fila
 * traiga los cuadros de LOS DOS: si solo se midiera el de abajo, la prueba no
 * contestaria la pregunta. */

assert.strictEqual((page.match(/<video\s+id="efecto"/g) || []).length, 1,
  "hay un segundo <video> declarado, no un canvas ni un div");
assert(/#efecto\s*\{[^}]*position:\s*absolute/.test(page),
  "va posicionado encima, no en el flujo");
assert(/#efecto\.off\s*\{\s*display:\s*none/.test(page),
  "y apagado no ocupa nada");
assert(page.indexOf('<canvas id="capa" class="off"></canvas>\n<video id="efecto"') >= 0,
  "el segundo video va DESPUES del canvas: encima, no debajo");
assert(/placeEfecto\(stageX, midTop \+ Math\.round\(\(midH - vh\) \/ 2\), vw, vh\)/
  .test(inline[1]),
  "el layout lo coloca sobre el recuadro del video, no en otro lado");
/* H-18b (operador, 2026-09-04): EXACTAMENTE el mismo rectangulo que el de
 * abajo. Un recuadro encogido y corrido mide otra cosa -un video chico- y
 * ademas no deja ver si la composicion ocurrio. */
assert(/function placeEfecto\(x, y, w, h\) \{\n  px\(byId\("efecto"\), x, y, w, h\);\n\}/
  .test(inline[1]),
  "el efecto va exactamente sobre el video de abajo, sin encoger ni correr");
assert(!/Math\.round\(w \* 0\.26\)/.test(inline[1]),
  "y no queda rastro del recuadro chico que el operador rechazo");

assert(/function stepDosVideos\(\)/.test(inline[1]),
  "la prueba de los dos videos existe");
assert(/\{ loop: true, efecto: "v0-vp9-alpha" \}/.test(inline[1]),
  "el de abajo va en bucle y el de arriba es la pieza con alfa");
assert(/findPiece\("v0-vp9"\)/.test(inline[1]),
  "el de abajo es VP9: el codec base que eligio el operador el 2026-09-04");
assert(/caidos " \+ efecto\.dropped \+\s*\n?\s*"\/" \+ efecto\.total/.test(inline[1]) ||
       /efecto\.dropped/.test(inline[1]) && /efecto\.total/.test(inline[1]),
  "la fila trae los cuadros del de ARRIBA tambien");
assert(/if \(o\.efecto\) \{ startEfecto\(o\.efecto\); \}/.test(inline[1]) &&
       /if \(o\.efecto\) \{ stopEfecto\(\); \}/.test(inline[1]),
  "arranca con la medicion y se corta con ella: nunca queda sonando solo");
assert(/stopEfecto\(\);\n  salirEntera\(\);\n  byId\("alphaBg"\)\.className = "";/
  .test(inline[1]),
  "el 0 tambien lo apaga: en una TV no hay otra forma de callarlo");

/* Y entra en lo que corre el 1, porque todavia no lo contesto la caja. La
 * forma exacta del concat se verifica abajo, con H-20 adentro. */
assert(/stepDosVideos\(\)\]/.test(inline[1]),
  "el 1 corre los dos videos: lo no consagrado, nada mas");
assert(/dos videos/.test(action("87").label), "87 = dos videos a la vez");
assert(/H-18/.test(action("87").detail));

/* H-18: el contador del de ARRIBA se arma cuando empieza a sonar, no al pedirle
 * que suene. Medido el 2026-09-04 corriendo la prueba dos veces seguidas: con
 * la base tomada antes, la segunda pasada informaba "1/2 caidos" -la resta iba
 * contra los contadores de la pasada anterior, que load() acababa de poner en
 * cero-. Un contador que solo acierta la primera vez no sirve para nada. */
assert(/function armEfecto\(\)/.test(inline[1]),
  "la linea de base del efecto se arma aparte");
assert(/if \(!\(node\.currentTime > 0\)\) \{ return; \}/.test(inline[1]),
  "y se arma cuando el de arriba EMPEZO A SONAR, no antes");
assert(/if \(o\.efecto\) \{ armEfecto\(\); \}/.test(inline[1]),
  "se intenta armar en cada vuelta de la medicion");
assert(/efecto\.error = "el de arriba no arranco"/.test(inline[1]),
  "si nunca sono, la fila lo dice en vez de mostrar un cero enganoso");

/* --- H-20: a pantalla entera, y el reporte en dos columnas --- */

/* Dos pedidos del operador del 2026-09-04, despues de la foto de esa noche:
 * medir con el video ocupando toda la superficie ("suele bajar rendimiento") y
 * que el reporte entre en la pantalla, porque la foto corto en la novena fila.
 * En una TV no se scrollea ni se copia texto: lo que no entra, no existe. */

assert(page.indexOf('<pre id="colA">') >= 0 && page.indexOf('<pre id="colB">') >= 0,
  "el reporte se pinta en dos columnas");
assert.strictEqual(/<textarea/.test(page), false,
  "y ya no en un <textarea>: con el foco adentro, los numeros eran texto y el " +
  "mando dejaba de responder");
assert(/#reportCols pre\s*\{[^}]*white-space:\s*pre-wrap/.test(page),
  "las columnas envuelven: una linea larga no puede salirse de su columna");
assert(/#reportCols pre\s*\{[^}]*overflow:\s*hidden/.test(page),
  "y no scrollean: lo que no entra hay que achicarlo, no esconderlo");
assert(/function paintReport\(\)/.test(inline[1]), "el reporte se pinta aparte");
assert(/for \(cien = 140; cien >= 24; cien -= 6\)/.test(inline[1]),
  "la letra arranca grande y se achica hasta que entra, con un piso");
assert(/colA\.scrollHeight <= colA\.clientHeight/.test(inline[1]),
  "quien decide si entro es el alto MEDIDO, no la estimacion del reparto");

/* Las dos columnas se reparten de verdad: si todo cayera en una, seguiriamos
 * con el mismo problema con otra forma. */
action("95").run();
assert(textoDe(byId("colA")).indexOf("# pack v0") === 0,
  "la primera columna arranca con la cabecera del reporte");
assert(textoDe(byId("colB")).length > 0,
  "y la segunda recibe su mitad: el reparto no puede quedar todo de un lado");
action("88").run();
assert.strictEqual(byId("full").className, "",
  "el 88 cierra el reporte: es la tecla de volver que pidio el operador");
assert(/cerrar reporte/.test(action("88").label));
assert(/dos columnas/.test(action("95").detail));

/* La pantalla entera. Lo que se mide es el video ocupando la superficie -en la
 * caja, 3840x2160 sobre un panel de 1280x720-; la API de fullscreen es un
 * extra que se pide y se DECLARA, nunca se supone. */
assert(/pantalla entera/.test(action("70").label), "70 = pantalla entera");
assert(/H-20/.test(action("70").detail));
assert(/entera a ojo/.test(action("73").label), "73 = prender y apagar, sin medir");
assert(/function layoutEntera\(w, h\)/.test(inline[1]),
  "la pantalla entera tiene su propio layout");
assert(/vh = Math\.round\(w \* 9 \/ 16\)/.test(inline[1]),
  "respeta 16:9 en vez de estirar: un video deformado se compara contra otra cosa");
assert(/if \(entera\.on\) \{ layoutEntera\(w, h\); return; \}/.test(inline[1]),
  "y el layout normal se aparta cuando esta prendida");
assert(/function esconderTodo\(si\)/.test(inline[1]) &&
       /\["head", "keys", "side"\]/.test(inline[1]),
  "se esconde todo menos el zocalo, que dice como se sale");
assert(/function dioLaApi\(\)/.test(inline[1]),
  "la fila declara si el WebView concedio la pantalla completa de verdad");
assert(/webkitRequestFullscreen/.test(inline[1]),
  "se prueban los dos nombres: este WebView es Chromium 70");
assert(/salirEntera\(\);/.test(inline[1].slice(inline[1].indexOf("function stopAll"))),
  "el 0 tambien devuelve la pantalla: en una TV no hay otra salida");

/* Cuatro escalones, porque lo que importa no es un numero sino donde se rompe:
 * el video solo, con la capa, con el efecto, y todo junto (la forma del
 * producto). Entre medio, entrar y salir. */
assert(/function enteraSteps\(\)/.test(inline[1]));
["entera:solo", "entera:capa", "entera:dos", "entera:todo"].forEach(function (id) {
  assert(inline[1].indexOf('"' + id + '"') >= 0, "falta el paso " + id);
});
assert(/return techoSteps\(\)\.concat\(\[stepDosVideos\(\)\], enteraSteps\(\)\)/
  .test(inline[1]),
  "el 1 suma la pantalla entera: es lo que la caja todavia no contesto");

/* H-21: los dos planos A OJO, en bucle y sin cortes.
 *
 * El operador vio "que se corta el video cuando son dos superpuestos". Los
 * cortes son de la MEDICION -el 70 corre cuatro escalones y entre uno y otro
 * para, cambia la carga y arranca de nuevo-, no del aparato. Pero la pregunta
 * de fondo no la contesta ningun contador: esta tecla existe para mirarlo
 * seguido, y por eso NO agrega fila al reporte. */
function cuerpoDe(nombre) {
  var desde = inline[1].indexOf("function " + nombre + "(");
  var hasta = inline[1].indexOf("\n}", desde);
  assert(desde >= 0 && hasta > desde, "no esta la funcion " + nombre);
  return inline[1].slice(desde, hasta);
}

assert(/dos a ojo/.test(action("71").label), "71 = los dos planos a ojo");
assert(/H-21/.test(action("71").detail));
assert(/BUCLE/.test(action("71").detail),
  "la leyenda tiene que decir que no corta: es lo que lo distingue del 70");
var bucleCuerpo = cuerpoDe("toggleBucle");
assert(/entrarEntera\(\);/.test(bucleCuerpo),
  "arranca a pantalla entera, que es como lo pidio el operador");
assert(/startEfecto\("v0-vp9-alpha"\);/.test(bucleCuerpo),
  "son los dos planos, no uno");
assert(/video\.loop = true;/.test(bucleCuerpo),
  "en bucle: la pieza no puede terminarse mientras se la mira");
assert(/layout\(\);/.test(bucleCuerpo),
  "layout despues de startEfecto: el de arriba va en el rectangulo exacto");
assert(bucleCuerpo.indexOf("addExtra") < 0 &&
       bucleCuerpo.indexOf("measure(") < 0,
  "no mide y no agrega fila: muestra");
assert(/setInterval\(tickBucle, 1000\)/.test(bucleCuerpo),
  "el zocalo lleva los caidos vivos, para que el ojo y los numeros se miren juntos");
var tick = cuerpoDe("tickBucle");
assert(/armEfecto\(\);/.test(tick),
  "la base del de arriba se toma cuando empieza a sonar, no al pedir el play");
assert(/bucle\.armed && video\.currentTime > 0/.test(tick),
  "y la del de abajo tambien");
assert(/pararBucle\(\);/.test(cuerpoDe("stopAll")),
  "el 0 apaga el reloj: si no, sigue escribiendo en el zocalo despues de cortar");
assert(cuerpoDe("pararBucle").indexOf("stopAll") < 0,
  "pararBucle solo apaga el reloj; si tambien apagara todo, se llamarian en circulo");

/* H-12b: la red, declarada.
 *
 * El operador descartó «arrancar sin red»: la app de la caja tiene validaciones
 * intermedias que la piden, así que ese camino no se puede probar y no se
 * insiste. Lo que SÍ puede hacer es cortar la red con la página ya abierta, y
 * ahí el `85` es una prueba limpia -lee de IndexedDB y reproduce desde un
 * `blob:`, sin tocar la red-. Para que la foto pruebe algo, la cabecera y la
 * fila tienen que DECIR si había red. */
assert(/function redDice\(\)/.test(inline[1]));
assert(/navigator\.onLine/.test(inline[1]),
  "el dato sale del navegador, no de una suposicion");
assert(/red.t" \+ redDice\(\)\);/.test(inline[1]),
  "la cabecera lleva el campo red");
assert(/"desde cache; " \+ \(record\.bytes \|\| 0\) \+ " B; red " \+/.test(inline[1]),
  "y la fila de cache tambien: es la que prueba que los bytes salieron del aparato");

/* Y anda: el stub no declara onLine, asi que la cabecera dice "?" en vez de
 * inventar un "si". */
assert(/red\t\?/.test(reporteTexto()),
  "sin navigator.onLine se declara ?, nunca se supone que habia red");
navigatorStub.onLine = false;
action("0").run();
assert(/red\tno/.test(reporteTexto()),
  "con la red cortada la cabecera lo dice");
navigatorStub.onLine = true;
action("0").run();
assert(/red\tsi/.test(reporteTexto()));

/* H-22: el zocalo dice lo ultimo que el aparato mando por el teclado.
 *
 * En el WebView de un Smart TV con Android no entraba ningun numero. Con esta
 * linea, una foto separa dos fallas que se ven iguales: si nunca cambia de
 * "ninguna todavia", los eventos no llegan a la pagina; si cambia y el numero
 * igual no hace nada, llegan por un campo que no estabamos mirando. */
assert(/ninguna todavia/.test(textoDe(byId("env"))),
  "antes de la primera tecla, el zocalo lo dice");
assert(typeof registered.onKey === "function",
  "la pagina le pide al mando que le cuente cada tecla");
registered.onKey("keydown kc=0 w=0 cc=0 key=7 code= foco=BODY", 1);
assert(/tecla 1: keydown/.test(textoDe(byId("env"))) &&
       /key=7/.test(textoDe(byId("env"))),
  "y despues trae los campos crudos: " + textoDe(byId("env")));

console.log("v0 page tests (H-18b + H-20 + H-21 + red + H-22): OK");
