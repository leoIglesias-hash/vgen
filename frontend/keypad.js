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

  /* CUATRO caminos para leer un digito, y se prueban todos.
   *
   * H-22 (2026-09-04): en el WebView de un Smart TV con Android, ni el control
   * remoto ni un pad numerico USB movian la pagina. Preguntar de una sola forma
   * es suponer, y aca no se supone:
   *
   *   1. `keyCode`/`which` 48..57 - teclado y la mayoria de los controles.
   *   2. `keyCode` 96..105 - el bloque numerico con Bloq Num.
   *   3. `key` - la propiedad moderna. Hay WebViews que mandan keyCode 0 y
   *      solo pueblan esta, sobre todo cuando el digito pasa por un IME, que
   *      es como varios controles de TV escriben numeros.
   *   4. `code` ("Digit3" / "Numpad3") y `charCode` - por si `key` tampoco
   *      esta y lo unico que llega es el `keypress`.
   *
   * Cuesta cuatro comparaciones por tecla. La alternativa costaba una visita. */
  function digitOf(event) {
    var code = event.keyCode || event.which || 0;
    var key, name, letra;
    if (code >= 48 && code <= 57) { return String(code - 48); }
    if (code >= 96 && code <= 105) { return String(code - 96); }
    key = event.key;
    if (typeof key === "string" && key.length === 1 &&
        key >= "0" && key <= "9") { return key; }
    name = event.code;
    if (typeof name === "string") {
      if (name.length === 6 && name.substring(0, 5) === "Digit") {
        letra = name.charAt(5);
        if (letra >= "0" && letra <= "9") { return letra; }
      }
      if (name.length === 7 && name.substring(0, 6) === "Numpad") {
        letra = name.charAt(6);
        if (letra >= "0" && letra <= "9") { return letra; }
      }
    }
    code = event.charCode || 0;
    if (code >= 48 && code <= 57) { return String(code - 48); }
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

  /* Lo que el aparato mando de verdad, en una linea. Con esto una foto contesta
   * "no toma los numeros": o aparece la linea y dice por que campo vino el
   * digito -o donde estaba el foco-, o no aparece nada y entonces los eventos
   * no llegan a la pagina, que es otra falla y tambien es una respuesta. */
  function describe(event) {
    var node = event.target || event.srcElement;
    return (event.type || "?") +
           " kc=" + (event.keyCode === undefined ? "-" : event.keyCode) +
           " w=" + (event.which === undefined ? "-" : event.which) +
           " cc=" + (event.charCode === undefined ? "-" : event.charCode) +
           " key=" + (event.key === undefined ? "-" : event.key) +
           " code=" + (event.code === undefined ? "-" : event.code) +
           " foco=" + (node && node.nodeName ? node.nodeName : "-");
  }

  function create(options) {
    var actions = options.actions || [];
    var delay = options.delay > 0 ? options.delay : 900;
    var onBuffer = options.onBuffer || function () {};
    var onKey = options.onKey || function () {};
    var host = options.host ||
               (typeof window !== "undefined" ? window : null);
    var buffer = "";
    var timer = 0;
    var codes = [];
    var vistos = 0;
    var ultimoDigitoEn = 0;
    var i;
    for (i = 0; i < actions.length; i++) { codes.push(actions[i].code); }

    function ahora() { return new Date().getTime(); }

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

    /* El MISMO evento pasa por document y por window: se lo marca para no
     * contarlo dos veces. Marcar el evento es mas seguro que mirar el reloj,
     * porque dos teclas de verdad pueden llegar muy juntas. */
    function yaVisto(event) {
      if (event.__asclKeypad) { return true; }
      event.__asclKeypad = 1;
      return false;
    }

    function atender(event) {
      var code = event.keyCode || event.which || 0;
      var target = event.target || event.srcElement;
      var tag = target && target.nodeName ? target.nodeName.toUpperCase() : "";
      var digit;
      vistos++;
      onKey(describe(event), vistos);
      /* Si el foco esta en un campo de texto, los numeros son texto, no ordenes. */
      if (tag === "INPUT" || tag === "TEXTAREA") { return; }
      digit = digitOf(event);
      if (digit) {
        ultimoDigitoEn = ahora();
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

    function onKeyDown(event) {
      if (yaVisto(event)) { return; }
      atender(event);
    }

    /* `keypress` es el PLAN B, no un segundo camino: solo se atiende si el
     * `keydown` de esa misma tecla no dio un digito. Sin esa guarda, un aparato
     * que manda los dos eventos dispararia cada numero dos veces. */
    function onKeyPress(event) {
      if (yaVisto(event)) { return; }
      if (ahora() - ultimoDigitoEn < 300) { return; }
      atender(event);
    }

    if (options.attach !== false && typeof document !== "undefined") {
      if (document.addEventListener) {
        document.addEventListener("keydown", onKeyDown, false);
        document.addEventListener("keypress", onKeyPress, false);
        if (typeof window !== "undefined" && window.addEventListener) {
          window.addEventListener("keydown", onKeyDown, false);
          window.addEventListener("keypress", onKeyPress, false);
        }
      } else {
        document.onkeydown = onKeyDown;
      }
    }

    return { push: push, flush: flush, clear: clear, codes: codes,
             delay: delay, onKeyDown: onKeyDown, onKeyPress: onKeyPress };
  }

  return { create: create, digitOf: digitOf, isPrefix: isPrefix,
           describe: describe };
})();
