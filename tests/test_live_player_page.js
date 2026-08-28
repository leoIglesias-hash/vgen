"use strict";
/* F7: la pagina del runtime real (frontend/live-player.html) reemplaza a la
 * demo de laboratorio y respeta los contratos de INT-001 y W-14. */

var assert = require("assert");
var fs = require("fs");
var path = require("path");

var frontend = path.join(__dirname, "..", "frontend");
var page = fs.readFileSync(path.join(frontend, "live-player.html"), "utf8");
var inline = page.match(/<script>\s*([\s\S]*?)\s*<\/script>\s*<\/body>/);

assert(inline, "controlador inline presente");
assert(!fs.existsSync(path.join(frontend, "demo-overlay.html")),
  "la demo de laboratorio queda reemplazada por el runtime real");

/* rutas estables del despliegue plano */
assert(page.indexOf('CLIP_URL="./outputs/clip.asclv"') >= 0);
assert(page.indexOf('SLOTS_URL="./outputs/clip.slots"') >= 0);
assert(page.indexOf('DATA_URL="./outputs/data.txt"') >= 0);

/* orden de scripts: readers -> renderers -> slots -> overlay -> canal -> texto */
assert(page.indexOf('src="reader.js"') < page.indexOf('src="reader-v2.js"'));
assert(page.indexOf('src="reader-v2.js"') < page.indexOf('src="reader-factory.js"'));
assert(page.indexOf('src="render-webgl.js"') < page.indexOf('src="slots.js"'));
assert(page.indexOf('src="slots.js"') < page.indexOf('src="overlay.js"'));
assert(page.indexOf('src="overlay.js"') < page.indexOf('src="datachannel.js"'));
assert(page.indexOf('src="datachannel.js"') < page.indexOf('src="textlayer.js"'));

/* un solo layer: exactamente un canvas en el markup, sin capa DOM extra */
assert.strictEqual(page.match(/<canvas/g).length, 1,
  "INV-1: un canvas, una matriz");

/* orden por frame de INT-001 §9.2: beforeSeek -> seek -> afterSeek */
assert(/overlay\.beforeSeek\(\);[\s\S]{0,40}reader\.seek\(frame\);[\s\S]{0,40}overlay\.afterSeek\(\);/.test(inline[1]),
  "el overlay debe envolver al seek en ese orden exacto");
assert(inline[1].indexOf("drawFrame") >= 0);

/* INT-004: orden por frame con texto nativo — seekTo (beforeSeek/seek/
 * afterSeek) -> markDirty(texto) -> renderer.draw -> textLayer.draw */
assert(/seekTo\(frame\);\s*if\(textLayer\) markTextDirty\(\);\s*renderer\.draw\(reader\);\s*if\(textLayer\) textLayer\.draw\(/.test(inline[1]),
  "el texto se marca sucio tras el seek y se dibuja despues del frame");
assert(inline[1].indexOf("textLayer.markDirty(reader)") >= 0,
  "markTextDirty usa la API de la capa");
assert(/markTextDirty[\s\S]{0,400}reader\.markRectDirty\(it\.x,it\.y,it\.w,it\.h\)/.test(inline[1]),
  "todas las cajas declaradas se marcan para que borrar texto no deje fantasma");

/* INT-004 / regla 6: con texto declarado el renderer ES Canvas2D y su
 * backing store escala (pixelScale) para texto nitido */
assert(/if\(!textLayer\)\{\s*try\{\s*var w=new window\.WebGLRenderer/.test(inline[1]),
  "WebGL solo se intenta sin texto nativo");
assert(inline[1].indexOf("r.pixelScale=cellPx") >= 0,
  "el backing store del Canvas2D escala con el zoom cuando hay texto");
assert(inline[1].indexOf("cellScale=(textLayer && r.pixelScale>1)?r.pixelScale:1") >= 0);

/* INT-004: solo sidecar v2 con campos de digitos grandes genera espejo, y
 * todo payload aceptado (boton o canal) alimenta matriz Y texto */
assert(inline[1].indexOf("if(meta.version!==2) return") >= 0);
assert(inline[1].indexOf("if(s0.w<20) continue") >= 0,
  "solo los numeros grandes se espejan");
assert(/overlay\.setValues=function\(payload\)\{\s*var ok=origSet\.call\(overlay,payload\);\s*if\(ok\) mirrorTexts\(String\(payload\)\);/.test(inline[1]),
  "el espejo se alimenta de los mismos payloads que la matriz");
assert(/overlay\.clear=function\(\)\{\s*origClear\.call\(overlay\);\s*clearTexts\(\);/.test(inline[1]),
  "clear limpia matriz y textos juntos");
assert(/overlay\.clear\(\);\s*if\(reader && lastShown>=0 && !playing\)\{\s*if\(textLayer\) markTextDirty\(\);\s*renderer\.draw\(reader\);\s*if\(textLayer\) textLayer\.draw\(/.test(inline[1]),
  "limpiar dibuja SIN re-seek: el seek resetearia los rects que clear() dejo marcados");

/* INV-7: sin reserva, sin sidecar o con sidecar ajeno el video sigue */
assert(page.indexOf("overlay inactivo") >= 0);
assert(page.indexOf("El video sigue") >= 0);
assert(page.indexOf("attach devolvio null") >= 0);
assert(page.indexOf("Sin sidecar") >= 0);

/* verificacion cruzada parametrica: la cola reservada del bundle valida el
 * sidecar (v1: 10 en 246..; v2: pal_reserved en 256-N..) */
assert(page.indexOf("palReserved=(bytes.length>10 && bytes[8]===2)?bytes[10]:10") >= 0,
  "la reserva se toma del byte de version/pal_reserved del sidecar");
assert(page.indexOf("tail[i]=reader.palette[first*3+i]") >= 0,
  "la cola reservada del bundle valida el sidecar");
assert(page.indexOf("h.palSize!==256") >= 0);

/* la carga simulada genera payloads validos por campo (presencia v2) */
assert(page.indexOf("function randomPayload(fields)") >= 0);
assert(page.indexOf('out+="0"+padNumber(0,w)') >= 0,
  "presencia 0 con ceros canonicos");
assert(page.indexOf('out+="1"+padNumber(v,w)') >= 0);

/* canal de datos real con la cadencia de INT-001 §8.2 */
assert(page.indexOf("ASCILINEDataChannel.create(DATA_URL,overlay,{intervalMs:15000})") >= 0);
assert(page.indexOf("channel.start()") >= 0);

/* endurecimiento del bundle, como player.html */
assert(page.indexOf('s==="ASCLVID1" || s==="ASCLVID2"') >= 0);
assert(page.indexOf("bytes[7]===49 || bytes[7]===50") >= 0);
assert(page.indexOf("16+asclLen+audioLen!==buf.byteLength") >= 0);
assert(page.indexOf("bytes[7]-48!==bytes[20]") >= 0,
  "envelope e interior deben declarar la misma version");

/* W-14: robustez heredada del player tradicional */
assert(page.indexOf("renderer.dispose(true)") >= 0);
assert(page.indexOf("w.dispose(true)") >= 0);
assert(page.indexOf("nativeRequestFrame && nativeCancelFrame") >= 0);
assert(page.indexOf("nativeRequestFrame.call(window,fn)") >= 0 &&
  page.indexOf("nativeCancelFrame.call(window,id)") >= 0);
assert(/try\{\s*drawFrame\(target\);\s*\}catch/.test(inline[1]),
  "el loop debe capturar excepciones de seek/draw");
assert(inline[1].indexOf("Error de reproduccion") >= 0);
assert(inline[1].indexOf("?src=") < 0, "sin origen arbitrario por query");

assert.strictEqual(/\b(?:let|const|class)\b|=>|`/.test(inline[1]), false);
assert.doesNotThrow(function () { new Function(inline[1]); });

console.log("live player page tests: OK");
