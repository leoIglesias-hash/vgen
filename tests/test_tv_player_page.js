"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "tv-player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);
var refreshFunction = page.match(/function refreshCurrentVideo\(\)\{([\s\S]*?)\n  \}\n\n  downloadButton\.onclick/);
var demoPath = path.join(__dirname, "..", "outputs", "clip.asclv");
var demo = fs.readFileSync(demoPath);

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
assert(page.indexOf("disposeRenderer(true);\n    reader=null;\n    lastShown=-1") >= 0,
  "reader, renderer y canvas anteriores deben quedar descartados");
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
assert(page.indexOf("bytes[7]===49 || bytes[7]===50") >= 0,
  "la descarga debe reconocer ASCLVID1 y ASCLVID2");
assert(page.indexOf("16+videoLength+audioLength!==buffer.byteLength") >= 0,
  "el bundle no debe aceptar truncado ni bytes anexados");
assert(page.indexOf("mozfullscreenchange") >= 0);
assert(page.indexOf("MSFullscreenChange") >= 0);
assert.strictEqual(demo.slice(0, 8).toString("ascii"), "ASCLVID2");
assert(demo.readUInt32LE(8) > 32, "el demo debe contener video");
assert(demo.readUInt32LE(12) > 0, "el demo debe conservar el audio incluido");
assert.strictEqual(/\b(?:let|const|class)\b/.test(inline[1]), false);
assert.strictEqual(/=>/.test(inline[1]), false);
assert.strictEqual(/\bfetch\b/.test(inline[1]), false);
assert.strictEqual(/\bPromise\b/.test(inline[1]), false);
assert.strictEqual(/serviceWorker/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("TV player page tests: OK");
