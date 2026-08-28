"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "el player tradicional debe conservar controlador inline");
assert(page.indexOf('DEFAULT_SRC = "./outputs/clip.asclv"') >= 0,
  "ambos players deben compartir la ruta estable del despliegue plano");
assert(page.indexOf('src="reader.js"') < page.indexOf('src="reader-v2.js"'));
assert(page.indexOf('src="reader-v2.js"') < page.indexOf('src="reader-factory.js"'));
assert(page.indexOf('src="reader-factory.js"') < page.indexOf('src="render-canvas2d.js"'));
assert(page.indexOf("window.ASCILINEReader || window.ASCL") >= 0,
  "v1 mantiene fallback y v2 usa el factory");
assert(page.indexOf('s==="ASCLVID1" || s==="ASCLVID2"') >= 0);
assert(page.indexOf("u[7]===49 || u[7]===50") >= 0);
assert(page.indexOf("16+asclLen+audioLen!==buf.byteLength") >= 0,
  "debe rechazar truncado y bytes extra");
assert(page.indexOf("bytes[7]-48!==bytes[20]") >= 0,
  "envelope e interior deben declarar la misma version");
assert(page.indexOf('"ASCL v"+h.version') >= 0,
  "la interfaz debe mostrar la version cargada");

/* W-14: robustez del player tradicional */
assert(page.indexOf("renderer.dispose(true)") >= 0,
  "pickRenderer debe liberar el renderer anterior (contexto WebGL vivo)");
assert(page.indexOf("w.dispose(true)") >= 0,
  "un intento WebGL fallido no debe abandonar su contexto");
assert(inline[1].indexOf("qs(\"src\")") < 0 && inline[1].indexOf("?src=") < 0 &&
  /var src=DEFAULT_SRC;/.test(inline[1]),
  "sin ?src= arbitrario: la carga automatica usa solo la ruta estable");
assert(/try \{\s*reader\.seek\(target\);\s*renderer\.draw\(reader\);\s*\} catch/.test(inline[1]),
  "el loop debe capturar excepciones de seek/draw");
assert(inline[1].indexOf("stop();") >= 0 &&
  inline[1].indexOf("Error de reproduccion") >= 0,
  "un frame corrupto debe detener el loop y pausar el audio");
assert(page.indexOf("nativeRequestFrame && nativeCancelFrame") >= 0,
  "requestFrame/cancelFrame deben elegirse como par");
assert(page.indexOf("nativeRequestFrame.call(window,fn)") >= 0 &&
  page.indexOf("nativeCancelFrame.call(window,id)") >= 0,
  "los nativos deben invocarse con window como receptor");

assert.strictEqual(/\b(?:let|const|class)\b|=>|`/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("traditional player page tests: OK");
