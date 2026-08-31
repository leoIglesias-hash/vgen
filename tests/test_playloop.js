"use strict";
/* W-22: el motor compartido de cadencia y pre-decode (frontend/playloop.js).
 *
 * Se prueba contra readers falsos: lo que importa acá es la maquinaria de
 * tiempo y el intercambio, no la decodificación (que ya tiene sus propias
 * suites). El reloj es inyectado para que las medidas sean deterministas.
 */

var assert = require("assert");
var PlayLoop = require("../frontend/playloop.js");

function fakeClock() {
  var clock = { t: 0 };
  clock.now = function () { return clock.t; };
  return clock;
}

/* Reader falso: registra los seek y declara keyframes cada `every` cuadros. */
function fakeReader(options) {
  options = options || {};
  var every = options.every || 15;
  var reader = {
    header: {
      fps: options.fps || 15,
      nFrames: options.nFrames || 150,
      cols: 8, rows: 8
    },
    decodedIndex: -1,
    seeks: [],
    disposed: 0
  };
  reader._isKey = function (index) { return index % every === 0; };
  reader.seek = function (index) {
    if (options.seekThrows) { throw new Error("seek roto"); }
    reader.seeks.push(index);
    reader.decodedIndex = index;
    return reader;
  };
  reader.dispose = function () { reader.disposed++; };
  return reader;
}

function fakeAPI(readers) {
  var made = 0;
  return {
    made: function () { return made; },
    parse: function () {
      var reader = readers[made];
      made++;
      if (!reader) { throw new Error("sin readers de repuesto"); }
      return reader;
    }
  };
}

/* --------------------------------------------------------------- cadencia -- */

/* Con la cadencia apagada el motor es exactamente el comportamiento histórico:
 * el cuadro sale de floor() del reloj maestro y nada más. */
(function pacingOffEsElComportamientoHistorico() {
  var clock = fakeClock();
  var engine = PlayLoop.create({ now: clock.now, pacing: false, predecode: false });
  assert.strictEqual(engine.target(3.7, 15), 3);
  assert.strictEqual(Math.round(engine.fraction * 100), 70);
  assert.strictEqual(engine.target(9.25, 15), 9);
}());

/* El primer cuadro tras un reset se engancha al maestro sin corregir nada,
 * incluso cuando now() vale 0 (la bandera es explícita justamente por eso). */
(function primerCuadroSeEnganchaAlMaestro() {
  var clock = fakeClock();
  var engine = PlayLoop.create({ now: clock.now, predecode: false });
  assert.strictEqual(engine.target(4.5, 15), 4);
  assert.strictEqual(engine.fraction, 0.5);
}());

/* Cuenta cada cuánto cambia el cuadro mostrado, en callbacks del display. */
function gapCollector() {
  var previous = -1, lastChange = 0, gaps = {};
  return {
    gaps: gaps,
    add: function (target, tick) {
      var gap;
      if (target === previous) { return; }
      if (previous >= 0) {
        gap = "g" + (tick - lastChange);
        gaps[gap] = (gaps[gap] || 0) + 1;
      }
      previous = target;
      lastChange = tick;
    }
  };
}

/* W-20 (a): el defecto que esto arregla. Un TV viejo mueve audio.currentTime a
 * saltos gruesos e IRREGULARES: acá el maestro avanza un cuadro cada 3/5/4/4
 * refrescos (el promedio es el correcto, el reparto no). Decidiendo con
 * floor(maestro) esa irregularidad se copia tal cual a la pantalla; con la
 * cadencia anclada al display el reparto queda parejo en 4. El mismo tren de
 * callbacks alimenta a los dos motores para que la comparación sea directa. */
(function cadenciaParejaConMaestroEscalonado() {
  var pattern = [3, 5, 4, 4];
  var clock = fakeClock();
  var paced = PlayLoop.create({ now: clock.now, predecode: false });
  var raw = PlayLoop.create({ now: clock.now, pacing: false, predecode: false });
  var pacedGaps = gapCollector(), rawGaps = gapCollector();
  var i, step = 0, next = pattern[0], master = 0;
  paced.target(0, 15);
  raw.target(0, 15);
  for (i = 1; i <= 240; i++) {
    clock.t = i * (1000 / 60);
    if (i === next) {
      master++;
      step++;
      next += pattern[step % pattern.length];
    }
    pacedGaps.add(paced.target(master, 15), i);
    rawGaps.add(raw.target(master, 15), i);
  }
  assert((rawGaps.gaps.g3 || 0) + (rawGaps.gaps.g5 || 0) >= 20,
    "sin cadencia la irregularidad del maestro llega entera a la pantalla");
  assert((pacedGaps.gaps.g3 || 0) + (pacedGaps.gaps.g5 || 0) <= 4,
    "con cadencia sólo queda algún reajuste puntual");
  assert(pacedGaps.gaps.g4 >= 45,
    "un cuadro nuevo cada 4 callbacks de 60 Hz, que es 15 fps parejo");
}());

/* Un desvío grande (seek, loop, stall) no se corrige de a poco: resincroniza. */
(function desvioGrandeResincronizaDeUna() {
  var clock = fakeClock();
  var engine = PlayLoop.create({ now: clock.now, predecode: false });
  engine.target(0, 15);
  clock.t = 16;
  assert.strictEqual(engine.target(40, 15), 40, "más de 2 cuadros: salto directo");
  clock.t = 32;
  /* Dentro de la banda la corrección es lenta: no salta al maestro. */
  assert.strictEqual(engine.target(41, 15) < 41, true);
}());

/* Una pestaña oculta deja un dt enorme; integrarlo adelantaría el video. */
(function dtEnormeNoSeIntegra() {
  var clock = fakeClock();
  var engine = PlayLoop.create({ now: clock.now, predecode: false });
  engine.target(0, 15);
  clock.t = 5000;
  assert.strictEqual(engine.target(0, 15), 0,
    "un dt mayor a " + PlayLoop.MAX_TICK_MS + " ms no avanza la fase");
}());

(function resetPacingVuelveAEngancharse() {
  var clock = fakeClock();
  var engine = PlayLoop.create({ now: clock.now, predecode: false });
  engine.target(0, 15);
  clock.t = 1000;
  engine.target(15, 15);
  engine.resetPacing(0);
  assert.strictEqual(engine.fraction, 0);
  clock.t = 1016;
  assert.strictEqual(engine.target(7.5, 15), 7, "tras el reset manda el maestro");
}());

/* ------------------------------------------------------------- pre-decode -- */

(function adelantaElProximoKeyframeYSeIntercambia() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var spare = fakeReader({ every: 15 });
  var adopted = [], costs = [];
  var engine = PlayLoop.create({
    now: clock.now,
    onAdopt: function (index) { adopted.push(index); },
    onPreDecode: function (cost) { costs.push(cost); }
  });
  assert.strictEqual(engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8), true);
  assert.strictEqual(spare.decodedIndex, -1, "el spare arranca sin cuadro decodificado");

  engine.target(2.0, 15);
  assert.strictEqual(engine.idle(main, 2) >= 0, true, "hay tiempo muerto: adelanta");
  assert.deepStrictEqual(spare.seeks, [15], "adelanta el próximo keyframe, no el próximo cuadro");
  assert.strictEqual(engine.readyIndex(), 15);
  assert.strictEqual(main.seeks.length, 0, "el reader que se muestra no se toca");
  assert.strictEqual(costs.length, 1);

  /* Un cuadro que no es el adelantado no intercambia nada. */
  assert.strictEqual(engine.exchange(9, main), null);

  /* El adelantado sí: la página recibe el spare y el motor se queda con el otro. */
  assert.strictEqual(engine.exchange(15, main), spare);
  assert.deepStrictEqual(adopted, [15]);
  assert.deepStrictEqual(spare.seeks, [15], "el keyframe adoptado no se vuelve a decodificar");
  assert.strictEqual(engine.readyIndex(), -1, "adoptado deja de estar listo");
  /* Y ahora el spare es el reader viejo: el siguiente adelanto lo usa a él. */
  engine.target(16.0, 15);
  engine.idle(spare, 16);
  assert.deepStrictEqual(main.seeks, [30], "el reader desplazado pasa a ser el de repuesto");
}());

/* Adelantar un keyframe que no llega a tiempo provoca justo el tirón que esto
 * viene a sacar: sin margen suficiente no se adelanta. */
(function sinMargenNoAdelanta() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var spare = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ now: clock.now });
  engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8);
  /* fracción 0.99 de un cuadro de 66,7 ms deja menos de 1 ms de margen. */
  engine.target(2.99, 15);
  assert.strictEqual(engine.idle(main, 2), -1);
  assert.deepStrictEqual(spare.seeks, []);
}());

(function sinIndiceDeKeyframesNoAdelanta() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var spare = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ now: clock.now });
  engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8);
  main._isKey = null;
  engine.target(2.0, 15);
  assert.strictEqual(engine.idle(main, 2), -1, "reader sin _isKey: no se adelanta nada");
  assert.strictEqual(engine.nextKeyframe(main, 0), -1);
}());

/* El horizonte acota la búsqueda: un clip sin keyframes cercanos no obliga a
 * recorrer el video entero en cada callback ocioso. */
(function elHorizonteAcotaLaBusqueda() {
  var reader = fakeReader({ every: 15, fps: 15, nFrames: 1000 });
  var engine = PlayLoop.create({ predecode: false });
  reader._isKey = function (index) { return index === 900; };
  assert.strictEqual(engine.nextKeyframe(reader, 10), -1,
    "fuera del horizonte de " + PlayLoop.KEY_HORIZON_S + " s no se busca");
  reader._isKey = function (index) { return index === 40; };
  assert.strictEqual(engine.nextKeyframe(reader, 10), 40);
}());

/* INV-7: si el spare no se puede crear, o falla decodificando, el player sigue
 * exactamente como si el pre-decode no existiera. */
(function elPreDecodeEsOpcional() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ now: clock.now });
  assert.strictEqual(engine.attach(fakeAPI([]), new ArrayBuffer(8), 0, 8), false,
    "un parse que falla no propaga la excepción");
  assert.strictEqual(engine.hasSpare(), false);
  engine.target(2.0, 15);
  assert.strictEqual(engine.idle(main, 2), -1);
  assert.strictEqual(engine.exchange(15, main), null);

  var roto = fakeReader({ every: 15, seekThrows: true });
  var otro = PlayLoop.create({ now: clock.now });
  otro.attach(fakeAPI([roto]), new ArrayBuffer(8), 0, 8);
  otro.target(2.0, 15);
  assert.strictEqual(otro.idle(main, 2), -1, "un seek roto no propaga la excepción");
  assert.strictEqual(otro.hasSpare(), false, "el spare roto no se reintenta");
  otro.target(3.0, 15);
  assert.strictEqual(otro.idle(main, 3), -1);
}());

(function apagarElPreDecodeLiberaElSegundoCells() {
  var spare = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ predecode: true });
  engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8);
  assert.strictEqual(engine.hasSpare(), true);
  engine.setPreDecode(false);
  assert.strictEqual(engine.hasSpare(), false);
  assert.strictEqual(spare.disposed, 1, "el segundo `cells` se suelta");
  /* Y con el pre-decode apagado attach no vuelve a crearlo. */
  assert.strictEqual(engine.attach(fakeAPI([fakeReader({})]), new ArrayBuffer(8), 0, 8), false);
  assert.strictEqual(engine.hasSpare(), false);
}());

(function invalidateDescartaLoAdelantadoSinTocarElReader() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var spare = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ now: clock.now });
  engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8);
  engine.target(2.0, 15);
  engine.idle(main, 2);
  assert.strictEqual(engine.readyIndex(), 15);
  engine.invalidate();
  assert.strictEqual(engine.readyIndex(), -1);
  assert.strictEqual(engine.exchange(15, main), null, "tras un salto no se adopta");
  assert.strictEqual(engine.hasSpare(), true, "pero el spare se conserva para el próximo");
}());

/* Dos llamadas ociosas seguidas no repiten trabajo. */
(function noVuelveAAdelantarLoYaAdelantado() {
  var clock = fakeClock();
  var main = fakeReader({ every: 15 });
  var spare = fakeReader({ every: 15 });
  var engine = PlayLoop.create({ now: clock.now });
  engine.attach(fakeAPI([spare]), new ArrayBuffer(8), 0, 8);
  engine.target(2.0, 15);
  engine.idle(main, 2);
  engine.idle(main, 2);
  engine.idle(main, 3);
  assert.deepStrictEqual(spare.seeks, [15]);
}());

console.log("playloop tests: OK");
