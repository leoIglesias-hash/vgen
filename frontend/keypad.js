"use strict";

/* keypad.js - mando numerico para las paginas de diagnostico del formato.
 *
 * Existe porque el destino real es un TV BOX con control remoto: ahi el click
 * es caro (puntero emulado) y las teclas numericas son gratis. Cada accion se
 * dispara con un numero.
 *
 * El retardo NO es global: solo se espera cuando el digito tecleado PUEDE ser
 * el comienzo de un codigo mas largo. Con codigos 0..9 y 10..13, el "5" dispara
 * al instante y el "1" espera, porque podria volverse 10, 11, 12 o 13. Ademas
 * OK/Enter dispara lo que haya en el buffer sin esperar, y Escape/Backspace lo
 * limpia: en un control remoto eso es la diferencia entre util e insufrible.
 *
 * ES5.1 estricto (gate tests/test_frontend_compatibility.js). Sin dependencias.
 */

var ASCLKeypad = (function () {

  /* Los controles remotos y los teclados mandan los digitos por keyCode; los
   * numericos del pad llegan en otro rango. Se aceptan los dos. */
  function digitOf(event) {
    var code = event.keyCode || event.which || 0;
    if (code >= 48 && code <= 57) { return String(code - 48); }
    if (code >= 96 && code <= 105) { return String(code - 96); }
    return "";
  }

  function isPrefix(codes, value) {
    var i;
    for (i = 0; i < codes.length; i++) {
      if (codes[i].length > value.length &&
          codes[i].substring(0, value.length) === value) { return true; }
    }
    return false;
  }

  function create(options) {
    var actions = options.actions || [];
    var delay = options.delay > 0 ? options.delay : 900;
    var onBuffer = options.onBuffer || function () {};
    var host = options.host ||
               (typeof window !== "undefined" ? window : null);
    var buffer = "";
    var timer = 0;
    var codes = [];
    var i;
    for (i = 0; i < actions.length; i++) { codes.push(actions[i].code); }

    function find(value) {
      var j;
      for (j = 0; j < actions.length; j++) {
        if (actions[j].code === value) { return actions[j]; }
      }
      return null;
    }

    function stopTimer() {
      if (timer && host && host.clearTimeout) { host.clearTimeout(timer); }
      timer = 0;
    }

    function clear() {
      buffer = "";
      stopTimer();
      onBuffer("", 0);
    }

    function fire(value) {
      var action = find(value);
      clear();
      if (action && action.run) { action.run(); }
      return action ? true : false;
    }

    function flush() {
      if (!buffer) { return "vacio"; }
      return fire(buffer) ? "ok" : "nada";
    }

    function push(digit) {
      var value = buffer + digit;
      stopTimer();
      if (isPrefix(codes, value)) {
        buffer = value;
        onBuffer(buffer, delay);
        if (host && host.setTimeout) {
          timer = host.setTimeout(function () { fire(buffer); }, delay);
        }
        return "espera";
      }
      return fire(value) ? "ok" : "nada";
    }

    function onKeyDown(event) {
      var code = event.keyCode || event.which || 0;
      var target = event.target || event.srcElement;
      var tag = target && target.nodeName ? target.nodeName.toUpperCase() : "";
      var digit;
      /* Si el foco esta en un campo de texto, los numeros son texto, no ordenes. */
      if (tag === "INPUT" || tag === "TEXTAREA") { return; }
      digit = digitOf(event);
      if (digit) {
        if (event.preventDefault) { event.preventDefault(); }
        push(digit);
        return;
      }
      if (code === 13) {            /* OK del control remoto */
        if (buffer) {
          if (event.preventDefault) { event.preventDefault(); }
          flush();
        }
        return;
      }
      if (code === 27 || code === 8) {   /* Escape / Volver */
        if (buffer) {
          if (event.preventDefault) { event.preventDefault(); }
          clear();
        }
      }
    }

    if (options.attach !== false && typeof document !== "undefined") {
      if (document.addEventListener) {
        document.addEventListener("keydown", onKeyDown, false);
      } else {
        document.onkeydown = onKeyDown;
      }
    }

    return { push: push, flush: flush, clear: clear, codes: codes,
             delay: delay, onKeyDown: onKeyDown };
  }

  return { create: create, digitOf: digitOf, isPrefix: isPrefix };
})();
