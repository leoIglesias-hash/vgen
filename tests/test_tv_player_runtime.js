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
    revoked: [], audioLoads: 0, audioPauses: 0, parseSlot: 0
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
      seeks: [],
      seek: function (index) { this.seeks.push(index); this.decodedIndex = index; },
      /* W-20: sin keyframes declarados solo el 0 lo es, que es el caso en que
         no hay nada que adelantar. */
      _isKey: function (index) {
        return options.keyframes ? options.keyframes.indexOf(index) >= 0 : index === 0;
      },
      fillRGBA: function () {}, fillRGBARows: function () {}
    };
  }

  function MockWebGLRenderer(canvas) { this.canvas = canvas; }
  MockWebGLRenderer.prototype.init = function () { return true; };
  MockWebGLRenderer.prototype.draw = function (activeReader) {
    stats.webglDraws += 1;
    stats.lastWebGLReader = activeReader;
    stats.lastWebGLFrame = activeReader.decodedIndex;
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
  /* W-20: cada apertura crea DOS readers sobre los mismos bytes — el que
     reproduce y el que adelanta keyframes. El primero de cada par es el que el
     player usa para presentar. */
  var readerAPI = {
    parse: function () {
      var instance;
      if (options.parseError) throw new Error("video corrupto");
      instance = reader();
      if (stats.parseSlot) { stats.spare = instance; stats.parseSlot = 0; }
      else { stats.reader = instance; stats.parseSlot = 1; }
      return instance;
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
  var pointer, xhr;
  /* CACHE-001 (F6-4): la primera XHR es el puntero clip.current.txt; sin
     responseText valido la descarga cae al clip.asclv historico. */
  assert.strictEqual(runtime.xhrs.length, 1);
  pointer = runtime.xhrs[0];
  assert.strictEqual(pointer.url, "./outputs/clip.current.txt");
  pointer.onload();
  assert.strictEqual(pointer.onload, null);
  assert.strictEqual(runtime.xhrs.length, 2,
    "sin puntero valido la descarga debe caer al clip historico");
  xhr = runtime.xhrs[1];
  assert(xhr.url.indexOf("./outputs/clip.asclv") === 0);
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
  /* CACHE-001: el refresco vuelve a pasar por el puntero, con no-cache. */
  assert.strictEqual(runtime.xhrs.length, 3);
  var refreshPointer = runtime.xhrs[2];
  assert.strictEqual(refreshPointer.url, "./outputs/clip.current.txt");
  assert.strictEqual(refreshPointer.headers["Cache-Control"], "no-cache",
    "el no-cache del refresco aplica al recurso MUTABLE (el puntero)");
  refreshPointer.onload();
  assert.strictEqual(runtime.xhrs.length, 4);
  assert(runtime.xhrs[3].url.indexOf("./outputs/clip.asclv?asclv_refresh=") === 0);
  assert.strictEqual(runtime.xhrs[3].headers["Cache-Control"], "no-cache");
}());

/* CACHE-001 (F6-4): un puntero valido descarga el clip versionado inmutable. */
(function testValidPointerDownloadsImmutableVersionedClip() {
  var runtime = createRuntime();
  assert.strictEqual(runtime.xhrs.length, 1);
  var pointer = runtime.xhrs[0];
  pointer.responseText = "# ASCILINE CACHE-001; sha256=x\nclip.0123456789ab.asclv\n";
  pointer.onload();
  assert.strictEqual(runtime.xhrs.length, 2);
  var video = runtime.xhrs[1];
  assert.strictEqual(video.url, "./outputs/clip.0123456789ab.asclv",
    "el clip versionado se pide por su nombre exacto, sin token");
  video.response = bundle(0);
  video.onload();
  assert.strictEqual(runtime.stats.webglDraws, 1);

  runtime.elements.refreshVideo.onclick({
    type: "click", stopPropagation: function () {}, preventDefault: function () {}
  });
  assert.strictEqual(runtime.xhrs.length, 3);
  var refreshPointer = runtime.xhrs[2];
  assert.strictEqual(refreshPointer.headers["Cache-Control"], "no-cache");
  refreshPointer.responseText = "clip.aabbccddeeff.asclv";
  refreshPointer.onload();
  assert.strictEqual(runtime.xhrs.length, 4);
  var versioned = runtime.xhrs[3];
  assert.strictEqual(versioned.url, "./outputs/clip.aabbccddeeff.asclv");
  assert.strictEqual(versioned.headers["Cache-Control"], undefined,
    "un recurso versionado por contenido nunca se fuerza a no-cache");
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

/* W-20 (a): con un reloj maestro que avanza a saltos gruesos -lo que hace
   audio.currentTime en TVs viejos- la presentacion no debe saltar dos cuadros y
   despues quedarse quieta. Esa irregularidad se percibe peor que un fps bajo
   constante, y es por lo que se descarto el 1920@10. */
(function testPacingSmoothsACoarseMasterClock() {
  var runtime = createRuntime({ readerHeader: { fps: 10, nFrames: 60 } });
  var audio = runtime.elements.audio, shown = [], i, step, previous;
  completeInitialDownload(runtime, bundle(4));
  runtime.controller().play();
  /* El display avanza parejo (50 ms) y el audio en escalones de 200 ms. */
  for (i = 0; i < 12; i++) {
    step = i * 50;
    runtime.setClock(step);
    audio.currentTime = Math.floor(step / 200) * 0.2;
    runtime.runRAF();
    shown.push(runtime.stats.lastWebGLFrame);
  }
  for (i = 1; i < shown.length; i++) {
    assert(shown[i] - shown[i - 1] <= 1,
      "la presentacion nunca debe saltar dos cuadros de una: " + shown.join(","));
    assert(shown[i] >= shown[i - 1], "y nunca debe retroceder: " + shown.join(","));
  }
  assert(shown[shown.length - 1] >= 4,
    "y tiene que seguir avanzando con el audio: " + shown.join(","));
  previous = shown[0];
  assert.strictEqual(previous, 0, "el primer cuadro se engancha al reloj maestro");
}());

/* W-20 (b): el keyframe siguiente se decodifica en el tiempo muerto y se
   ADOPTA intercambiando readers, no re-decodificando. */
(function testKeyframePreDecodeAndAdoption() {
  var runtime = createRuntime({
    readerHeader: { fps: 10, nFrames: 40 }, keyframes: [0, 2]
  });
  completeInitialDownload(runtime, bundle(0));
  var main = runtime.stats.reader, spare = runtime.stats.spare;
  assert(spare && spare !== main, "el player abre un segundo reader para adelantar");
  runtime.controller().play();

  runtime.setClock(0);
  runtime.runRAF();
  assert.deepStrictEqual(spare.seeks, [2],
    "en el callback ocioso se adelanta el proximo keyframe, no el proximo cuadro");

  runtime.setClock(200);
  runtime.runRAF();
  assert.strictEqual(runtime.stats.lastWebGLReader, spare,
    "el cuadro presentado sale del reader adelantado");
  assert.deepStrictEqual(spare.seeks, [2],
    "el keyframe adoptado no se vuelve a decodificar");
  assert.strictEqual(main.seeks.indexOf(2), -1,
    "y el reader que reproducia no lo decodifico nunca");
}());

/* El pre-decode es una optimizacion: si no hay proximo keyframe a la vista, el
   tiempo muerto no se usa para nada y la reproduccion sigue igual. */
(function testNoPreDecodeWithoutUpcomingKeyframe() {
  var runtime = createRuntime({ readerHeader: { fps: 10, nFrames: 40 } });
  completeInitialDownload(runtime, bundle(0));
  var spare = runtime.stats.spare;
  runtime.controller().play();
  runtime.setClock(0);
  runtime.runRAF();
  assert.deepStrictEqual(spare.seeks, [],
    "sin keyframe proximo no se decodifica nada por las dudas");
}());

console.log("TV player runtime tests: OK");
