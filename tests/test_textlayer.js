"use strict";
/* INT-004-A: capa de texto nativo (frontend/textlayer.js).
 *  - create() todo-o-nada: un item invalido y no se crea nada;
 *  - setText() valida y conserva el ultimo estado valido (INV-7);
 *  - markDirty() marca via markRectDirty exactamente las cajas CON texto
 *    que entran en la grilla; texto vacio no marca;
 *  - draw() escala por cellPx, pinta borde ANTES que relleno, limita al
 *    ancho de la caja (maxWidth) y cachea el string de fuente por cellPx
 *    (sin reconstrucciones en el camino caliente);
 *  - texto vacio no dibuja ni marca. */

var assert = require("assert");
var TL = require("../frontend/textlayer.js");

function item(over) {
  var base = {
    id: "a", x: 2, y: 3, w: 8, h: 4, size: 2,
    color: "#fff", outline: "#000", font: "serif", align: "left",
    text: "HOLA"
  }, key;
  for (key in over) {
    if (Object.prototype.hasOwnProperty.call(over, key)) {
      base[key] = over[key];
    }
  }
  return base;
}

/* ---- contexto Canvas2D sintetico: registra cada strokeText/fillText con el
 * estado vigente en el momento de la llamada ---- */
function MockCtx() {
  this.font = "";
  this.textAlign = "";
  this.textBaseline = "";
  this.fillStyle = "";
  this.strokeStyle = "";
  this.lineWidth = 0;
  this.lineJoin = "";
  /* INT-007-A: estado de sombra; un item sin sombra no debe tocarlo */
  this.shadowColor = "SIN-TOCAR";
  this.shadowBlur = -1;
  this.shadowOffsetX = -1;
  this.shadowOffsetY = -1;
  this.ops = [];
}
MockCtx.prototype._snap = function (op, text, x, y, maxW) {
  this.ops.push({
    op: op, text: text, x: x, y: y, maxW: maxW,
    font: this.font, align: this.textAlign, baseline: this.textBaseline,
    style: op === "stroke" ? this.strokeStyle : this.fillStyle,
    lineWidth: this.lineWidth, lineJoin: this.lineJoin,
    shadowColor: this.shadowColor, shadowBlur: this.shadowBlur,
    shadowOffsetX: this.shadowOffsetX, shadowOffsetY: this.shadowOffsetY
  });
};
MockCtx.prototype.strokeText = function (t, x, y, m) {
  this._snap("stroke", t, x, y, m);
};
MockCtx.prototype.fillText = function (t, x, y, m) {
  this._snap("fill", t, x, y, m);
};

function MockReader(cols, rows) {
  this.header = { cols: cols, rows: rows };
  this.rects = [];
}
MockReader.prototype.markRectDirty = function (x, y, w, h) {
  this.rects.push(x + "," + y + "," + w + "," + h);
};

/* ---- create: todo-o-nada ---- */
(function () {
  var bad = [
    null, undefined, "x", 7, {},
    [],                                        /* vacio */
    [item({}), item({ id: "a" })],             /* id duplicado */
    [item({ id: -1 })], [item({ id: 1.5 })], [item({ id: "" })],
    [item({ x: -1 })], [item({ y: 0.5 })],
    [item({ w: 0 })], [item({ h: 0 })], [item({ w: "8" })],
    [item({ size: 0 })], [item({ size: -2 })],
    [item({ size: 5 })],                       /* size > h */
    [item({ size: "2" })],
    [item({ color: "" })], [item({ color: 7 })],
    [item({ color: "a\u0007b" })],           /* control char */
    [item({ outline: 7 })], [item({ outline: "" })],
    [item({ font: "" })], [item({ font: 7 })],
    [item({ align: "top" })], [item({ align: 7 })],
    [item({ text: 7 })],
    [item({ text: new Array(66).join("x") })], /* 65 chars > MAX_TEXT */
    [item({ text: "a\nb" })],
    /* el item 2 invalido tira TODO el lote */
    [item({}), item({ id: "b", w: 0 })]
  ], big = [], i;
  for (i = 0; i < 65; i++) big.push(item({ id: i }));
  bad.push(big);
  for (i = 0; i < bad.length; i++) {
    assert.strictEqual(TL.create(bad[i]), null,
      "create debio rechazar el caso " + i);
  }
  /* limite exacto de texto (64) e items (64) aceptados */
  assert.notStrictEqual(
    TL.create([item({ text: new Array(65).join("x") })]), null);
  big.pop();
  assert.notStrictEqual(TL.create(big), null);
})();

/* ---- defaults y estado inicial ---- */
(function () {
  var layer = TL.create([{ id: 0, x: 1, y: 1, w: 4, h: 2, size: 1,
                           color: "red" }]);
  var ctx = new MockCtx(), reader = new MockReader(40, 20);
  assert.notStrictEqual(layer, null);
  assert.strictEqual(layer.count, 1);
  /* sin texto inicial: no dibuja ni marca */
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 0);
  assert.strictEqual(layer.markDirty(reader), 0);
  assert.strictEqual(reader.rects.length, 0);
  /* con texto: usa los defaults (sans-serif, center, sin borde) */
  assert.strictEqual(layer.setText(0, "77"), true);
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 1);
  assert.strictEqual(ctx.ops[0].op, "fill");
  assert.strictEqual(ctx.ops[0].font, "10px sans-serif");
  assert.strictEqual(ctx.ops[0].align, "center");
  assert.strictEqual(ctx.ops[0].x, (1 + 4 / 2) * 10);
})();

/* ---- setText: validacion y conservacion (INV-7) ---- */
(function () {
  var layer = TL.create([item({})]);
  assert.strictEqual(layer.setText("zzz", "1"), false);  /* id inexistente */
  assert.strictEqual(layer.setText("a", 7), false);
  assert.strictEqual(layer.setText("a", null), false);
  assert.strictEqual(layer.setText("a", new Array(66).join("x")), false);
  assert.strictEqual(layer.setText("a", "x\ty"), false);
  /* los fallos conservaron el texto inicial */
  var ctx = new MockCtx();
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops[1].text, "HOLA");
  /* "" valido: borra */
  assert.strictEqual(layer.setText("a", ""), true);
  ctx = new MockCtx();
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 0);
  var reader = new MockReader(40, 20);
  assert.strictEqual(layer.markDirty(reader), 0);
})();

/* ---- markDirty: cajas exactas, solo con texto, fuera de grilla se saltea ---- */
(function () {
  var layer = TL.create([
    item({ id: 1, x: 2, y: 3, w: 8, h: 4, text: "UNO" }),
    item({ id: 2, x: 30, y: 15, w: 10, h: 5, text: "DOS" }),
    item({ id: 3, x: 0, y: 0, w: 5, h: 2, text: "" }),      /* sin texto */
    item({ id: 4, x: 35, y: 0, w: 6, h: 2, text: "FUERA" }) /* 35+6>40 */
  ]);
  var reader = new MockReader(40, 20);
  assert.strictEqual(layer.markDirty(reader), 2);
  assert.deepStrictEqual(reader.rects, ["2,3,8,4", "30,15,10,5"]);
  /* reader invalido: 0, sin lanzar */
  assert.strictEqual(layer.markDirty(null), 0);
  assert.strictEqual(layer.markDirty({}), 0);
  assert.strictEqual(layer.markDirty({ header: reader.header }), 0);
})();

/* ---- draw: escalado por cellPx, anclajes por align, maxWidth ---- */
(function () {
  var layer = TL.create([
    item({ id: "l", align: "left" }),
    item({ id: "c", align: "center" }),
    item({ id: "r", align: "right" })
  ]);
  var ctx = new MockCtx(), k;
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 6);  /* stroke+fill por item */
  for (k = 0; k < ctx.ops.length; k++) {
    assert.strictEqual(ctx.ops[k].font, "20px serif");   /* size 2 * 10px */
    assert.strictEqual(ctx.ops[k].baseline, "middle");
    assert.strictEqual(ctx.ops[k].y, (3 + 4 / 2) * 10);  /* centro vertical */
    assert.strictEqual(ctx.ops[k].maxW, 80);             /* w * cellPx */
  }
  assert.strictEqual(ctx.ops[0].x, 20);           /* left: x*cellPx */
  assert.strictEqual(ctx.ops[2].x, (2 + 4) * 10); /* center */
  assert.strictEqual(ctx.ops[4].x, (2 + 8) * 10); /* right */
  /* borde antes que relleno, con los estilos correctos */
  assert.strictEqual(ctx.ops[0].op, "stroke");
  assert.strictEqual(ctx.ops[0].style, "#000");
  assert.strictEqual(ctx.ops[0].lineWidth, 20 / 8);
  assert.strictEqual(ctx.ops[0].lineJoin, "round");
  assert.strictEqual(ctx.ops[1].op, "fill");
  assert.strictEqual(ctx.ops[1].style, "#fff");
  /* guardas: no lanza, no pinta */
  layer.draw(null, 10);
  layer.draw(ctx, 0);
  layer.draw(ctx, NaN);
  assert.strictEqual(ctx.ops.length, 6);
})();

/* ---- cache del string de fuente por cellPx ---- */
(function () {
  var layer = TL.create([item({})]);
  var ctx = new MockCtx();
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops[0].font, "20px serif");
  /* mismo cellPx: NO se reconstruye (si se reconstruyera, pisaria esto) */
  layer._fontStr[0] = "CACHEADO";
  ctx = new MockCtx();
  layer.draw(ctx, 10);
  assert.strictEqual(ctx.ops[0].font, "CACHEADO");
  /* cellPx nuevo: se reconstruye con la escala nueva */
  ctx = new MockCtx();
  layer.draw(ctx, 25);
  assert.strictEqual(ctx.ops[0].font, "50px serif");
  assert.strictEqual(ctx.ops[0].maxW, 8 * 25);
  assert.strictEqual(ctx.ops[0].lineWidth, 50 / 8);
  /* lineWidth nunca baja de 1 */
  var thin = TL.create([item({ id: "t", size: 1 })]);
  ctx = new MockCtx();
  thin.draw(ctx, 4);   /* 4px de texto -> 0.5 -> clamp a 1 */
  assert.strictEqual(ctx.ops[0].lineWidth, 1);
})();

/* ---- INT-007-A: weight y shadow ---- */
(function () {
  var bad = [
    [item({ weight: 7 })], [item({ weight: "" })],
    [item({ weight: new Array(34).join("x") })],  /* 33 > MAX_WEIGHT */
    [item({ weight: "a\u0007b" })],    /* control char */
    [item({ shadow: 7 })], [item({ shadow: "" })],
    [item({ shadow: "a\nb" })],
    [item({ shadow: new Array(66).join("x") })]   /* 65 > MAX_STYLE */
  ], i;
  for (i = 0; i < bad.length; i++) {
    assert.strictEqual(TL.create(bad[i]), null,
      "create debio rechazar weight/shadow invalido, caso " + i);
  }
  /* null explicito = omitido */
  assert.notStrictEqual(TL.create([item({ weight: null, shadow: null })]),
    null);

  /* sin sombra: las propiedades shadow* del contexto NO se tocan (la salida
   * es identica a la historica) */
  var plain = TL.create([item({})]);
  var ctx = new MockCtx();
  plain.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 2);
  assert.strictEqual(ctx.shadowColor, "SIN-TOCAR");
  assert.strictEqual(ctx.shadowBlur, -1);

  /* weight se antepone al font shorthand; sin weight el string es el
   * historico (cubierto por los tests previos) */
  var bold = TL.create([item({ weight: "bold" })]);
  ctx = new MockCtx();
  bold.draw(ctx, 10);
  assert.strictEqual(ctx.ops[0].font, "bold 20px serif");

  /* con sombra y borde: la sombra vive SOLO en la primera pasada (stroke)
   * y el relleno queda nitido; al terminar el item la sombra esta apagada */
  var sh = TL.create([item({ shadow: "rgba(0,0,0,0.5)" })]);
  ctx = new MockCtx();
  sh.draw(ctx, 10);
  assert.strictEqual(ctx.ops[0].op, "stroke");
  assert.strictEqual(ctx.ops[0].shadowColor, "rgba(0,0,0,0.5)");
  assert.strictEqual(ctx.ops[0].shadowBlur > 0, true);
  assert.strictEqual(ctx.ops[0].shadowOffsetX, ctx.ops[0].shadowOffsetY);
  assert.strictEqual(ctx.ops[1].op, "fill");
  assert.strictEqual(ctx.ops[1].shadowColor, "rgba(0,0,0,0)");
  assert.strictEqual(ctx.ops[1].shadowBlur, 0);
  assert.strictEqual(ctx.shadowColor, "rgba(0,0,0,0)");
  assert.strictEqual(ctx.shadowBlur, 0);

  /* sin borde: la sombra va en el relleno y se apaga al salir */
  var shNoOutline = TL.create([{ id: 0, x: 2, y: 3, w: 8, h: 4, size: 2,
    color: "#fff", shadow: "rgba(0,0,0,0.5)", text: "77" }]);
  ctx = new MockCtx();
  shNoOutline.draw(ctx, 10);
  assert.strictEqual(ctx.ops.length, 1);
  assert.strictEqual(ctx.ops[0].op, "fill");
  assert.strictEqual(ctx.ops[0].shadowColor, "rgba(0,0,0,0.5)");
  assert.strictEqual(ctx.shadowColor, "rgba(0,0,0,0)");

  /* derrame acotado a < 1 celda: blur <= 0.6*cellPx y offset <= 0.4*cellPx
   * aun con texto enorme */
  var huge = TL.create([{ id: 0, x: 0, y: 0, w: 40, h: 20, size: 20,
    color: "#fff", shadow: "#000", text: "9" }]);
  ctx = new MockCtx();
  huge.draw(ctx, 10);
  assert.strictEqual(ctx.ops[0].shadowBlur <= 6, true);
  assert.strictEqual(ctx.ops[0].shadowOffsetX <= 4, true);

  /* markDirty: la caja con sombra se marca expandida 1 celda, clampeada a
   * la grilla; sin sombra queda exacta (cubierto por los tests previos) */
  var layer = TL.create([
    item({ id: 1, x: 2, y: 3, w: 8, h: 4, text: "UNO",
           shadow: "rgba(0,0,0,0.5)" }),
    item({ id: 2, x: 0, y: 0, w: 5, h: 2, text: "BORDE",
           shadow: "rgba(0,0,0,0.5)" }),
    item({ id: 3, x: 30, y: 15, w: 10, h: 5, text: "ESQ",
           shadow: "rgba(0,0,0,0.5)" })
  ]);
  var reader = new MockReader(40, 20);
  assert.strictEqual(layer.markDirty(reader), 3);
  assert.deepStrictEqual(reader.rects,
    ["1,2,10,6",    /* expandida en las 4 direcciones */
     "0,0,6,3",     /* clamp en el origen */
     "29,14,11,6"]); /* clamp contra cols/rows */
})();

console.log("textlayer tests: OK");
