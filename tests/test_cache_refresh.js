"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var Cache = require("../frontend/cache-refresh.js");

(function testMenuKeyAcrossTVEventVariants() {
  assert.strictEqual(Cache.isMenuKey({ key: "9", keyCode: 57 }), true);
  assert.strictEqual(Cache.isMenuKey({ key: "Tab", keyCode: 9 }), false,
    "Tab moderno no debe abrir el menu tecnico");
  assert.strictEqual(Cache.isMenuKey({ code: "Digit9" }), true);
  assert.strictEqual(Cache.isMenuKey({ code: "Numpad9" }), true);
  assert.strictEqual(Cache.isMenuKey({ keyIdentifier: "U+0039" }), true);
  assert.strictEqual(Cache.isMenuKey({ keyCode: 57 }), true);
  assert.strictEqual(Cache.isMenuKey({ keyCode: 105 }), true);
  assert.strictEqual(Cache.isMenuKey({ key: "Unidentified", keyCode: 57 }), true,
    "un control TV puede exponer key inutil y keyCode correcto");
  assert.strictEqual(Cache.isMenuKey({ code: "Unidentified", keyCode: 105 }), true);
  assert.strictEqual(Cache.isMenuKey({ key: "8", keyCode: 57 }), false,
    "un digito moderno explicito debe prevalecer sobre metadata contradictoria");
  assert.strictEqual(Cache.isMenuKey({ keyCode: 9 }), false,
    "Tab legacy no debe quedar secuestrado por un codigo numerico ambiguo");
  assert.strictEqual(Cache.isMenuKey({ key: "8", keyCode: 56 }), false);
}());

(function testPersistentSafeTokenAndStableBasePath() {
  var values = {};
  var storage = {
    getItem: function (key) { return values[key] || null; },
    setItem: function (key, value) { values[key] = value; }
  };
  var options = {
    source: "./outputs/clip.asclv",
    storage: storage,
    storageKey: "test-token",
    now: function () { return 1700000000000; },
    random: function () { return 0.5; }
  };
  var first = Cache.createTokenStore(options);
  var refreshed;

  assert.strictEqual(first.url(false), "./outputs/clip.asclv");
  refreshed = first.url(true);
  assert(/^\.\/outputs\/clip\.asclv\?asclv_refresh=[A-Za-z0-9_-]+$/.test(refreshed));
  assert(Cache.validToken(values["test-token"]));
  assert.strictEqual(first.url(false), refreshed,
    "los reintentos deben usar la misma version cacheable");
  assert.strictEqual(Cache.createTokenStore(options).url(false), refreshed,
    "una recarga de pagina debe recuperar el token persistido");
}());

(function testBlockedStorageFallsBackWithoutBreakingRefresh() {
  var blocked = {
    getItem: function () { throw new Error("bloqueado"); },
    setItem: function () { throw new Error("bloqueado"); }
  };
  var state = Cache.createTokenStore({
    source: "./outputs/clip.asclv",
    storage: blocked,
    now: function () { return 10; },
    random: function () { return 0; }
  });
  assert.strictEqual(state.url(false), "./outputs/clip.asclv");
  assert.strictEqual(state.url(true), "./outputs/clip.asclv?asclv_refresh=va-0");
  assert.strictEqual(state.url(false), "./outputs/clip.asclv?asclv_refresh=va-0");
}());

(function testExistingQueryAndFragmentArePreserved() {
  assert.strictEqual(
    Cache.appendToken("clip.asclv?lang=es#video", "refresh", "v1-safe"),
    "clip.asclv?lang=es&refresh=v1-safe#video"
  );
  assert.strictEqual(Cache.appendToken("clip.asclv", "refresh", "valor inseguro"),
    "clip.asclv");
}());

(function testSyntheticClickGuard() {
  var guard = new Cache.GestureGuard(800);
  assert.strictEqual(guard.accept("touchend", 1000), true);
  assert.strictEqual(guard.accept("click", 1100), false);
  assert.strictEqual(guard.accept("click", 1800), true);
  assert.strictEqual(guard.accept("touchend", 2000), true);
  assert.strictEqual(guard.accept("click", 1900), true,
    "un reloj que retrocede no debe bloquear el control");
}());

/* CACHE-001 (F6-4): puntero de texto plano hacia el clip versionado. */
(function testClipPointerParsing() {
  var parse = Cache.parseClipPointer;
  assert.strictEqual(parse("clip.b081f4ba1d2e.asclv\n"), "clip.b081f4ba1d2e.asclv");
  assert.strictEqual(
    parse("# ASCILINE CACHE-001; sha256=abc\nclip.0123456789ab.asclv\n"),
    "clip.0123456789ab.asclv",
    "los comentarios # se saltean; la primera linea util manda");
  assert.strictEqual(parse("\r\n  clip.deadbeef00aa.asclv \r\n"),
    "clip.deadbeef00aa.asclv", "CRLF y espacios se recortan");
  assert.strictEqual(parse("clip.DEADBEEF00AA.asclv"), "",
    "solo hex minusculas: el puntero es canonico, no permisivo");
  assert.strictEqual(parse("../secreto/clip.aabbccddeeff.asclv"), "",
    "sin rutas: el nombre es exacto o no es");
  assert.strictEqual(parse("clip.abc.asclv"), "", "menos de 8 hex es invalido");
  assert.strictEqual(parse("clip.asclv"), "", "el nombre historico no es puntero");
  assert.strictEqual(parse(""), "");
  assert.strictEqual(parse(null), "");
  assert.strictEqual(parse(new Array(5000).join("a")), "",
    "un puntero gigante se descarta sin parsear");
  assert.strictEqual(parse("# solo comentarios\n#\n"), "");
}());

(function testDistributedSourceStaysES5() {
  var source = fs.readFileSync(
    path.join(__dirname, "..", "frontend", "cache-refresh.js"), "utf8");
  assert.strictEqual(/\b(?:let|const|class)\b/.test(source), false);
  assert.strictEqual(/=>/.test(source), false);
  assert.strictEqual(/\bfetch\b/.test(source), false);
  assert.strictEqual(/\bPromise\b/.test(source), false);
  assert.strictEqual(/serviceWorker/.test(source), false);
  assert.doesNotThrow(function () { new Function(source); });
}());

console.log("Cache refresh tests: OK");
