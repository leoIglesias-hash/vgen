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
assert(page.indexOf('s==="ASCLVID1" || s==="ASCLVID2" || s==="ASCLVID3"') >= 0);
assert(page.indexOf("u[7]===49 || u[7]===50 || u[7]===51") >= 0);
assert(page.indexOf("headerSize+asclLen+audioLen+metaLen!==buf.byteLength") >= 0,
  "debe rechazar truncado y bytes extra (header v3 de 20 B incluido)");
assert(page.indexOf("bytes[7]-48!==bytes[headerSize+4]") >= 0,
  "envelope e interior deben declarar la misma version");
assert(page.indexOf("bytes[7]===51?20:16") >= 0,
  "F6-3: el header ASCLVID3 mide 20 bytes (meta_len)");
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
assert(/try \{[\s\S]{0,320}reader\.seek\(target\);[\s\S]{0,40}renderer\.draw\(reader\);\s*\} catch/.test(inline[1]),
  "el loop debe capturar excepciones de seek/draw");

/* W-22: el motor compartido tambien acá. Esta es la página de laboratorio: si
   midiera con otra cadencia, comparar renderers acá no diría nada del
   producto. */
assert(page.indexOf('<script src="playloop.js"></script>') >= 0);
assert(page.indexOf('src="playloop.js"') < page.indexOf("<script>"),
  "playloop.js se carga antes del inline que lo usa");
assert(inline[1].indexOf("window.ASCILINEPlayLoop.create({ now:now })") >= 0);
assert(inline[1].indexOf("engine.target(clockFrames(),reader.header.fps)") >= 0);
assert(/adopted=engine\.exchange\(target,reader\);[\s\S]{0,140}renderer\.reader=reader;/.test(inline[1]),
  "adoptar el keyframe adelantado reapunta el renderer al reader adoptado");
assert(inline[1].indexOf("engine.idle(reader,target)") >= 0,
  "los callbacks que no cambian de cuadro ofrecen su tiempo muerto al motor");
assert(inline[1].indexOf("engine.attach(readerAPI,buf,byteOffset,byteLength)") >= 0);
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
