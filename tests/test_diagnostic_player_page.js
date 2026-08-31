"use strict";

/* W-16 (adelanta F8-1): contrato estatico del player de diagnostico.
 *
 * La regla del proyecto es que lo medido sea exactamente lo que corre en el TV:
 * por eso la instrumentacion vive dentro de esta pagina, envolviendo metodos de
 * la instancia, y ningun archivo de produccion se modifica para medir. Este test
 * fija esa propiedad y las etapas que la pagina tiene que publicar.
 */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var pagePath = path.join(__dirname, "..", "frontend", "diagnostic-player.html");
var page = fs.readFileSync(pagePath, "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "el diagnostic debe llevar su controlador inline");

/* Carga el mismo frontend de produccion, sin copias paralelas. */
assert(page.indexOf("<script src=\"inflate.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"reader.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"reader-v2.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"reader-factory.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"render-canvas2d.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"render-webgl.js\"></script>") >= 0);
assert(page.indexOf("<script src=\"cache-refresh.js\"></script>") >= 0,
  "el puntero CACHE-001 se lee con el parser canonico");
assert(page.indexOf("window.ASCILINEReader || window.ASCL") >= 0,
  "el despacho de version debe pasar por el factory con fallback v1");

/* Las cuatro etapas del frame + el resto del seek. */
assert(inline[1].indexOf("wrapTimed(instance, \"_inflate\", \"inflate\")") >= 0);
assert(inline[1].indexOf("wrapTimed(instance, \"_walkRegional\", \"walk\")") >= 0);
assert(inline[1].indexOf("wrapTimed(instance, \"fillRGBA\", \"rgba\")") >= 0);
assert(inline[1].indexOf("wrapTimed(instance, \"fillRGBARows\", \"rgba\")") >= 0);
assert(inline[1].indexOf("wrapTimed(instance, \"fillRGBAChanged\", \"rgba\")") >= 0);
assert(inline[1].indexOf("blitMs = drawMs - rgbaMs") >= 0,
  "el blit/upload se obtiene restando la conversion al draw completo");
assert(inline[1].indexOf("otherMs = decodeMs - acc.inflate - acc.walk") >= 0,
  "el resto del seek debe quedar visible, no repartido entre las otras etapas");

/* fillRGBA delega en fillRGBARows: sin guarda de reentrada la conversion se
   contaria dos veces y el blit quedaria en cero. */
assert(inline[1].indexOf("depth[key]++") >= 0 &&
  inline[1].indexOf("if(!depth[key]){ acc[key] += now() - t0; }") >= 0,
  "las etapas anidadas solo deben sumar en el nivel externo");

/* Estadistica publicada. */
assert(inline[1].indexOf("pct(0.5)") >= 0 && inline[1].indexOf("pct(0.95)") >= 0,
  "el diagnostic debe publicar p50 y p95");
assert(inline[1].indexOf("session.dropped += target - lastShown - 1") >= 0,
  "los frames salteados deben contarse como drops");
assert(inline[1].indexOf("totalMs > session.budget){ session.late++") >= 0,
  "un frame por encima del presupuesto debe contarse como tarde");
assert(inline[1].indexOf("1000 / header.fps") >= 0,
  "el presupuesto por frame sale de los fps del clip, no de una constante");
assert(inline[1].indexOf("SAMPLE_MAX") >= 0,
  "la ventana de muestras debe ser fija: nada crece por frame");

/* Tres grillas en la misma pantalla y fuente elegible. */
assert(/PRESETS\s*=\s*\[[\s\S]*?1280-12[\s\S]*?1920-10[\s\S]*?\]/.test(inline[1]),
  "debe ofrecer las variantes publicadas como fuentes conmutables");
assert(inline[1].indexOf("qs(\"src\")") >= 0 && inline[1].indexOf("qs(\"dir\")") >= 0,
  "la fuente debe poder indicarse por query string");
assert(inline[1].indexOf("function historyTable()") >= 0,
  "las grillas medidas deben acumularse en una tabla");
assert(inline[1].indexOf("qs(\"renderer\")") >= 0 && inline[1].indexOf("qs(\"rec\")") >= 0,
  "renderer y reconstruccion deben ser forzables para comparar caminos");

/* No mide audio a proposito (la cadencia es asunto de W-20). */
assert(page.indexOf("<audio") < 0,
  "el diagnostic no reproduce audio: mide costo por frame");

/* Piso legacy: el gate canonico es tests/test_frontend_compatibility.js, que
   blanquea strings y comentarios antes de analizar (esta pagina emite HTML con
   atributos class="..." dentro de strings). Aca solo quedan las trampas que no
   dependen de esa distincion. */
assert.strictEqual(/=>/.test(inline[1]), false);
assert.strictEqual(/\bfetch\b|\bPromise\b/.test(inline[1]), false);
assert.strictEqual(/\bJSON\s*\./.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("diagnostic player page tests: OK");
