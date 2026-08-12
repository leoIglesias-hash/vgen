"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "tv-player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);
var demoPath = path.join(__dirname, "..", "outputs",
  "TKN-2441-GANADOR-graphic-kmeans.asclv");
var demo = fs.readFileSync(demoPath);

assert(inline, "la pagina TV debe contener su controlador inline");
assert(page.indexOf("./output/clip.asclv") >= 0);
assert(page.indexOf("../outputs/TKN-2441-GANADOR-graphic-kmeans.asclv") < 0);
assert(page.indexOf("Iniciar descarga") >= 0);
assert(page.indexOf("tv-controller.js") >= 0);
assert(page.indexOf("render-canvas2d.js") >= 0);
assert(page.indexOf("render-webgl.js") >= 0);
assert(page.indexOf("beginDownload(false)") >= 0, "debe intentar precarga automatica");
assert(page.indexOf("beginDownload(true)") >= 0, "debe permitir descarga manual");
assert(page.indexOf("activeXHR!==xhr") >= 0,
  "una respuesta XHR vieja no debe pisar un reintento nuevo");
assert(page.indexOf("lastDownloadTouch") >= 0,
  "touch + click sintetico no deben iniciar dos descargas");
assert(page.indexOf("mozfullscreenchange") >= 0);
assert(page.indexOf("MSFullscreenChange") >= 0);
assert.strictEqual(demo.slice(0, 8).toString("ascii"), "ASCLVID1");
assert(demo.readUInt32LE(8) > 32, "el demo debe contener video");
assert(demo.readUInt32LE(12) > 0, "el demo debe conservar el audio incluido");
assert.strictEqual(/\b(?:let|const|class)\b/.test(inline[1]), false);
assert.strictEqual(/=>/.test(inline[1]), false);
assert.strictEqual(/\bfetch\b/.test(inline[1]), false);
assert.strictEqual(/\bPromise\b/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("TV player page tests: OK");
