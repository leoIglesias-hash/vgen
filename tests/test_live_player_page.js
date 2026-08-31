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
assert(page.indexOf('src="textlayer.js"') < page.indexOf('src="textfeed.js"'));

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
assert(/markTextDirty[\s\S]{0,700}reader\.markRectDirty\(x,y,w,h\)/.test(inline[1]),
  "todas las cajas declaradas se marcan para que borrar texto no deje fantasma");
/* INT-007-A: las cajas con sombra se marcan expandidas 1 celda (el derrame
 * de la sombra esta acotado a < 1 celda en textlayer.js) */
assert(/if\(it\.shadow\)\{\s*if\(x>0\)\{x--;w\+\+;\}/.test(inline[1]),
  "la caja con sombra se expande para que cambiar texto no deje halo");

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

/* INT-006: texto standalone — sin overlay de matriz el player declara tres
 * campos de 2 digitos dimensionados por cols/rows, el feed (textfeed.js)
 * expone la interfaz digitCount/setValues y el canal lo consume SIN cambios */
assert(inline[1].indexOf("function standaloneSpec()") >= 0);
assert(inline[1].indexOf("function attachStandalone(reason)") >= 0);
assert(inline[1].indexOf("fields.push({id:k+1,width:2})") >= 0,
  "tres campos de 2 digitos por defecto");
assert(inline[1].indexOf("textFeed=window.ASCILINETextFeed.create(textLayer,spec.fields)") >= 0);
assert(inline[1].indexOf("ASCILINEDataChannel.create(DATA_URL,textFeed,{intervalMs:15000})") >= 0,
  "el canal consume el feed con la misma interfaz que el overlay");
/* todos los caminos sin overlay de matriz caen al modo standalone */
assert(/attachStandalone\("Sin sidecar \("/.test(inline[1]));
assert(/s\.onerror=function\(\)\{ attachStandalone\("Sin sidecar/.test(inline[1]));
assert(/attachStandalone\("attach devolvio null/.test(inline[1]));
assert(/attachStandalone\("Sidecar rechazado: "/.test(inline[1]));
assert(/attachStandalone\("Clip sin paleta completa/.test(inline[1]));
/* boton de carga y limpieza en standalone: mismo orden sin re-seek */
assert(/else if\(textFeed\)\{\s*digits=randomDigits\(textFeed\.digitCount\);/.test(inline[1]));
assert(/else if\(textFeed && textLayer\)\{[\s\S]{0,400}textLayer\.setText\(feedFields\[j\]\.id,""\);[\s\S]{0,200}markTextDirty\(\);\s*renderer\.draw\(reader\);\s*textLayer\.draw\(/.test(inline[1]),
  "limpiar en standalone vacia los textos y repinta sin re-seek");

/* INT-006-C (D7=a): imagen nativa opcional con drawImage sobre el MISMO
 * canvas, despues del texto; su caja se marca sucia cada frame; sin imagen
 * (404) nada cambia (INV-7) */
assert(page.indexOf('IMG_URL="./outputs/logo.png"') >= 0);
assert(inline[1].indexOf("function tryAttachImage()") >= 0);
assert(/if\(!textLayer \|\| imgEl \|\| !window\.Image\) return;/.test(inline[1]),
  "la imagen solo se activa con texto declarado (renderer ya Canvas2D)");
assert(/renderer\.draw\(reader\);\s*if\(textLayer\) textLayer\.draw\(renderer\.ctx,cellScale\);\s*if\(imgBox\) drawImg\(frame\);/.test(inline[1]),
  "la imagen se dibuja despues del frame y del texto");
assert(/if\(imgSpin\)\{\s*reader\.markRectDirty\(imgSpin\.x,imgSpin\.y,imgSpin\.w,imgSpin\.h\);/.test(inline[1]),
  "debajo de la imagen se repinta el cuadrado que circunscribe el giro");
assert(inline[1].indexOf("im.onerror=function(){") >= 0,
  "sin imagen nada cambia (INV-7)");
assert(/imgBox\.w\*cellScale,imgBox\.h\*cellScale/.test(inline[1]),
  "la imagen escala con cellScale como el texto");

/* INT-007-A: tipografia menos comun con fallback serif + sombra translucida
 * en las cajas de texto (espejo INT-004 y standalone INT-006) */
assert(/TEXT_FONT='"Palatino Linotype","Book Antiqua",Palatino,Georgia,serif'/.test(inline[1]),
  "pila de fuentes menos comun con fallback serif");
assert(/TEXT_SHADOW="rgba\(0,0,0,0\.\d+\)"/.test(inline[1]),
  "la sombra es translucida (rgba con alpha)");
assert.strictEqual(
  inline[1].match(/font:TEXT_FONT,\s*weight:TEXT_WEIGHT,shadow:TEXT_SHADOW/g).length, 2,
  "espejo y standalone comparten fuente, peso y sombra");

/* INT-007-B: el logo gira como ruleta simulada — angulo determinista por
 * frame (sin reloj), save/translate/rotate/restore acotados al draw, y el
 * area sucia es el cuadrado circunscripto (lado = diagonal de la caja) */
assert(/ctx\.save\(\);\s*ctx\.translate\(cx,cy\);\s*ctx\.rotate\(\(frame%IMG_TURN\)\*IMG_STEP\);[\s\S]{0,220}ctx\.restore\(\);/.test(inline[1]),
  "rotacion alrededor del centro, determinista por frame, sin estado colgado");
assert(inline[1].indexOf("IMG_STEP=2*Math.PI/IMG_TURN") >= 0,
  "vuelta completa cada IMG_TURN frames");
assert(inline[1].indexOf("d=Math.ceil(Math.sqrt(w*w+h*h))") >= 0,
  "el cuadrado sucio circunscribe la rotacion (diagonal de la caja)");
assert(/drawImg\(lastShown\)/.test(inline[1]),
  "los redraws en pausa usan el frame mostrado: mismo frame, mismo angulo");

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
assert(page.indexOf('s==="ASCLVID1" || s==="ASCLVID2" || s==="ASCLVID3"') >= 0);
assert(page.indexOf("headerSize+asclLen+audioLen+metaLen!==buf.byteLength") >= 0);
assert(page.indexOf("bytes[7]-48!==bytes[headerSize+4]") >= 0,
  "envelope e interior deben declarar la misma version");
assert(page.indexOf('s==="ASCLVID3"?20:16') >= 0,
  "F6-3: el header ASCLVID3 mide 20 bytes (meta_len)");
assert(page.indexOf("tryAttachOverlay(bundleMeta)") >= 0,
  "F6-3: el sidecar embebido en el ASCLVID3 alimenta el overlay sin XHR extra");

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
