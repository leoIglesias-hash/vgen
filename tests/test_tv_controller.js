"use strict";

var assert = require("assert");
var fs = require("fs");
var path = require("path");
var TV = require("../frontend/tv-controller.js");

function emitter() {
  var listeners = {};
  return {
    addEventListener: function (type, fn) {
      if (!listeners[type]) { listeners[type] = []; }
      listeners[type].push(fn);
    },
    removeEventListener: function (type, fn) {
      var list = listeners[type] || [];
      var i = list.indexOf(fn);
      if (i >= 0) { list.splice(i, 1); }
    },
    emit: function (type, event) {
      var list = (listeners[type] || []).slice();
      var i;
      event = event || {};
      event.type = type;
      for (i = 0; i < list.length; i++) { list[i](event); }
    },
    count: function (type) { return (listeners[type] || []).length; }
  };
}

(function testActivationKeys() {
  assert.strictEqual(TV.isActivationKey({ key: "1" }), true);
  assert.strictEqual(TV.isActivationKey({ key: "8" }), true);
  assert.strictEqual(TV.isActivationKey({ key: "0" }), false);
  assert.strictEqual(TV.isActivationKey({ key: "9" }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 49 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 56 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 1 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 8 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 0 }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 9 }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 97 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 104 }), true);
  assert.strictEqual(TV.isActivationKey({ keyCode: 48 }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 57 }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 96 }), false);
  assert.strictEqual(TV.isActivationKey({ keyCode: 105 }), false);
  assert.strictEqual(TV.isActivationKey({ which: 52 }), true);
  assert.strictEqual(TV.isActivationKey({ code: "Digit3" }), true);
  assert.strictEqual(TV.isActivationKey({ code: "Numpad7" }), true);
  assert.strictEqual(TV.isActivationKey({ code: "Digit9" }), false);
  assert.strictEqual(TV.isActivationKey({ keyIdentifier: "U+0031" }), true);
  assert.strictEqual(TV.isActivationKey({ keyIdentifier: "U+0038" }), true);
  assert.strictEqual(TV.isActivationKey({ keyIdentifier: "U+0039" }), false);
}());

(function testFullscreenPrefixes() {
  var requestNames = [
    "requestFullscreen", "webkitRequestFullscreen", "webkitRequestFullScreen",
    "mozRequestFullScreen", "msRequestFullscreen"
  ];
  var exitNames = [
    "exitFullscreen", "webkitExitFullscreen", "webkitCancelFullScreen",
    "mozCancelFullScreen", "msExitFullscreen"
  ];
  requestNames.forEach(function (name) {
    var element = {}, called = 0;
    element[name] = function () { called += 1; assert.strictEqual(this, element); };
    TV.requestFullscreen(element);
    assert.strictEqual(called, 1, name);
  });
  exitNames.forEach(function (name) {
    var doc = {}, called = 0;
    doc[name] = function () { called += 1; assert.strictEqual(this, doc); };
    TV.exitFullscreen(doc);
    assert.strictEqual(called, 1, name);
  });
}());

(function testSafePlayWithoutPromiseDependency() {
  var calls = 0, caught = 0, reported = 0;
  assert.strictEqual(TV.safePlay(function () { calls += 1; }), undefined);
  TV.safePlay(function () {
    calls += 1;
    return { "catch": function (fn) { caught += 1; fn(new Error("denegado")); } };
  }, null, function () { reported += 1; });
  TV.safePlay(function () { calls += 1; throw new Error("fallo sincrono"); }, null,
    function () { reported += 1; });
  assert.strictEqual(calls, 3);
  assert.strictEqual(caught, 1);
  assert.strictEqual(reported, 2);
}());

(function testInitInputAndTouchClickGuard() {
  var doc = emitter(), surface = emitter(), full = emitter();
  var fullscreenCalls = 0, playCalls = 0, prevented = 0, time = 1000;
  full.requestFullscreen = function () { fullscreenCalls += 1; };
  doc.documentElement = full;
  var controller = TV.init({
    document: doc,
    surface: surface,
    fullscreenElement: full,
    play: function () { playCalls += 1; },
    now: function () { return time; }
  });

  doc.emit("keydown", { keyCode: 50, preventDefault: function () { prevented += 1; } });
  assert.strictEqual(fullscreenCalls, 1);
  assert.strictEqual(playCalls, 1);
  assert.strictEqual(prevented, 1);
  doc.emit("keydown", { keyCode: 65 });
  assert.strictEqual(playCalls, 1);

  surface.emit("click");
  assert.strictEqual(playCalls, 2);
  time += 100;
  surface.emit("touchend");
  assert.strictEqual(playCalls, 3);
  time += 100;
  surface.emit("click");
  assert.strictEqual(playCalls, 3, "el click sintetico posterior al touch se ignora");
  time += 800;
  surface.emit("click");
  assert.strictEqual(playCalls, 4);
  assert.strictEqual(fullscreenCalls, 4);

  assert.strictEqual(doc.count("keydown"), 1);
  assert.strictEqual(surface.count("click"), 1);
  controller.destroy();
  assert.strictEqual(doc.count("keydown"), 0);
  assert.strictEqual(surface.count("click"), 0);
  surface.emit("click");
  assert.strictEqual(playCalls, 4);
}());

(function testLegacyAttachEventFallback() {
  var handlers = {}, plays = 0, fullscreenCalls = 0;
  var doc = {
    documentElement: { requestFullscreen: function () { fullscreenCalls += 1; } },
    attachEvent: function (name, fn) { handlers[name] = fn; },
    detachEvent: function (name) { delete handlers[name]; }
  };
  var controller = TV.init({ document: doc, surface: doc, play: function () { plays += 1; } });
  handlers.onkeydown({ keyCode: 100 });
  assert.strictEqual(plays, 1);
  assert.strictEqual(fullscreenCalls, 1);
  controller.destroy();
  assert.strictEqual(handlers.onkeydown, undefined);
}());

(function testDistributedSourceStaysES5() {
  var source = fs.readFileSync(path.join(__dirname, "..", "frontend", "tv-controller.js"), "utf8");
  assert.strictEqual(/\b(?:let|const|class)\b/.test(source), false);
  assert.strictEqual(/=>/.test(source), false);
  assert.strictEqual(/\bPromise\b/.test(source), false);
}());

console.log("TV controller tests: OK");
