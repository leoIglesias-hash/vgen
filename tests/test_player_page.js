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
assert.strictEqual(/\b(?:let|const|class)\b|=>|`/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("traditional player page tests: OK");
