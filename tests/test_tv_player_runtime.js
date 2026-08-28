"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var vm = require("vm");
var Cache = require("../frontend/cache-refresh.js");

var page = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "tv-player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);
assert(inline, "no se encontro el controlador inline del TV player");

function emitter(base) {
  var listeners = {};
  var target = base || {};
  target.addEventListener = function (type, handler) {
    if (!listeners[type]) listeners[type] = [];
    listeners[type].push(handler);
  };
  target.removeEventListener = function (type, handler) {
    var list = listeners[type] || [], i = list.indexOf(handler);
    if (i >= 0) list.splice(i, 1);
  };
  target.emit = function (type, event) {
    var list = (listeners[type] || []).slice(), i;
    event = event || {};
    event.type = type;
    for (i = 0; i < list.length; i++) list[i](event);
  };
  target.listenerCount = function (type) { return (listeners[type] || []).length; };
  return target;
}

function bundle(audioLength, version) {
  version = version || 1;
  var videoLength = 32;
  var buffer = new ArrayBuffer(16 + videoLength + audioLength);
  var bytes = new Uint8Array(buffer), view = new DataView(buffer), magic = "ASCLVID"+version, i;
  for (i = 0; i < magic.length; i++) bytes[i] = magic.charCodeAt(i);
  view.setUint32(8, videoLength, true);
  view.setUint32(12, audioLength, true);
  bytes[16] = 65; bytes[17] = 83; bytes[18] = 67; bytes[19] = 76; /* ASCL */
  bytes[20] = version;
  return buffer;
}

function createRuntime(options) {
  options = options || {};
  var elements = {}, xhrs = [], rafCallbacks = {}, rafId = 0, clock = 0;
  var stats = {
    webglDraws: 0, canvasDraws: 0, webglDispose: [], canvasDispose: 0,
    revoked: [], audioLoads: 0, audioPauses: 0
  };

  function canvasElement() {
    return emitter({ id: "cv", width: 640, height: 360, style: {}, parentNode: null });
  }

  var stage = emitter({
    id: "stage", style: {}, className: "", clientWidth: 640, clientHeight: 360,
    focus: function () {}
  });
  stage.replaceChild = function (replacement, old) {
    assert.strictEqual(old.parentNode, stage);
    replacement.parentNode = stage;
    old.parentNode = null;
    elements.cv = replacement;
  };
  var initialCanvas = canvasElement();
  initialCanvas.parentNode = stage;
  elements.stage = stage; elements.cv = initialCanvas;
  elements.audio = {
    style: {}, currentTime: 0, ended: false, loop: false, src: "",
    pause: function () { stats.audioPauses += 1; },
    play: function () {},
    load: function () { stats.audioLoads += 1; },
    removeAttribute: function (name) { if (name === "src") this.src = ""; }
  };
  ["download", "techHotspot", "techMenu", "refreshVideo", "closeTechMenu",
    "headline", "detail"].forEach(function (id) {
    elements[id] = emitter({
      id: id, style: {}, className: "", innerHTML: "", textContent: "", innerText: "",
      focus: function () {},
      setAttribute: function () {}
    });
  });

  var document = emitter({
    documentElement: { clientWidth: 640, clientHeight: 360 },
    getElementById: function (id) { return elements[id]; },
    createElement: function (name) {
      assert.strictEqual(name, "canvas");
      return canvasElement();
    }
  });

  function MockXHR() {
    this.status = 200;
    this.response = null;
    this.headers = {};
    xhrs.push(this);
  }
  MockXHR.prototype.open = function (method, url) { this.method = method; this.url = url; };
  MockXHR.prototype.setRequestHeader = function (name, value) { this.headers[name] = value; };
  MockXHR.prototype.getResponseHeader = function () { return "application/octet-stream"; };
  MockXHR.prototype.send = function () { this.sent = true; };
  MockXHR.prototype.abort = function () { if (this.onabort) this.onabort(); };

  function reader() {
    var header = { flags: 0, cols: 8, rows: 5, fps: 1, nFrames: 3 }, key;
    if (options.readerHeader) {
      for (key in options.readerHeader) header[key] = options.readerHeader[key];
    }
    return {
      header: header,
      decodedIndex: -1,
      seek: function (index) { this.decodedIndex = index; },
      fillRGBA: function () {}, fillRGBARows: function () {}
    };
  }

  function MockWebGLRenderer(canvas) { this.canvas = canvas; }
  MockWebGLRenderer.prototype.init = function () { return true; };
  MockWebGLRenderer.prototype.draw = function (activeReader) {
    stats.webglDraws += 1;
    stats.lastWebGLReader = activeReader;
    if (options.contextLossDuringDraw) {
      this.canvas.emit("webglcontextlost", { preventDefault: function () {} });
      throw new Error("contexto GPU perdido durante draw");
    }
    if (options.throwWebGLDraw) throw new Error("GPU draw fallo");
  };
  MockWebGLRenderer.prototype.dispose = function (releaseContext) {
    stats.webglDispose.push(releaseContext);
  };

  function MockCanvas2DRenderer(canvas) { this.canvas = canvas; }
  MockCanvas2DRenderer.prototype.init = function (activeReader) {
    stats.lastCanvasInitReader = activeReader;
    return true;
  };
  MockCanvas2DRenderer.prototype.draw = function (activeReader) {
    stats.canvasDraws += 1;
    stats.lastCanvasReader = activeReader;
    stats.lastCanvasFrame = activeReader.decodedIndex;
  };
  MockCanvas2DRenderer.prototype.dispose = function () { stats.canvasDispose += 1; };

  var controllerOptions = null;
  var urlAPI = {
    createObjectURL: function () { return "blob:test-video"; },
    revokeObjectURL: function (url) { stats.revoked.push(url); }
  };
  var readerAPI = {
    parse: function () {
      if (options.parseError) throw new Error("video corrupto");
      stats.reader = reader();
      return stats.reader;
    }
  };
  var window = {
    document: document,
    location: { search: "" },
    innerWidth: 640, innerHeight: 360,
    localStorage: { getItem: function () { return null; }, setItem: function () {} },
    performance: { now: function () { return clock; } },
    requestAnimationFrame: function (callback) {
      rafId += 1; rafCallbacks[rafId] = callback; return rafId;
    },
    cancelAnimationFrame: function (id) { delete rafCallbacks[id]; },
    setTimeout: setTimeout, clearTimeout: clearTimeout,
    URL: urlAPI,
    XMLHttpRequest: MockXHR,
    ASCILINECacheRefresh: Cache,
    WebGLRenderer: MockWebGLRenderer,
    Canvas2DRenderer: MockCanvas2DRenderer,
    ASCL: readerAPI,
    ASCILINEReader: readerAPI,
    ASCILINETV: {
      init: function (received) { controllerOptions = received; return {}; }
    }
  };
  window.window = window;

  function FakeBlob(parts, blobOptions) {
    this.parts = parts; this.type = blobOptions && blobOptions.type;
  }

  vm.runInNewContext(inline[1], {
    window: window, document: document, XMLHttpRequest: MockXHR,
    Blob: FakeBlob, DataView: DataView, Uint8Array: Uint8Array,
    ArrayBuffer: ArrayBuffer, Date: Date, Math: Math, isFinite: isFinite,
    decodeURIComponent: decodeURIComponent, setTimeout: setTimeout, clearTimeout: clearTimeout
  }, { filename: "tv-player-inline.js" });

  return {
    elements: elements, xhrs: xhrs, stats: stats,
    controller: function () { return controllerOptions; },
    setClock: function (value) { clock = value; },
    runRAF: function () {
      var ids = Object.keys(rafCallbacks), id, callback;
      assert(ids.length > 0, "se esperaba un frame pendiente");
      id = Number(ids[0]); callback = rafCallbacks[id]; delete rafCallbacks[id];
      callback(clock);
    },
    pendingRAF: function () { return Object.keys(rafCallbacks).length; }
  };
}

function completeInitialDownload(runtime, buffer) {
  var xhr;
  assert.strictEqual(runtime.xhrs.length, 1);
  xhr = runtime.xhrs[0];
  xhr.response = buffer;
  xhr.onload();
  assert.strictEqual(xhr.onload, null);
  assert.strictEqual(xhr.onprogress, null);
  assert.strictEqual(xhr.onerror, null);
  assert.strictEqual(xhr.onabort, null,
    "la XHR terminada no debe retener closures ni el buffer viejo por handlers");
}

(function testSynchronousWebGLDrawFailureFallsBackToCanvas() {
  var runtime = createRuntime({ throwWebGLDraw: true });
  completeInitialDownload(runtime, bundle(0));
  assert.strictEqual(runtime.stats.webglDraws, 1);
  assert.deepStrictEqual(runtime.stats.webglDispose, [true]);
  assert.strictEqual(runtime.stats.canvasDraws, 1);
  assert.strictEqual(runtime.stats.lastCanvasReader, runtime.stats.reader,
    "Canvas debe reutilizar exactamente el reader ya decodificado");
  assert.strictEqual(runtime.stats.lastCanvasFrame, 0);
  assert(runtime.elements.detail.textContent.indexOf("canvas2d") >= 0);
}());

(function testAsclvid2UsesTheSameSingleRendererPath() {
  var runtime = createRuntime();
  completeInitialDownload(runtime, bundle(0, 2));
  assert.strictEqual(runtime.stats.webglDraws, 1);
  assert.strictEqual(runtime.stats.canvasDraws, 0);
  assert.strictEqual(runtime.stats.reader.decodedIndex, 0);
}());

(function testReentrantContextLossDoesNotStopTheNewCanvas() {
  var runtime = createRuntime({ contextLossDuringDraw: true });
  completeInitialDownload(runtime, bundle(0));
  assert.deepStrictEqual(runtime.stats.webglDispose, [false]);
  assert.strictEqual(runtime.stats.canvasDraws, 1);
  assert.strictEqual(runtime.stats.lastCanvasFrame, 0);
  assert(runtime.elements.detail.textContent.indexOf("canvas2d") >= 0,
    "la excepcion del contexto viejo no debe invalidar el fallback ya instalado");
}());

(function testContextLossKeepsFrameAndPlaybackClockOnCanvas() {
  var runtime = createRuntime();
  completeInitialDownload(runtime, bundle(0));
  var webglCanvas = runtime.elements.cv;
  assert.strictEqual(webglCanvas.listenerCount("webglcontextlost"), 1);
  runtime.controller().play();
  assert.strictEqual(runtime.pendingRAF(), 1);

  var prevented = 0;
  webglCanvas.emit("webglcontextlost", {
    preventDefault: function () { prevented += 1; }
  });
  assert.strictEqual(prevented, 1);
  assert.deepStrictEqual(runtime.stats.webglDispose, [false],
    "un contexto ya perdido no debe recibir loseContext otra vez");
  assert.strictEqual(runtime.stats.canvasDraws, 1);
  assert.strictEqual(runtime.stats.lastCanvasFrame, 0);
  assert.strictEqual(runtime.pendingRAF(), 1,
    "el fallback no debe cancelar el reloj de reproduccion");

  runtime.setClock(1200);
  runtime.runRAF();
  assert.strictEqual(runtime.stats.canvasDraws, 2);
  assert.strictEqual(runtime.stats.lastCanvasFrame, 1,
    "el RAF existente debe seguir avanzando sobre Canvas");
}());

(function testRefreshDisposesGPUBeforeStartingTheReplacementXHR() {
  var runtime = createRuntime();
  completeInitialDownload(runtime, bundle(0));
  var oldCanvas = runtime.elements.cv;
  runtime.elements.refreshVideo.onclick({
    type: "click", stopPropagation: function () {}, preventDefault: function () {}
  });
  assert.deepStrictEqual(runtime.stats.webglDispose, [true]);
  assert.strictEqual(oldCanvas.width, 1);
  assert.strictEqual(oldCanvas.height, 1);
  assert.strictEqual(oldCanvas.listenerCount("webglcontextlost"), 0);
  assert.strictEqual(runtime.xhrs.length, 2);
  assert(runtime.xhrs[1].url.indexOf("./outputs/clip.asclv?asclv_refresh=") === 0);
  assert.strictEqual(runtime.xhrs[1].headers["Cache-Control"], "no-cache");
}());

(function testInvalidBundleReleasesAudioAndPartialState() {
  var runtime = createRuntime({ parseError: true });
  completeInitialDownload(runtime, bundle(4));
  assert.deepStrictEqual(runtime.stats.revoked, ["blob:test-video"]);
  assert.strictEqual(runtime.stats.audioLoads, 1);
  assert(runtime.stats.audioPauses >= 1);
  assert.strictEqual(runtime.elements.download.style.display, "block");
  assert.strictEqual(runtime.elements.stage.className, "error");
  assert.strictEqual(runtime.elements.headline.textContent, "No se pudo abrir el ASCLV");
}());

/* W-14: un ASCL v1 con CRC en cero (verificacion salteada por el reader) se
 * rechaza explicito en el TV. */
(function testV1WithoutCrcIsRejected() {
  var runtime = createRuntime({ readerHeader: { version: 1, crc32: 0 } });
  completeInitialDownload(runtime, bundle(0));
  assert.strictEqual(runtime.elements.stage.className, "error");
  assert.strictEqual(runtime.elements.headline.textContent, "No se pudo abrir el ASCLV");
  assert(runtime.elements.detail.textContent.indexOf("sin CRC32") >= 0);
  assert.strictEqual(runtime.elements.download.style.display, "block");
}());

(function testV1WithCrcStillPlays() {
  var runtime = createRuntime({ readerHeader: { version: 1, crc32: 0x1234 } });
  completeInitialDownload(runtime, bundle(0));
  assert.strictEqual(runtime.stats.webglDraws, 1);
  assert.notStrictEqual(runtime.elements.stage.className, "error");
}());

/* W-14: una perdida de contexto transitoria vuelve a WebGL cuando el contexto
 * se restaura, en lugar de quedar en Canvas2D para siempre. */
(function testContextRestoreReturnsToWebGL() {
  var runtime = createRuntime();
  completeInitialDownload(runtime, bundle(0));
  var webglCanvas = runtime.elements.cv;
  webglCanvas.emit("webglcontextlost", { preventDefault: function () {} });
  assert.strictEqual(runtime.stats.canvasDraws, 1, "fallback a Canvas tras la perdida");
  assert.strictEqual(webglCanvas.listenerCount("webglcontextrestored"), 1,
    "el canvas perdido debe quedar escuchando la restauracion");

  webglCanvas.emit("webglcontextrestored", {});
  assert.strictEqual(runtime.stats.webglDraws, 2,
    "el contexto restaurado debe reinstalar WebGL");
  assert.strictEqual(webglCanvas.listenerCount("webglcontextrestored"), 0,
    "la escucha de restauracion se consume una sola vez");
  assert.strictEqual(runtime.elements.cv.listenerCount("webglcontextlost"), 1,
    "el WebGL nuevo vuelve a vigilar la perdida de contexto");
  assert(runtime.elements.cv !== webglCanvas, "WebGL se reinstala sobre un canvas nuevo");
}());

console.log("TV player runtime tests: OK");
