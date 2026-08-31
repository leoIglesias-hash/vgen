/*
 * tv-controller.js - Activacion del reproductor para Smart TV y webviews viejos.
 *
 * ES5.1, sin exigir promesas. Una tecla numerica del 1 al 8, un click o
 * un toque solicitan fullscreen y arrancan la reproduccion en el mismo gesto.
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  root.ASCILINETV = api;
}(typeof window !== "undefined" ? window : this, function (root) {
  "use strict";

  function noop() {}

  function clockNow() {
    return Date.now ? Date.now() : new Date().getTime();
  }

  function reportError(onError, error) {
    if (typeof onError === "function") {
      try { onError(error); } catch (ignored) {}
    }
  }

  /* Observa rechazos solo cuando el objeto devuelto ofrece catch(). */
  function ignoreRejection(result, onError) {
    if (result && typeof result["catch"] === "function") {
      try {
        result["catch"](typeof onError === "function" ? onError : noop);
      } catch (error) {
        reportError(onError, error);
      }
    }
    return result;
  }

  function callSafely(fn, context, onError) {
    var result;
    if (typeof fn !== "function") { return null; }
    try {
      result = fn.call(context);
      return ignoreRejection(result, onError);
    } catch (error) {
      reportError(onError, error);
      return null;
    }
  }

  function isActivationKey(event) {
    var key, code, physical, identifier, digit;
    if (!event) { return false; }
    key = event.key;
    if (typeof key === "string" && key.length === 1 && key >= "1" && key <= "8") {
      return true;
    }
    physical = event.code;
    if (typeof physical === "string") {
      if (physical.indexOf("Digit") === 0) { digit = physical.substr(5); }
      else if (physical.indexOf("Numpad") === 0) { digit = physical.substr(6); }
      if (digit && digit.length === 1 && digit >= "1" && digit <= "8") { return true; }
    }
    /* WebKit antiguo (varios navegadores de TV): U+0031 .. U+0038. */
    identifier = event.keyIdentifier;
    if (typeof identifier === "string" && identifier.length === 6 &&
        identifier.substr(0, 5) === "U+003" &&
        identifier.charAt(5) >= "1" && identifier.charAt(5) <= "8") {
      return true;
    }
    code = event.keyCode;
    if (typeof code !== "number") { code = event.which; }
    /* 1..8: algunos controles entregan el digito crudo; 49..56: fila
       numerica; 97..104: teclado numerico. */
    return (code >= 1 && code <= 8) ||
      (code >= 49 && code <= 56) || (code >= 97 && code <= 104);
  }

  function requestFullscreen(element, onError) {
    var fn;
    if (!element) { return null; }
    fn = element.requestFullscreen ||
      element.webkitRequestFullscreen || element.webkitRequestFullScreen ||
      element.mozRequestFullScreen || element.msRequestFullscreen;
    return callSafely(fn, element, onError);
  }

  function exitFullscreen(doc, onError) {
    var fn;
    if (!doc) { return null; }
    fn = doc.exitFullscreen || doc.webkitExitFullscreen ||
      doc.webkitCancelFullScreen || doc.mozCancelFullScreen ||
      doc.msExitFullscreen;
    return callSafely(fn, doc, onError);
  }

  function fullscreenElement(doc) {
    if (!doc) { return null; }
    return doc.fullscreenElement || doc.webkitFullscreenElement ||
      doc.mozFullScreenElement || doc.msFullscreenElement || null;
  }

  function safePlay(playable, context, onError) {
    if (typeof playable === "function") {
      return callSafely(playable, context || null, onError);
    }
    if (playable && typeof playable.play === "function") {
      return callSafely(playable.play, playable, onError);
    }
    return null;
  }

  function addListener(target, type, handler) {
    if (!target) { return noop; }
    if (target.addEventListener) {
      target.addEventListener(type, handler, false);
      return function () { target.removeEventListener(type, handler, false); };
    }
    if (target.attachEvent) {
      target.attachEvent("on" + type, handler);
      return function () { target.detachEvent("on" + type, handler); };
    }
    return noop;
  }

  function init(options) {
    options = options || {};
    var doc = options.document || root.document;
    var surface = options.surface || doc;
    var keyTarget = options.keyTarget || doc;
    var target = options.fullscreenElement || (doc && doc.documentElement) || surface;
    var guardMs = typeof options.touchClickGuardMs === "number" ?
      options.touchClickGuardMs : 800;
    var now = typeof options.now === "function" ? options.now : clockNow;
    var lastTouch = -1;
    var removers = [];

    function activate(event) {
      var type = event && event.type;
      var time = now();
      if (type === "click" && lastTouch >= 0 && time >= lastTouch &&
          time - lastTouch < guardMs) {
        return false;
      }
      if (type === "touchend") { lastTouch = time; }
      requestFullscreen(target, options.onError);
      safePlay(options.play, options.playContext, options.onError);
      if (typeof options.onActivate === "function") {
        callSafely(options.onActivate, null, options.onError);
      }
      return true;
    }

    function onKeyDown(event) {
      event = event || root.event;
      if (!isActivationKey(event)) { return; }
      if (event.preventDefault) { event.preventDefault(); }
      else { event.returnValue = false; }
      activate(event);
    }

    removers.push(addListener(keyTarget, "keydown", onKeyDown));
    removers.push(addListener(surface, "click", activate));
    removers.push(addListener(surface, "touchend", activate));

    return {
      activate: activate,
      destroy: function () {
        var i;
        for (i = removers.length - 1; i >= 0; i--) { removers[i](); }
        removers.length = 0;
      }
    };
  }

  return {
    isActivationKey: isActivationKey,
    requestFullscreen: requestFullscreen,
    exitFullscreen: exitFullscreen,
    fullscreenElement: fullscreenElement,
    safePlay: safePlay,
    init: init
  };
}));
