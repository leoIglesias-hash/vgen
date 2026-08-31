"use strict";

var assert = require("assert");
var crypto = require("crypto");
var fs = require("fs");
var path = require("path");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "tv-player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);
var refreshFunction = page.match(/function refreshCurrentVideo\(\)\{([\s\S]*?)\n  \}\n\n  downloadButton\.onclick/);
var demoPath = path.join(__dirname, "..", "outputs", "clip.asclv");
var requireDemo = process.env.ASCLV_REQUIRE_RELEASE_ARTIFACT === "1";
var demo = fs.existsSync(demoPath) ? fs.readFileSync(demoPath) : null;

assert(inline, "la pagina TV debe contener su controlador inline");
assert(refreshFunction, "debe existir la operacion de actualizacion completa");
assert(page.indexOf("./outputs/clip.asclv") >= 0,
  "la pagina debe conservar la ruta manual ./outputs/clip.asclv");
assert(page.indexOf("../outputs/TKN-2441-GANADOR-graphic-kmeans.asclv") < 0);
assert(page.indexOf("Iniciar descarga") >= 0);
assert(page.indexOf("Limpiar cach&eacute; / descargar de nuevo") >= 0,
  "el menu tecnico debe explicar claramente la actualizacion del archivo");
assert(page.indexOf('title="Menu tecnico">MENU</button>') >= 0,
  "el acceso al menu debe ser reconocible incluso sin tecla numerica");
assert(page.indexOf("background:rgba(20,20,20,.42)") >= 0 &&
  page.indexOf("opacity:.52") >= 0,
  "el hotspot debe quedar visible de forma translucida sobre el video");
assert(page.indexOf("opacity:.06") < 0,
  "el acceso anterior era demasiado invisible en una TV");
assert(page.indexOf("No borra la cach&eacute; global") >= 0,
  "el control no debe presentarse como borrado de cache global");
assert(page.indexOf("tv-controller.js") >= 0);
assert(page.indexOf("cache-refresh.js") >= 0);
assert(page.indexOf("reader-v2.js") >= 0,
  "el TV debe cargar el reader regional v2 sin retirar v1");
assert(page.indexOf("reader-factory.js") >= 0,
  "el despacho debe depender de la version interna ASCL");
assert(page.indexOf("window.ASCILINEReader || window.ASCL") >= 0,
  "v1 debe conservar fallback si falta el factory nuevo");
assert(page.indexOf("render-canvas2d.js") >= 0);
assert(page.indexOf("render-webgl.js") >= 0);
assert(page.indexOf("beginDownload(false)") >= 0, "debe intentar precarga automatica");
assert(page.indexOf("beginDownload(true)") >= 0, "debe permitir descarga manual");
assert(page.indexOf("beginDownload(true,true)") >= 0,
  "la actualizacion debe forzar una URL nueva sin cambiar DEFAULT_SRC");
assert(page.indexOf("setRequestHeader(\"Cache-Control\",\"no-cache\")") >= 0);
assert(page.indexOf("setRequestHeader(\"Pragma\",\"no-cache\")") >= 0);
assert(page.indexOf("ASCILINE_ASCLV_REFRESH_V1") >= 0,
  "el token de actualizacion debe persistir cuando localStorage esta disponible");
assert(page.indexOf("headline.innerHTML") < 0 && page.indexOf("detail.innerHTML") < 0,
  "errores XHR y del parser deben mostrarse como texto, no interpretarse como HTML");
assert(page.indexOf("setNodeText(headline,title)") >= 0,
  "el mensaje TV debe conservar fallback textual para navegadores antiguos");
assert(page.indexOf("try { cacheStorage=window.localStorage") >= 0,
  "el acceso a localStorage debe tolerar navegadores que lo bloquean");
assert(page.indexOf("stopButtonEvent(event)") >= 0,
  "los controles tecnicos no deben propagar el gesto al fullscreen");
assert(page.indexOf("hotspotGesture.accept") >= 0);
assert(page.indexOf("refreshGesture.accept") >= 0);
assert(page.indexOf("try { old.width=1; old.height=1; }") >= 0,
  "el canvas viejo debe soltar su backing store antes de la descarga");
assert(page.indexOf("replacement.width=1") >= 0);
assert(refreshFunction[1].indexOf("stop(false)") >= 0);
assert(refreshFunction[1].indexOf("ready=false") >= 0);
assert(refreshFunction[1].indexOf("releaseAudio()") >= 0);
assert(refreshFunction[1].indexOf("discardLoadedVideo()") >= 0);
assert(refreshFunction[1].indexOf("downloadButton.style.display=\"block\"") >= 0,
  "un fallo posterior debe dejar visible el reintento");
assert(refreshFunction[1].indexOf("beginDownload(true,true)") >= 0);
assert(refreshFunction[1].indexOf("releaseAudio()") <
  refreshFunction[1].indexOf("beginDownload(true,true)"));
assert(refreshFunction[1].indexOf("discardLoadedVideo()") <
  refreshFunction[1].indexOf("beginDownload(true,true)"));
/* Todo lo que puede retener un video entero se suelta al descartar, y el
   renderer se suelta ANTES que el reader que estaba dibujando. Se verifica por
   contenido y orden, no como bloque literal: desde W-20 hay un segundo reader
   en el medio y un bloque literal solo obligaría a reescribir el test. */
var discardBody = page.match(/function discardLoadedVideo\(\)\{([\s\S]*?)\n  \}/);
assert(discardBody, "debe existir la operación de descarte del video cargado");
assert(discardBody[1].indexOf("disposeRenderer(true)") >= 0);
assert(discardBody[1].indexOf("engine.detach()") >= 0,
  "W-20: el reader de pre-decode también retiene un `cells` entero");
assert(discardBody[1].indexOf("\n    reader=null;") >= 0);
assert(discardBody[1].indexOf("lastShown=-1") >= 0);
assert(discardBody[1].indexOf("freshCanvas()") >= 0);
assert(discardBody[1].indexOf("clipBuffer=null") >= 0,
  "el ArrayBuffer del clip no debe quedar retenido por el player");
assert(discardBody[1].indexOf("disposeRenderer(true)") <
  discardBody[1].indexOf("\n    reader=null;"),
  "el renderer se suelta antes que el reader que estaba dibujando");
assert(page.indexOf("webglcontextlost") >= 0,
  "una perdida de contexto GPU debe activar el fallback Canvas");
assert(page.indexOf("fallbackToCanvas(true)") >= 0);
assert(page.indexOf("fallbackToCanvas(false)") >= 0,
  "una excepcion de draw WebGL tambien debe degradar a Canvas");
assert(page.indexOf("function drawCurrent()") >= 0);
assert(page.indexOf("function seekAndDraw(index)") >= 0,
  "todos los cambios de frame deben pasar por el draw protegido");
assert(page.indexOf("previous.dispose(releaseContext===true)") >= 0,
  "el refresco debe liberar recursos GPU de forma explicita");
assert(page.indexOf("stop(false);\n          ready=false;\n          releaseAudio();\n          discardLoadedVideo()") >= 0,
  "un bundle invalido debe liberar audio, reader, canvas y renderer parciales");
assert(page.indexOf("activeXHR!==xhr") >= 0,
  "una respuesta XHR vieja no debe pisar un reintento nuevo");
assert(page.indexOf("lastDownloadTouch") >= 0,
  "touch + click sintetico no deben iniciar dos descargas");
assert(page.indexOf("bytes[7]===49 || bytes[7]===50 || bytes[7]===51") >= 0,
  "la descarga debe reconocer ASCLVID1, ASCLVID2 y ASCLVID3");
assert(page.indexOf("headerSize+videoLength+audioLength+metaLength!==buffer.byteLength") >= 0,
  "el bundle no debe aceptar truncado ni bytes anexados");
assert(page.indexOf("bytes[7]===51?20:16") >= 0,
  "el header ASCLVID3 mide 20 bytes (meta_len)");

/* CACHE-001 (F6-4): puntero mutable -> clip versionado inmutable */
assert(page.indexOf('var POINTER_SRC=POINTER_DIR+"clip.current.txt"') >= 0);
assert(page.indexOf('parseClipPointer(pointerXHR.responseText||"")') >= 0,
  "el puntero se valida con el parser canonico");
assert(page.indexOf("downloadVideo(manual,forceRefresh,POINTER_DIR+name,true)") >= 0,
  "un puntero valido descarga el clip versionado como inmutable");
assert(page.indexOf("forceRefresh && !immutable && xhr.setRequestHeader") >= 0,
  "un recurso versionado por contenido nunca se fuerza a no-cache");
assert(page.indexOf("cacheTokens.url(forceRefresh===true),false") >= 0,
  "el fallback al clip.asclv historico conserva el token de renovacion");
/* W-19: el player informa el tamaño de presentación y vuelve a presentar si el
   renderer cambió su backing store (redimensionarlo lo deja en blanco). */
assert(page.indexOf("renderer.setPresentationSize(width,height)") >= 0,
  "fitCanvas debe informar el tamaño de presentación al renderer");
assert(page.indexOf("renderer.present()") >= 0,
  "un cambio de backing store exige volver a presentar sin re-decodificar");
assert(page.indexOf("var scaleMode=qs(\"scale\")===\"int\" ? \"int\" : \"fit\"") >= 0,
  "el escalado entero es opt-in por query string: el default sigue siendo llenar el panel");

/* W-20 + W-22: cadencia anclada al display y pre-decode del próximo keyframe,
   con la maquinaria en el motor compartido (frontend/playloop.js). La página
   solo aporta el reloj maestro, el reader y el renderer; la matemática de la
   cadencia se verifica una vez en tests/test_playloop.js. */
assert(page.indexOf('<script src="playloop.js"></script>') >= 0,
  "el motor compartido tiene que estar cargado antes del controlador inline");
assert(page.indexOf('src="playloop.js"') < page.indexOf("<script>"),
  "playloop.js se carga antes del inline que lo usa");
assert(page.indexOf("window.ASCILINEPlayLoop.create({") >= 0);
assert(page.indexOf("function pacedTarget()") >= 0);
assert(page.indexOf("engine.target(clockFrames(),reader.header.fps)") >= 0,
  "el reloj maestro de esta página (el audio, si hay) sigue siendo suyo");
assert(page.indexOf("var pacingEnabled=qs(\"pacing\") !== \"off\"") >= 0 &&
  page.indexOf("var preDecodeEnabled=qs(\"predecode\") !== \"off\"") >= 0,
  "las dos piezas de W-20 deben poder apagarse desde el TV sin recompilar");
assert(/pacing:pacingEnabled,\s*predecode:preDecodeEnabled/.test(page),
  "y esos dos interruptores deben llegar al motor");
assert(page.indexOf("function preDecodeIdle(") >= 0 &&
  page.indexOf("engine.idle(reader,target)") >= 0,
  "el tiempo muerto entre cuadros se le ofrece al motor");
assert(page.indexOf("function adoptSpare(index)") >= 0 &&
  page.indexOf("engine.exchange(index,reader)") >= 0,
  "adoptar el keyframe adelantado es intercambiar readers, no copiar celdas");
assert(/adopted=engine\.exchange\(index,reader\);[\s\S]{0,120}renderer\.reader=reader;/.test(page),
  "tras el intercambio el renderer tiene que apuntar al reader adoptado");

assert(page.indexOf("mozfullscreenchange") >= 0);
assert(page.indexOf("MSFullscreenChange") >= 0);

/* W-14: robustez del player TV */
assert(page.indexOf("reader.header.version===1 && !reader.header.crc32") >= 0,
  "un ASCL v1 con CRC en cero debe rechazarse explicitamente");
assert(page.indexOf("ASCL v1 sin CRC32") >= 0);
assert(page.indexOf("webglcontextrestored") >= 0,
  "una perdida transitoria de contexto no debe degradar a Canvas para siempre");
assert(page.indexOf("watchContextRestore(watched)") >= 0,
  "el fallback debe dejar armada la vuelta a WebGL");
assert(page.indexOf("detachRestoreWatch();\n    disposeRenderer(true)") >= 0,
  "el refresco debe soltar tambien la escucha de restauracion");
assert(page.indexOf("nativeRequestFrame && nativeCancelFrame") >= 0,
  "requestFrame/cancelFrame deben elegirse como par");
assert(page.indexOf("nativeRequestFrame.call(window,fn)") >= 0 &&
  page.indexOf("nativeCancelFrame.call(window,id)") >= 0,
  "los nativos deben invocarse con window como receptor");
if (demo) {
  var magic = demo.slice(0, 8).toString("ascii");
  assert(magic === "ASCLVID1" || magic === "ASCLVID2" || magic === "ASCLVID3",
    "el archivo de la ruta TV debe ser ASCLVID1, ASCLVID2 o ASCLVID3");
  /* F6-3: ASCLVID3 lleva header de 20 bytes con meta_len. */
  var demoHeaderSize = magic === "ASCLVID3" ? 20 : 16;
  var demoMetaLength = magic === "ASCLVID3" ? demo.readUInt32LE(16) : 0;
  /* W-14: inventario — si el artefacto local es v1, debe llevar CRC real,
     porque la pagina TV ahora rechaza v1 con CRC en cero. */
  if (demo[demoHeaderSize + 4] === 1) {
    assert(demo.readUInt32LE(demoHeaderSize + 28) !== 0,
      "el artefacto v1 del inventario debe llevar CRC32 distinto de cero");
  }
  assert(demo.readUInt32LE(8) > 32, "el demo debe contener video");
  assert.strictEqual(
    demoHeaderSize + demo.readUInt32LE(8) + demo.readUInt32LE(12) + demoMetaLength,
    demo.length,
    "el demo local no debe estar truncado ni contener bytes posteriores");
  if (requireDemo) {
    assert.strictEqual(magic, "ASCLVID2",
      "el artefacto HQ del release debe conservar ASCLVID2");
    assert(demo.readUInt32LE(12) > 0,
      "el artefacto HQ del release debe conservar el audio incluido");
    assert.strictEqual(
      crypto.createHash("sha256").update(demo).digest("hex").toUpperCase(),
      "6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A",
      "el artefacto HQ no coincide con el binario aprobado");
  }
} else {
  assert.strictEqual(requireDemo, false,
    "falta outputs/clip.asclv; copie el artefacto de release o quite --require-release-artifact");
}
assert.strictEqual(/\b(?:let|const|class)\b/.test(inline[1]), false);
assert.strictEqual(/=>/.test(inline[1]), false);
assert.strictEqual(/\bfetch\b/.test(inline[1]), false);
assert.strictEqual(/\bPromise\b/.test(inline[1]), false);
assert.strictEqual(/serviceWorker/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("TV player page tests: OK");
