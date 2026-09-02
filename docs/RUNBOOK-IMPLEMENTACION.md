# Runbook de implementación — formato propio híbrido

Estado: **nace el 2026-09-01 con ASCILINE-hybrid; alcance ampliado el mismo día
tras el debate de dirección, y método corregido esa misma tarde** (se descartó la
sonda sintética: se arranca emitiendo). Este archivo contiene SOLO las reglas de
ejecución y las tareas del paradigma nuevo.

El runbook del paradigma anterior (100 % JS: F10, F11, F8, DIAG-001 y opcionales,
todas **suspendidas**) está archivado verbatim en
[`historico/RUNBOOK-IMPLEMENTACION-asclv-js.md`](historico/RUNBOOK-IMPLEMENTACION-asclv-js.md);
si alguna se retoma, vuelve de ahí con decisión del operador, no se reescribe.

**Antes de ejecutar cualquier tarea de acá, leer
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md)** — es el norte del proyecto y
lo que evita que una sesión post-compact se desvíe. **El rumbo detallado
—evidencia, caminos, gates numéricos, orden y decisiones pendientes— está en
[`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md)** (vigente desde el
primer reporte de aparato, 2026-09-01); este runbook solo lleva las tareas.

## 0. Reglas de ejecución (heredadas, siguen todas vigentes)

1. **Commits directos a `main`, un commit por tarea.** Mensaje: `<ID>: <título>`.
2. **Regresión antes de cerrar.** La máquina de trabajo no tiene Python ni Node
   **a propósito**: la regresión completa corre en GitHub Actions (workflow
   `regression`) en cada push. Una tarea se cierra solo con ese CI en verde.
3. **Fila de registro obligatoria** para toda tarea que cambie bytes o fluidez
   medible. La medición en aparatos la hace el operador; su veredicto se
   transcribe textual.
4. **Una tarea no empieza si su precondición no está cerrada.**
5. **Ninguna tarea se cierra «porque compila».** El criterio de cierre está
   escrito y es verificable.
6. **Todo test nuevo se cablea en `tests/run_all.py` en el mismo commit.**
7. **Procedencia por sesión** en `RUNBOOK-ESTADO.md`.
8. **Se supone explícito, se reproduce, y recién ahí se normaliza** (regla
   corregida el 2026-09-01). Arrancar por suposición está permitido y es el
   método; lo que está prohibido es **normalizar** una suposición en la spec sin
   haberla reproducido. Toda suposición vive escrita con su refutación en
   [`EMISION-V0.md`](EMISION-V0.md) §4.
9. **Ningún aparato solo define el formato.** Un aparato puede refutar; para
   consagrar hacen falta al menos dos clases de aparato, o la decisión manual del
   operador (que siempre prevalece). Ver [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §1.

## 1. El paradigma (decisión del operador, 2026-09-01)

Resumen ejecutable; el desarrollo está en
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md).

- **Construimos un formato propio, códec-agnóstico**, que se decide caro y
  offline y se reproduce **siempre por hardware**, y que se puede **intervenir en
  vivo sin re-codificar**. No es un player: es un paquete + un contrato de
  reproducción.
- **`<video>` es la única puerta al hardware**: todo lo que emitamos termina en
  algo que `<video>` acepta nativamente. Nada se decodifica en CPU propia.
- **Composición de linajes:** de **VP9/AV1** la compresión y las primitivas
  (golden frames, tiles, alfa en WebM); de **DASH** el modelo de datos y la
  intervención estructural (Periods, AdaptationSets, Representations); de **HLS**
  el piso de compatibilidad probado; de **ASCILINE** el máster determinista, la
  intervención matricial y la disciplina de medición.
- **Encoder caro, decoder sin estrés.** La filosofía madre no cambió; cambió
  quién ejecuta: antes un intérprete JS, ahora un bloque de silicio.
- **Base 1280×720 con fps variable** (operador): fijar la resolución es lo que
  vuelve intercambiables a las piezas y evita que el decodificador se reconfigure.
- **Dos capas:** `<video>` base + **un** canvas de intervención. Reemplaza al
  invariante de un-solo-layer del paradigma anterior.
- **El player JS no muere:** queda como reproductor de escritorio y banco de
  verificación del máster. Se mantiene, no crece.
- Evidencia que sostiene todo: REGISTRO, DIAG-002/003 (2026-09-01) — en la caja
  real el JS da 290 ms/cuadro contra 66,7 de presupuesto y el `producto.mp4`
  (4,1 MB) *«reproduce muy bien»*.

## 2. Fase H — formato híbrido

**Orden (actualizado al cierre de H-13, 2026-09-01 noche): H-11 → H-12 → H-6 →
H-7 → H-8.** H-13 cerrada (REGISTRO «H-13: reporte de la caja»). H-9 cerrada; H-10 tiene la caja medida y queda
abierta para las otras clases. Se arrancó **emitiendo** (pack v0,
[`EMISION-V0.md`](EMISION-V0.md)) y se corrige reproduciendo. Regla de
dependencia: **H-7 no empieza sin H-13 y H-11 cerradas; H-8 no empieza sin H-7
aprobada por el operador.** H-14 y W-26 son independientes. La regla de avance:
**la fluidez es un gate, los bytes y el arranque son el objetivo**
([`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md) §3).

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **H-0** | repo, `docs/` | **CERRADA 2026-09-01** (`8dae1e5`). Crear `ASCILINE-hybrid` (clon con historia completa, main + assets), mover a `docs/historico/` los diseños del paradigma JS, reescribir CLAUDE.md/runbooks/índices | repo en `leoIglesias-hash/ASCILINE-hybrid` con CI verde ✔ |
| **H-1..H-3** | — | **REEMPLAZADAS** el 2026-09-01 por el debate de dirección. Eran: diseño del player híbrido, investigación de emisión H.264, player mínimo. Absorbidas y ampliadas al pasar el alcance a «formato propio códec-agnóstico». **IDs no reusables** | — |
| **H-4, H-5** | — | **REEMPLAZADAS** el 2026-09-01 (misma tarde) por decisión del operador: eran la **sonda sintética de capacidades** y el **banco** como paso previo. Se descartaron porque hubieran fijado el formato contra **una sola TV box**. Su contenido útil está **disuelto dentro de H-9/H-10**: la página que reproduce el pack v0 reporta lo mismo, pero sobre material real y en varios aparatos. **IDs no reusables** | — |
| **H-9** | `tools/emit_pieces.py` + workflow `emitir-v0` | **CERRADA 2026-09-01** (run `33566441576`). El pack v0 de [`EMISION-V0.md`](EMISION-V0.md) §3 emitido desde el máster: Baseline, Main, VP9, VP9+alfa, más `hls-ts/`, `hls-fmp4/` y `dash/` **por remux**, y `MANIFEST.tsv`. Resumen y evidencia: [`ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md`](ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md) | piezas regenerables byte a byte con su sha256; CI verde ✔ (deja abierta **H-14**) |
| **H-10** | `frontend/v0.html` + `frontend/keypad.js` | **reproducirlo y que él nos diga.** **La TV box está medida (2026-09-01)**: reporte transcripto en el REGISTRO, fila en [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §5, veredictos en [`EMISION-V0.md`](EMISION-V0.md) §4.b. Faltan el ojo del operador para alfa y VP9/HLS-TS (contador ciego), y las **otras clases** (celular, Smart TV, escritorio) — o su decisión manual de fijar la caja como clase que consagra | **abierta, no bloquea**: cierra con la tabla de §5 llena para ≥2 clases **o** con la decisión escrita del operador; veredictos textuales |
| **H-13** | `frontend/vgenfeed.js` (nuevo) + `frontend/v0.html` (crece) + `tests/test_vgenfeed.js` (nuevo) + `tests/test_v0_page.js` | **CERRADA 2026-09-01 noche** (código `85eebd1`→`b3d5837`, docs `0589dc9`; publicado en `v0/`; reporte de la caja transcripto en el REGISTRO; S9/S10/S12 marcadas en EMISION-V0 §4.c; camino del muxer escrito en el plan §2.3 y §4 H-8). Era: **por dónde entra el paquete** — con el pack ya publicado, **cero emisión nueva**. **(a) `vgenfeed.js`**, módulo ES5 compartido que H-8 va a reusar: `getBytes(url, cb)` (XHR `arraybuffer`), `concat(parts, mime)` → `Blob`, `feedMse(video, mime, urls, hooks)` (un `SourceBuffer`, anexo secuencial encadenado por `updateend`, `endOfStream` al final) y `switchTo(video, src, hooks)` (cambio de pieza midiendo pedido → primer avance de `currentTime`). Sin `Promise`, sin `JSON`. **(b) Cinco pruebas nuevas en `v0.html`**, todas sobre `dash/init.m4s` + `chunk-*.m4s` y las piezas progresivas publicadas: **`96` MSE H.264** (S9); **`97` Blob concatenado** (`init + 16 segmentos` en un Blob → `blob:`; S10; reporta también `duration`); **`98` intercambio de orden** (segmentos 1..8, 13..16, 9..12 por MSE y por Blob; S12); **`8` cambio a demanda** (VP9 → Baseline → VP9 por `src`, tres cambios, columna `cambio_ms` = pedido → primer avance; gate ≤ 1 s); **`99` bucle 60 s** (VP9 con `loop`, contando `seeking`/`waiting` por vuelta). **`5` corre las cinco en secuencia**; **`1` corre todo** (v0 + H-13). La tecla `8` deja de ser «solo hls-ts» (ese caso sigue dentro de `4`). Detección de `SourceBuffer.changeType` en la cabecera. **(c) Medición**: columna **`congel`** (muestras de 100 ms sin avance de `currentTime`, estando en `play`), «atascos» **cuenta solo después de arrancar**, la fila dice **«ciego»** cuando `total` no se movió, y **no se pausa al terminar** una medición (la pieza siguiente reemplaza `src`; la última queda sonando). Ningún dígito suelto queda demorado (regla del mando; `test_v0_page.js` lo verifica, más «hay 5 pruebas de paquete» y «existe la columna congel»). `test_vgenfeed.js` prueba el encadenado por `updateend` con un `SourceBuffer` falso y el orden de anexo | filas en el REGISTRO por camino con las columnas de [`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md) §3.1 (foto del reporte, tecla `95`); S9/S10/S12 marcadas en EMISION-V0 §4.c; gate ES5 y CI verdes; publicado en `v0/` (copia en `deploy/` antes); y **queda escrito qué camino implementa el muxer (H-8)** |
| **H-11** | `frontend/v0.html` (crece) | **la bifurcación de layout**: canvas de intervención encima del `<video>` (número, ruleta, texto) con tres cargas —nada / rectángulo chico repintado a 15 fps / pantalla completa una vez—, sobre Baseline y VP9, midiendo caídos con y sin él contra la línea de base ya medida (0–2/155). Reusa `overlay.js`/`textlayer.js`/`slots.js`/`datachannel.js`; canvas dimensionado **al panel**, nunca a la superficie | S5 resuelta con números (caja + segunda clase, o decisión del operador): la intervención va **encima** o **al lado**, y queda escrito en DISENO §9; gate ES5 verde |
| **H-6** | `tools/` + workflow | **matriz por bytes a igual look, con la fluidez como gate** (reorientada por el reporte: en la caja la fluidez está saturada y el decodificador es hardware). Ejes: VP9 (`crf`, `cpu-used`); **fps variable por segmento** derivado del máster (S6, ahora medido en bytes); H.264 piso relajado (Main/High, `refs`, B dentro del GOP cerrado 15); zonas estáticas; paleta consciente del 4:2:0. Emisión **v1**: cada variante con sus segmentos (CMAF para H.264; **WebM segmentado para VP9 → S11**), **con la pista de audio del máster muxeada** (AAC en mp4, Opus en WebM → **S13**) y una pista ambiente suelta para `<audio>` (→ **S14**). Incluye una fila de **referencia** con los defaults de ffmpeg (el `producto.mp4`) bajo los mismos contadores | tabla de variantes en el REGISTRO con medición **por aparato** y los gates de §3.1; **receta por perfil de dispositivo**, no una global, firmada por el operador |
| **H-12** | `frontend/` | **caché**: descarga por XHR con progreso → `Blob` → **IndexedDB** → reproducción desde `blob:`, con pineo por contenido (CACHE-001) y borrado de claves viejas | el pack sobrevive a un reinicio del aparato y reproduce sin red; degradación escrita si no persiste |
| **H-7** | `docs/SPEC-VGEN.md` (nuevo) | **spec normativa**: layout binario, manifiesto (texto tabulado, **no JSON**: el gate ES5 lo prohíbe), segmentos, sprites, cues, huecos, y el mapa perfil → camino de runtime. Cierra las filas «gateadas» de [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md) §10 | spec aprobada por el operador; **toda decisión trazable a una fila reproducida en ≥2 clases de aparato** |
| **H-8** | `frontend/` + `backend/` | **muxer ES5 + player híbrido mínimo**: emisor del paquete offline y, en el aparato, **lo que H-13 haya dejado en pie**: concatenador CMAF (camino A, si S10 se sostiene), alimentador MSE (camino B, si S9), generador de playlist HLS-TS (camino D, reserva). `<video>` + `<audio>` separado + canvas de intervención. Incluye «cambiar solo la música» | reproduce en la caja real con intervención activa y dentro de los gates de §3.1 (veredicto del operador); gate ES5 verde; depende de **H-7** |
| **H-14** | `tools/emit_pieces.py` + workflow | **determinismo del carril H.264** (deuda abierta contra el invariante 7, detectada en H-9): dos corridas del mismo máster con los mismos parámetros dieron **bytes distintos en Baseline y Main**, con la misma versión de ffmpeg y la misma línea de opciones de x264; VP9 salió byte-idéntico. Emitir la misma pieza **dos veces dentro de la misma corrida** para separar «no determinista» de «depende de la máquina»; si es lo segundo, decidir entre fijar la codificación (p. ej. sin `mbtree`) o redefinir el invariante como «misma build + misma máquina». Registrar `lscpu` en el workflow | la causa queda establecida con evidencia y el invariante 7 vuelve a cumplirse, o se redefine por escrito con el visto del operador |
| **W-26** | `frontend/live-player.html` | (heredada, independiente) la raíz publicada elige WebGL sin salida: aceptar `?renderer=` como las demás páginas y decidir el default para WebViews de TV box | la raíz respeta `?renderer=canvas2d`; gate ES5 verde |

**Pendiente externo (no es tarea nuestra):** pedirle a la app de la caja que el
WebView reporte el tamaño real del panel — hoy da 3840×2160 sobre un panel de
1280×720 (9× de píxeles regalados al compositor, medido en DIAG-003). Beneficia
también al carril `<video>`.

**Anotado sin tarea** (en [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md)
§11): nivel N4 de intervención (intercambio sub-cuadro por tiles/slices), cuadros
sostenidos escritos a mano, golden frames de VP9, composición offline de escenas,
y la nota de que F10 —suspendida— seguiría mejorando el producto porque el video
hereda los píxeles del máster.

## 3. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa (CI en verde sobre su push);
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si cambió bytes o fluidez, su fila está en el REGISTRO;
4. el commit lleva su ID;
5. si tocó el frontend, el gate ES5 pasa;
6. lo que requiere pantalla lo firma **el operador**, nadie más;
7. si es una tarea de medición, **ninguna celda quedó estimada**: o está medida o
   está vacía — y **ninguna conclusión sale de un solo aparato**.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por
tarea. Ese archivo —no la memoria de nadie— es lo que le dice a la próxima
sesión dónde quedó todo.
