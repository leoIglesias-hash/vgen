/*
 * playloop.js - motor de cadencia y pre-decode compartido por TODAS las
 * paginas del front (W-22).
 *
 * Hasta W-20 las dos piezas vivian copiadas dentro de `tv-player.html` y de
 * `diagnostic-player.html`, y no existian en `live-player.html` -que es lo que
 * sirve iargen.com/player/- ni en `player.html`. Copias divergentes de la misma
 * maquinaria son exactamente lo que hace que una mejora medida no llegue al
 * producto. Aca vive una sola vez y la consumen las cuatro paginas.
 *
 * Lo que hace, y por que:
 *
 *   (a) CADENCIA. En TVs viejos `audio.currentTime` avanza a saltos gruesos,
 *       asi que decidir el cuadro con floor(currentTime*fps) reparte los frames
 *       en 5/7/6/6 refrescos en vez de 6/6/6/6. Una cadencia irregular se
 *       percibe peor que un fps bajo constante (por eso se descarto el
 *       1920@10). La fase avanza con el reloj del DISPLAY y se corrige LENTO
 *       contra el reloj maestro: el maestro sigue mandando, lo que deja de
 *       decidir es el instante exacto de cada cuadro. Un desvio grande -seek,
 *       loop, stall- resincroniza de una.
 *
 *   (b) PRE-DECODE. Tres de cada cuatro callbacks a 60 Hz para un video de
 *       15 fps solo miran el reloj y vuelven a agendar. Ese tiempo muerto se usa
 *       para adelantar el proximo KEYFRAME, que no depende del estado actual y
 *       por eso es seguro adelantar (un delta exigiria una base definida y se
 *       disenaria aparte). Adoptarlo es INTERCAMBIAR dos readers, no copiar
 *       celdas: cada reader queda internamente consistente -su paleta, su dirty
 *       y su decodedIndex viajan juntos- asi que la transaccionalidad del
 *       invariante 4 no se toca. El adoptado trae dirtyFull de su propio
 *       keyframe, o sea que el renderer sube el cuadro entero, que es
 *       exactamente lo correcto.
 *
 * El motor NO es dueno del reader que se esta mostrando: la pagina lo sigue
 * teniendo en su propia variable y se lo pasa en cada llamada. Eso deja el
 * intercambio explicito en la pagina (que tambien tiene que reapuntar su
 * renderer y, si hay, su overlay) en vez de esconderlo detras de un accessor.
 *
 * INV-7: el pre-decode es una optimizacion, no un requisito. Si el segundo
 * reader no se puede crear -o falla decodificando- el motor se apaga solo y la
 * pagina sigue reproduciendo igual que antes.
 *
 * API:
 *   var engine = ASCILINEPlayLoop.create({now:fn, pacing:bool, predecode:bool,
 *                                         onPreDecode:fn, onAdopt:fn});
 *   engine.target(clockFrames, fps) -> indice de cuadro a mostrar
 *   engine.resetPacing(atFrame)     tras seek/loop/arranque
 *   engine.attach(readerAPI, buffer, offset, length) -> bool  (crea el spare)
 *   engine.exchange(index, current) -> reader adoptado o null
 *   engine.idle(reader, lastShown)  -> ms gastados, o -1 si no adelanto nada
 *   engine.invalidate()             el spare deja de ser adoptable
 *   engine.setPreDecode(bool)       apagarlo libera el segundo `cells`
 *   engine.detach()                 suelta el spare
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) { module.exports = api; }
  root.ASCILINEPlayLoop = api;
}(typeof window !== "undefined" ? window : this, function () {
  "use strict";

  /* Correccion por callback contra el reloj maestro. Chica a proposito: la
   * cadencia tiene que dominar sobre el ruido del maestro, no al reves. */
  var DRIFT_GAIN = 0.02;
  /* Mas de dos cuadros de desvio ya no es ruido del reloj: es un salto real. */
  var RESYNC_FRAMES = 2;
  /* Un dt mayor es una pestana que estuvo oculta o un stall: no se integra. */
  var MAX_TICK_MS = 250;
  /* Margen sobre el costo medido antes de animarse a adelantar un keyframe:
   * adelantar uno que no llega a tiempo provoca justo el tiron que esto saca. */
  var PRE_MARGIN_MS = 4;
  /* Horizonte de busqueda del proximo keyframe, en segundos de video. */
  var KEY_HORIZON_S = 3;

  function defaultNow() {
    return Date.now ? Date.now() : new Date().getTime();
  }

  function Engine(options) {
    options = options || {};
    this.now = typeof options.now === "function" ? options.now : defaultNow;
    this.pacing = options.pacing !== false;
    this.preDecode = options.predecode !== false;
    this.onPreDecode = typeof options.onPreDecode === "function" ? options.onPreDecode : null;
    this.onAdopt = typeof options.onAdopt === "function" ? options.onAdopt : null;
    /* Fraccion del cuadro actual ya transcurrida: de ahi sale el tiempo muerto
     * que puede gastar el pre-decode sin llegar tarde. */
    this.fraction = 0;
    this._phase = 0;
    this._lastTick = 0;
    this._started = false;
    this._spare = null;
    this._spareIndex = -1;
    this._spareReady = false;
    this._cost = 0;
  }

  /* (a) Cuadro a mostrar. `clock` es la posicion segun el reloj maestro en
   * frames fraccionarios; la pagina la calcula porque solo ella sabe si el
   * maestro es el audio o su propio reloj. */
  Engine.prototype.target = function (clock, fps) {
    var t = this.now(), dt = this._started ? t - this._lastTick : 0, drift;
    this._lastTick = t;
    if (!this.pacing) {
      this.fraction = clock - Math.floor(clock);
      return Math.floor(clock);
    }
    if (!this._started) {
      /* Primer cuadro despues de un reset: todavia no hay cadencia observada,
       * asi que se engancha al maestro sin corregir nada. La bandera es
       * explicita porque now() puede valer 0 justo al abrir la pagina. */
      this._started = true;
      this._phase = clock;
      this.fraction = this._phase - Math.floor(this._phase);
      return Math.floor(this._phase);
    }
    if (dt < 0 || dt > MAX_TICK_MS) { dt = 0; }
    this._phase += dt * fps / 1000;
    drift = clock - this._phase;
    if (drift > RESYNC_FRAMES || drift < -RESYNC_FRAMES) { this._phase = clock; }
    else { this._phase += drift * DRIFT_GAIN; }
    this.fraction = this._phase - Math.floor(this._phase);
    return Math.floor(this._phase);
  };

  Engine.prototype.resetPacing = function (atFrame) {
    this._phase = atFrame > 0 ? atFrame : 0;
    this._lastTick = 0;
    this.fraction = 0;
    this._started = false;
    return this;
  };

  /* (b) Segundo reader sobre los MISMOS bytes. Cuesta otro `cells` (2 MB a
   * 1920) y su scratch de inflate, y a cambio evita reescribir la maquinaria
   * dirty del reader para decodificar fuera de linea. Anotado para MEM-001. */
  Engine.prototype.attach = function (readerAPI, buffer, offset, length) {
    this.detach();
    this._cost = 0;
    if (!this.preDecode) { return false; }
    if (!readerAPI || typeof readerAPI.parse !== "function") { return false; }
    try {
      this._spare = readerAPI.parse(buffer, offset, length);
      this._spare.decodedIndex = -1;
    } catch (ignoredSpareParse) {
      this._spare = null;
      return false;
    }
    return true;
  };

  Engine.prototype.detach = function () {
    if (this._spare && typeof this._spare.dispose === "function") {
      try { this._spare.dispose(); } catch (ignoredSpareDispose) {}
    }
    this._spare = null;
    this._spareReady = false;
    this._spareIndex = -1;
    return this;
  };

  /* Tras un seek manual, un loop o cualquier salto, lo adelantado deja de
   * corresponder: se descarta sin tocar el reader que se esta mostrando. */
  Engine.prototype.invalidate = function () {
    this._spareReady = false;
    this._spareIndex = -1;
    return this;
  };

  Engine.prototype.setPreDecode = function (flag) {
    this.preDecode = !!flag;
    if (!this.preDecode) { this.detach(); }
    return this;
  };

  Engine.prototype.hasSpare = function () { return !!this._spare; };

  Engine.prototype.readyIndex = function () {
    return this._spareReady ? this._spareIndex : -1;
  };

  /* El intercambio. Devuelve el reader ya decodificado en `index` -que pasa a
   * ser el de la pagina- y se queda con el que la pagina venia usando. Si no
   * hay nada adelantado para ese indice devuelve null y la pagina hace su
   * seek normal. */
  Engine.prototype.exchange = function (index, current) {
    var adopted;
    if (!this._spareReady || this._spareIndex !== index || !this._spare) { return null; }
    if (!current) { return null; }
    adopted = this._spare;
    this._spare = current;
    this._spareReady = false;
    this._spareIndex = -1;
    if (this.onAdopt) { this.onAdopt(index); }
    return adopted;
  };

  /* Primer keyframe estrictamente posterior a `after`, dentro del horizonte.
   * Sin `_isKey` (reader v1 sin indice de keyframes) no se adelanta nada. */
  Engine.prototype.nextKeyframe = function (reader, after) {
    var i, last, horizon;
    if (!reader || typeof reader._isKey !== "function") { return -1; }
    last = reader.header.nFrames - 1;
    horizon = after + 1 + Math.round(reader.header.fps * KEY_HORIZON_S);
    if (horizon > last) { horizon = last; }
    for (i = after + 1; i <= horizon; i++) {
      if (reader._isKey(i)) { return i; }
    }
    return -1;
  };

  /* Se llama en los callbacks que NO cambian de cuadro. Devuelve el costo en
   * ms de lo que adelanto, o -1 si decidio no adelantar nada. */
  Engine.prototype.idle = function (reader, after) {
    var slack, key, t0, cost;
    if (!this.preDecode || !this._spare || this._spareReady || !reader) { return -1; }
    slack = (1 - this.fraction) / reader.header.fps * 1000;
    if (slack < this._cost + PRE_MARGIN_MS) { return -1; }
    key = this.nextKeyframe(reader, after);
    if (key < 0) { return -1; }
    t0 = this.now();
    try { this._spare.seek(key); }
    catch (ignoredPreDecode) {
      /* Un spare que no puede decodificar no vuelve a intentarse: el player
       * sigue exactamente como si nunca hubiera existido. */
      this._spare = null;
      return -1;
    }
    cost = this.now() - t0;
    /* Sube de golpe y baja lento: el presupuesto tiene que acordarse del peor
     * keyframe, no del promedio. */
    if (cost > this._cost) { this._cost = cost; }
    else { this._cost = this._cost * 0.9 + cost * 0.1; }
    this._spareIndex = key;
    this._spareReady = true;
    if (this.onPreDecode) { this.onPreDecode(cost); }
    return cost;
  };

  return {
    create: function (options) { return new Engine(options); },
    Engine: Engine,
    DRIFT_GAIN: DRIFT_GAIN,
    RESYNC_FRAMES: RESYNC_FRAMES,
    MAX_TICK_MS: MAX_TICK_MS,
    PRE_MARGIN_MS: PRE_MARGIN_MS,
    KEY_HORIZON_S: KEY_HORIZON_S
  };
}));
