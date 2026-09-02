# Estado de ejecución del runbook

Este archivo es la memoria entre sesiones. Se actualiza **al cerrar cada tarea**, no al
final del día. La próxima sesión de trabajo —humana o asistida— arranca leyendo este
archivo, no reconstruyendo el contexto.

Reglas de uso:

1. Una fila por tarea del [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).
   Al cerrarse una fase completa, sus tablas se archivan verbatim en `ejecutados/`
   y acá queda el resumen por carril (sección «Tareas cerradas»).
2. Estados válidos: `pendiente`, `en curso`, `cerrada`, `bloqueada (<por qué>)`,
   `archivada (<evidencia>)`, `opcional`.
3. Una tarea `cerrada` cumple la definición de terminado del runbook §5; no se marca antes.
4. Toda decisión que desvíe del runbook se anota en la bitácora de abajo con fecha y
   motivo. El runbook no se edita en silencio.

## Próxima acción (actualizado 2026-09-01 — el alcance es un FORMATO PROPIO)

> **Leer primero [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md).** Es el norte
> del proyecto y lo que evita que una sesión post-compact se desvíe. Después,
> [`EMISION-V0.md`](EMISION-V0.md) (el primer video y sus suposiciones) y
> [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) (el método).

**Dos cosas pasaron el 2026-09-01, en este orden.** Primero el operador decidió
la dirección que DIAG-002/003 había dejado pendiente (adoptar el híbrido; nace
este repo; **H-0 cerrada**). Después, en un debate de ideas el mismo día, el
alcance se amplió: ya no construimos «un player híbrido con mp4», sino

> **un formato de video propio, códec-agnóstico, que se decide caro y offline, se
> reproduce siempre por hardware, y se puede intervenir en vivo sin re-codificar.**

Sus palabras: *«nuestro propio formato de video sería ideal… sacar de estos
formatos cada cosa útil: v9 la compresión, dash la compatibilidad, asciline la
base que permite todo. encoder caro no importa, decoder con poco estrés»*.

**Lo que quedó fijado en el debate** (desarrollo en
[`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md)):

- **`<video>` es la única puerta al hardware.** Todo lo que emitamos termina en
  algo que `<video>` acepta nativamente; nada se decodifica en CPU propia.
- **Códec-agnóstico desde el día uno:** piezas etiquetadas, el aparato elige.
  H.264 Baseline es el **piso**, no el centro. Hipótesis fuerte a verificar: si
  YouTube anda bien en la caja, esa caja tiene **VP9 por hardware** — o sea que
  VP9 es su camino más rodado, no el exótico.
- **De DASH tomamos el modelo de datos** (Periods / AdaptationSets /
  Representations / segmentos por rango de bytes), no su runtime. Es la gramática
  exacta de un contenido intervenible: **cambiar solo la música es cambiar de
  pista**, y una intervención es un Period.
- **Base 1280×720 con fps variable** (decisión del operador). Fijar la resolución
  es lo que vuelve **intercambiables** a las piezas y evita que el decodificador
  se reconfigure a mitad de stream. El fps variable por segmento es
  probablemente el ahorro más grande y más barato de todo el sistema.
- **Escalera de intervención N1–N4** con su límite honesto escrito: N1
  estructural (gratis), N2 composición encima, N3 variantes pre-codificadas, N4
  sub-cuadro (investigación). Tocar un píxel arbitrario del video en vivo es
  imposible y todo diseño que lo necesite está mal planteado.
- **Se supone explícito, se reproduce, y recién ahí se normaliza.** El proyecto ya
  se equivocó una vez por suponer capacidades (F9 completa, y en la caja
  290 ms/cuadro contra 66,7) — y estuvo a punto de cometer el error simétrico
  (ver abajo).

**Corrección del método, la misma tarde del 2026-09-01.** El operador leyó el
plan y frenó la sonda:

> *«el camino de H-4 no es el correcto porque nos basaríamos solo en 1 tv box,
> mejor tomar las bondades de cada encoder para crear el nuestro y ya. Y empezar
> con el primer video aunque sea basado en suposiciones: al probarlo podremos ir
> viendo si vamos en la dirección correcta paso a paso.»*

Tiene razón en las dos cosas: una sonda sintética corrida en una sola caja
**sobreajusta el formato a ese aparato**, y reproducir material real responde más
que un cuestionario. Así que la sonda **no se pospone: se disuelve dentro del
primer video** — la página que reproduce el pack v0 reporta lo mismo, pero sobre
material verdadero y en varios aparatos. Invariante nuevo:
**ningún aparato solo define el formato** (refutar sí, consagrar no).

---

### ⏵ LO PRIMERO AL RETOMAR (actualizado con H-12 ejecutada hasta la pantalla, 2026-09-02 madrugada)

**La TV box ya está medida.** El operador corrió `https://iargen.com/player/v0/`
en la caja y mandó la foto del reporte; está **transcripto textual** en el
REGISTRO (entrada «H-10: primer reporte de aparato»), volcado en
[`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) §5 y con veredicto por suposición en
[`EMISION-V0.md`](EMISION-V0.md) §4.b. Lo que salió, en seis líneas: todo lo
progresivo reproduce **fluido por hardware** (0–2 caídos/155, con la superficie
4K activa); **Main = Baseline → decodificador hardware**; el arranque lo manda la
cantidad de bytes (H.264 2.985 ms por red, **517 ms** desde `blob:`; VP9
931 ms); **VP9 reproduce** (contador ciego, falta el ojo); **HLS-TS nativo sí**,
HLS-fMP4 inservible, DASH no; **MSE declarado y sin probar**.

**El rumbo está ordenado en
[`PLAN-IMPLEMENTACION-VGEN.md`](PLAN-IMPLEMENTACION-VGEN.md)** (evidencia,
caminos, gates numéricos, orden y decisiones pendientes). Leerlo antes de tocar
nada.

1. **El operador ya respondió cinco de las siete decisiones del §6** (REGISTRO,
   «Respuestas del operador al primer reporte»): el alfa **compone**; VP9
   «perfecto, hasta más fluido»; HLS-TS «se traba mucho al iniciar» (camino D
   fuera del producto); **la TV box es la clase principal** (consagra; la PC
   refuta); contenido = **loop intervenido + publicidad que reemplaza y vuelve +
   incentivadores a demanda** (plan §2.7); nombre **`.vgen`**. Y después las
   otras dos: **audio sí** («tipo radio» + hablado con sincronía en momentos →
   diseño en plan §2.6, S13/S14) y **gates aprobados** con caídos ≤ 3 %.
   **No queda ninguna decisión pendiente del operador.**
2. **H-13 CERRADA** (código `85eebd1`→`b3d5837`, docs `0589dc9`, publicado en
   `v0/`, y la **foto de la caja** transcripta en el REGISTRO, «H-13: reporte de
   la caja»). Lo que quedó decidido: **S9 consagrada** (MSE 2.033 ms por red,
   156 cuadros, 0 atascos, `changeType` sí); **S10 en dos clases** (el Blob
   `init+16` es un archivo → el muxer A es `concat()`; arranque 1.286 ms a
   re-medir contra un mp4 clásico); **S12 por MSE `sequence` sí, por Blob no,
   en dos clases** («blob orden se tilda en una parte», operador); **bucle por
   `loop` refutado** (3 `waiting`/60 s) → el bucle del producto va por MSE;
   cambio por `src` 305 ms a VP9 y 1.468/1.180 a Baseline → el incentivador es
   VP9 y residente (H-12). El camino del muxer está escrito en el plan §2.3 y
   §4 (H-8). Las filas `cambio*` miden 4 s a propósito (65 cuadros), no es un
   timer roto.
3. **H-11 EJECUTADA hasta la pantalla** (`fd9a7ab`, CI verde; REGISTRO «H-11
   implementada hasta la pantalla»): `<canvas id="capa">` encima del `<video>`,
   dimensionado **al panel** (1280/3840 en la caja), con tres cargas (nada /
   rect 15 fps / pantalla una vez) sobre Baseline y VP9, teclas `80`..`83`,
   contador `oculto` (Chromium pausa el video mudo con la página oculta).
   **Falta solo la foto de la caja:** el operador corre **`80`** (≈ 2 min,
   incluye `blob:` + `blob concat` seguidos), `95` y foto; `83` a ojo mientras
   algo suena; y dice si volvió el símbolo de play. Lectura: si `capa1`/`capa2`
   caen dentro del gate como `capa0` → **encima** (DISENO §9); si no → **al
   lado**. Publicado en `v0/` (una key) con copia previa en `deploy/`.
4. **La caja consagra por decisión manual del operador** (VISION §8.11 lo
   prevé): lo sostenido en ella queda consagrado; la PC, cuando se pruebe, es
   refutadora, no consagradora.
5. **H-12 EJECUTADA hasta la pantalla** (`0ce2cb4` → `9011fe7`, CI verde, publicada en
   `v0/`; REGISTRO «H-12 implementada hasta la pantalla»). `vgencache.js` =
   IndexedDB con pineo por contenido, poda, progreso, techo 10/25/50 MB y
   cuota; teclas **`84`** (guardar + desde caché + techo), **`85`** (desde
   caché, **la tecla de después de reiniciar**) y **`86`** (borrar); la
   cabecera del reporte dice `cache … guardadas N` al cargar. PC: desde caché
   **105 ms** Baseline / 324 ms VP9, 50 MB entran. **Falta la foto de la
   caja, en la misma visita de H-11:** `84` → `95` foto; **reiniciar**; `95`
   foto de la cabecera + `85` → foto. Lectura: `guardadas 2` tras reiniciar y
   arranque ≤ 1 s → persiste; «no está en la caché» → degradación a memoria
   por sesión; primera fila `QuotaExceededError` = techo.
6. **W-26 cerrada en código** (`522bdf8`): la raíz respeta
   `?renderer=canvas2d`; la raíz servida **no se republicó** (es más vieja que
   el repo ya antes del cambio: decisión del operador, con auditoría previa).
   **H-14 con evidencia de CI** (`0eb8dab`, workflow `emitir-v0` con
   `determinismo: true`): **causa establecida el 2026-09-02**: determinista en la misma máquina (9/9 pares idénticos), **distinto por CPU** (AMD 7763 = AMD 9V74 ≠ Intel; el pack publicado es el Intel) y **`cpu-independent=1` lo cura** (AMD 9V74 = Intel 8370C = Intel 8573C, +0,016 % de bytes). Falta la decisión del operador: adoptar la opción en la receta (recomendado) o redefinir el invariante 7

**Si llegan reportes de otros aparatos, van al REGISTRO antes que a cualquier
otra cosa**, transcriptos de la foto, nunca de memoria; y una fila nueva en
PLAN-DE-MEDICION §5.

---

**Lo vivo, en orden** (cuerpos en
[`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2; suposiciones y
refutaciones en [`EMISION-V0.md`](EMISION-V0.md)):

1. **H-9 — el pack v0, el primer video por suposición** (`tools/emit_pieces.py` +
   workflow): desde el máster `dcd6afb6…1632a`, cuatro piezas y un manifiesto —
   H.264 **Baseline** (el piso, DPB mínimo: sin B, `refs=1`, GOP cerrado 15),
   H.264 **Main** (el **detector de hardware vs. software**), **VP9** (banda y el
   camino que YouTube usa en Android TV), **VP9+alfa** (el personaje sin fondo
   con CPU ≈ 0) y `MANIFEST.tsv`. **CERRADA 2026-09-01** (run `33559631360`):
   VP9 pesa **53,8 % menos** que Baseline; Main **9,1 % menos** con idéntica
   estructura; y el Baseline de DPB mínimo cuesta **2,3× más bytes** que el
   `producto.mp4` de defaults —el DPB mínimo se paga en bitrate—. Fluidez: H-10.
2. **H-10 — reproducirlo y que él nos diga** (`frontend/v0.html`, ES5).
   **La TV box está medida (2026-09-01)**: reporte transcripto en el REGISTRO;
   fila en PLAN-DE-MEDICION §5; veredictos en EMISION-V0 §4.b. Faltan el ojo del
   operador (alfa; fluidez de VP9 y HLS-TS, que el contador no vio) y las otras
   clases de aparato — o su decisión manual de fijar la caja como clase que
   consagra. **Abierta, no bloquea.**
3. **H-13 — por dónde entra el paquete** (`frontend/v0.html` crece; **cero
   emisión nueva**): MSE con los segmentos CMAF ya publicados (S9), `init +
   segmentos` concatenados en un Blob (S10 — si se sostiene, el muxer del camino
   A es una concatenación), intercambio de orden (S12), bucle de 60 s, columna
   «congelados» para los caminos con contador ciego. **CERRADA 2026-09-01 noche
   con la foto de la caja: A = concatenación, B = MSE `sequence` (bucle e
   intercambio), `loop` progresivo refutado.**
4. **H-11 — la bifurcación de layout**: canvas de intervención encima del
   `<video>`, con tres cargas, sobre Baseline y VP9, contra la línea de base ya
   medida (S5). Decide **encima o al lado** para todo el producto.
5. **H-12 — caché**: XHR → `Blob` → IndexedDB → `blob:`, con pineo por contenido
   y techo medido. Vale **2,5 s de arranque** en la caja (E4). **EJECUTADA
   hasta la pantalla 2026-09-02** (`0ce2cb4` → `9011fe7`; teclas `84`/`85`/`86`; falta la
   foto de la caja antes y después de reiniciar).
6. **H-6 — matriz por bytes a igual look, con la fluidez como gate** (reorientada:
   en la caja la fluidez está saturada y el decodificador es hardware): VP9 ×
   fps variable por segmento × H.264 piso relajado × zonas estáticas × paleta
   4:2:0, emisión v1 con segmentos (WebM segmentado para VP9 → S11) y fila de
   referencia con los defaults. Cierra con **una receta por perfil**.
7. **H-7 — spec normativa** (`docs/SPEC-VGEN.md`): solo con H-13 y H-11
   cerradas y filas reproducidas en ≥2 clases de aparato (o decisión del
   operador); cierra las filas «gateadas» de
   [`DISENO-FORMATO-VGEN.md`](DISENO-FORMATO-VGEN.md) §10. **El manifiesto va en
   texto tabulado, nunca JSON** (el gate ES5 prohíbe `JSON`).
8. **H-8 — muxer ES5 + player híbrido mínimo:** lo que H-13 deje en pie
   (concatenador CMAF / alimentador MSE / playlist), solo con H-7 aprobada.
9. **H-14** (determinismo H.264 — **causa establecida el 2026-09-02**: determinista en la misma máquina (9/9 pares idénticos), **distinto por CPU** (AMD 7763 = AMD 9V74 ≠ Intel; el pack publicado es el Intel) y **`cpu-independent=1` lo cura** (AMD 9V74 = Intel 8370C = Intel 8573C, +0,016 % de bytes). Falta la decisión del operador: adoptar la opción en la receta (recomendado) o redefinir el invariante 7) y **W-26** (`?renderer=` en la
   raíz — **cerrada en código** `522bdf8`, raíz no republicada): independientes.
10. Externo: pedirle a la app de la caja que el WebView reporte el panel real
    (hoy da 3840×2160 sobre un panel de 1280×720 = 9× de píxeles regalados).

**H-1, H-2 y H-3 quedaron REEMPLAZADAS** por el debate de dirección (eran el
diseño del player híbrido, la investigación de emisión H.264 y el player mínimo),
y **H-4 y H-5 quedaron REEMPLAZADAS** por la corrección de método (eran la sonda
sintética y el banco como paso previo). Ninguno de esos IDs se reusa.

**El porqué de todo esto, medido en la caja real** (REGISTRO, DIAG-002/003,
2026-08-31..09-01):

- el player 100 % JS **no llega a 15 fps ahí** (FRAME p50 290 ms contra 66,7 de
  presupuesto; el cuello es CPU — `inflate` solo ya come el presupuesto — y la
  vista 1:1 solo mejora ~20 %); además el WebGL de esa GPU **no presenta**
  (pantallazos blancos; canvas2d limpio);
- el mismo producto decodificado a H.264 (`producto.mp4`: el `.asclv` máster
  `dcd6afb6…1632a` → 1280×720 @15, 4.130.240 B) *«reproduce muy bien»* por
  `<video>` con decodificador de **hardware** — y pesa **6× menos** que el
  `.asclv` (17 %) y 10,6 % del mp4 fuente.

**El máster no se reemplaza:** el `.ascl`/`.asclv` sigue siendo la verdad
determinista offline (paleta, trellis, look, byte-identidad). El formato nuevo
(`.vgen`, nombre fijado por el operador el 2026-09-01) **lo envuelve**: es lo que viaja. El player JS
queda como reproductor de escritorio y banco de verificación del máster: se
mantiene, no crece.

**Principio del operador (2026-08-31, sigue vigente):** los valores manuales
prevalecen sobre cualquier automatismo, y **la densidad se elige por clip** —
ahora **dentro** del paquete (vía Representations), sin cambiar la resolución
base del contenedor.

**Estado de fases: F0-F9 completas y verificadas (paradigma anterior; resúmenes
en [`ejecutados/`](ejecutados/README.md)); DIAG-002/003 cerradas con decisión;
abierta la fase H (H-0 y H-9 cerradas, H-1..H-5 reemplazadas, H-10 con la caja
medida, **H-13 cerrada, H-11 ejecutada hasta la pantalla —falta la foto de la caja—**); F10/F11/F8/DIAG-001 suspendidas.** El detalle: tabla
de tareas abajo.

**Receta de producto vigente (2026-08-31, S-4 cerrada):** defaults del workflow
`encode` + **`format=v3`** + **`tile=sweep`** + **`--cols 1280`** en extra —
1280×720 @15 fps graphic-hq, adaptive kmeans-oklab, dither off, zopfli, overlay=off,
`--palette-refit 5 --near-lossless 8 --cols 1280` →
**`dcd6afb6…1632a`** (24.458.884 B, 35,02 dB, **62,8 % del mp4 fuente**; el sweep
elige regional 32 con trellis espacial 16; ~1 h de runner, RSS 1,6 GB). Instalado en
`outputs/` y servido como raíz de iargen.com/player/ vía puntero CACHE-001. **Es el
máster de entrada de toda la matriz de emisión H-6.**

**Player EN PRODUCCIÓN** (infra propia, nada preexistente tocado): bucket R2 +
Worker `asciline-player`, ruta `iargen.com/player*`, espejo
`asciline-player.iargen.workers.dev`. **Copia de lo desplegado, en el repo:**
[`deploy/asciline-player/`](../deploy/asciline-player/README.md) — `worker.js` verbatim,
los archivos servidos y `MANIFEST.tsv` con las 71 keys. Subir clips o frontend SIN
redeploy: acuñar `UPLOAD_TOKEN` por la API, `PUT /__upload/<key>` con `x-upload-token`
+ `x-sha256` (R2 verifica el digest), verificar lo servido y **quemar** el token.
**Ningún token se persiste jamás** — por eso no hay workflow de publicación de frontend
(exigiría un secret de GitHub). Ojo: el worker desplegado **no tiene** autorización por
contenido, aunque `publish-player` la asuma; ese workflow no funcionaría hoy. Detalle:
[`ejecutados/2026-08-31-S7-resolucion-y-deploy-player.md`](ejecutados/2026-08-31-S7-resolucion-y-deploy-player.md).

## Cómo ver lo ya implementado (para no pisarse)

- **La sección «Tareas cerradas» de abajo** resume los carriles; las tablas completas
  (una fila por tarea con estado, commit y evidencia) están archivadas verbatim en
  [`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md).
  Si una tarea figura `cerrada`, no se re-implementa: se extiende.
- [`ejecutados/`](ejecutados/README.md): resumen operativo por fase o lote cerrado.
- [`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md): el porqué
  de cada decisión, por Instancia (append-only).
- Los SHA de todos los clips medidos: sección «Referencias de clips» al final.

## Procedencia del código

| Sesión | Fecha | Base de trabajo | Notas |
|---|---|---|---|
| planificación | 2026-08-27 | snapshot ZIP `ASCILINE-video-main` (referencias `archivo:línea` del runbook corresponden a este árbol) | auditoría, diseño INT-001, plan y runbook; sin cambios de código |
| implementación 1 | 2026-08-27 | mismo snapshot, git local `5493455` (baseline) | 8 tareas cerradas; parches en `entrega-2026-08-27/patches/`, aplicables con `git am` sobre el repo real |
| sincronización | 2026-08-27 | clon real en `Escritorio\\repo` (baseline == snapshot, verificado) | `git am` no se aplicó; los 22 archivos finales se escribieron directo en el árbol de trabajo. Historia por tarea preservada solo en los parches; el repo la recibe como un commit |
| implementación 2 | 2026-08-27 | clon real de GitHub, `906b010` | máquina sin Python/Node **a propósito**: la regresión se valida en GitHub Actions en cada push; commits directos a `main`, un commit por tarea |
| F6 (S-4) | 2026-08-30 | `main` en `ae5f574` (post-deploy del player) | arranca la revisión única de formato; orden elegido F6-1 → F6-3 → F6-2 → F6-4 (el barrido definitivo de tile corre sobre el codec v3 final) |
| fase H (H-0) | 2026-09-01 | clon de `ASCILINE-video` en `f89abcd` (cierre del diagnóstico DIAG-002/003) → repo nuevo `leoIglesias-hash/ASCILINE-hybrid` | historia completa preservada (`main` + `assets`); mismo modelo de trabajo (CI-only, commits directos a `main`) |
| fase H (debate + documentación objetiva) | 2026-09-01 | `main` de `ASCILINE-hybrid` en `8dae1e5` (H-0 cerrada, CI verde) | debate de dirección con el operador el mismo día: el alcance pasa a un **formato propio códec-agnóstico**. Se escriben `VISION-Y-OBJETIVOS.md`, `DISENO-FORMATO-VGEN.md` y `PLAN-DE-MEDICION.md`; H-1..H-3 quedan reemplazadas por H-4..H-8. Sin código |
| fase H (corrección de método) | 2026-09-01 | `main` de `ASCILINE-hybrid` en `0128309` (CI verde) | el operador frena la sonda sintética: hubiera fijado el formato contra una sola TV box. Se arranca **emitiendo** el pack v0 por suposición. Se escribe `EMISION-V0.md`, se reescribe `PLAN-DE-MEDICION.md`, H-4/H-5 quedan reemplazadas por H-9..H-12. Sin código |
| fase H (H-9 + herramientas + publicación) | 2026-09-01 | `main` de `ASCILINE-hybrid`, de `5ea6459` a `eef9e45` (CI verde en cada push) | **H-9 cerrada**: emisor `tools/emit_pieces.py` + workflow `emitir-v0`, pack v0 con los empaquetados HLS/DASH por remux, `frontend/v0.html` (una pantalla, sin scroll, mando numérico), `frontend/keypad.js` compartido y `frontend/ir.html` (lanzador autocontenido, va en otro servidor). Worker redesplegado dos veces (MIME de video + `Range`, y los tipos del carril segmentado), 60 keys publicadas y verificadas por SHA-256. Se abre **H-14**. Resumen: `ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md` |
| fase H (primer reporte de aparato + plan de implementación) | 2026-09-01 | `main` de `ASCILINE-hybrid` en `1f12044` (CI verde) | el operador manda la **foto del reporte de la TV box**; se transcribe textual al REGISTRO, se llena la fila de PLAN-DE-MEDICION §5 y el veredicto por suposición (EMISION-V0 §4.b, nuevas S9..S12 en §4.c). Se escribe **`PLAN-IMPLEMENTACION-VGEN.md`** (rumbo: evidencia, caminos, gates, orden H-13 → H-11 → H-12 → H-6 → H-7 → H-8, decisiones pendientes) y se abre **H-13**. Sin código |

> Al iniciar cada sesión de implementación: agregar una fila con el commit o snapshot
> sobre el que se trabaja. Si el árbol cambió desde el 2026-08-27, localizar las
> referencias por nombre de función, no por número de línea.

## Tareas abiertas (fase H, plan del 2026-09-01)

Una fila por tarea (regla 1). El cuerpo de cada una —archivo, acción, criterio de
cierre— está en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2.

| ID | Fase | Qué | Estado | Δbytes |
|---|---|---|---|---|
| H-0 | H | repo `ASCILINE-hybrid` + docs reorganizadas al paradigma mp4/híbrido | **cerrada 2026-09-01** (`8dae1e5`) | no |
| H-1..H-3 | H | (diseño del player híbrido / emisión H.264 / player mínimo) | **reemplazadas 2026-09-01** por el debate de dirección; absorbidas al pasar el alcance a «formato propio». IDs no reusables | — |
| H-4, H-5 | H | (sonda sintética de capacidades / banco como paso previo) | **reemplazadas 2026-09-01** (misma tarde) por decisión del operador: hubieran fijado el formato contra **una sola TV box**. Disueltas dentro de H-9/H-10. IDs no reusables | — |
| H-9 | H | **pack v0 — el primer video, por suposición** (`tools/emit_pieces.py` + workflow `emitir-v0`): 4 piezas + `hls-ts/`, `hls-fmp4/`, `dash/` por remux, y `MANIFEST.tsv` | **cerrada 2026-09-01** (run `33566441576` verde). Resumen: [`ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md`](ejecutados/2026-09-01-H9-pack-v0-y-herramientas.md); SHAs abajo en «Referencias de clips» | sí (piezas nuevas) |
| H-10 | H | **reproducirlo y que él nos diga** (`frontend/v0.html` + `keypad.js`): cuál arrancó de verdad, cuadros caídos, arranque, deriva, alfa, `blob:`, HLS/DASH, panel real — en la caja **y** 2-3 aparatos más | **en curso — la TV box está medida (2026-09-01)**: reporte transcripto en el REGISTRO, fila en PLAN-DE-MEDICION §5, veredictos en EMISION-V0 §4.b. Faltan el ojo del operador (alfa; VP9 y HLS-TS con contador ciego) y las otras clases, o su decisión manual. **No bloquea** | no |
| H-13 | H | **por dónde entra el paquete** (`frontend/v0.html` crece, cero emisión nueva): MSE con los segmentos CMAF publicados (S9), `init + segmentos` concatenados en un Blob (S10), intercambio de orden (S12), bucle de 60 s, `changeType`, columna «congelados», «atascos» sin el `waiting` inicial, fila «contador ciego» | **CERRADA 2026-09-01 noche** (`85eebd1`→`b3d5837` código, `0589dc9` docs; publicado en `v0/`; foto de la caja en el REGISTRO «H-13: reporte de la caja»). S9 consagrada, S10 en dos clases (muxer A = `concat()`), S12 por MSE `sequence` sí / por Blob no («se tilda»), bucle por `loop` refutado, cambio a demanda 305 ms a VP9 y 1.468/1.180 a Baseline. Camino del muxer escrito en el plan | no |
| H-11 | H | **la bifurcación de layout**: canvas de intervención **encima** del `<video>`, con tres cargas, sobre Baseline y VP9, contra la línea de base medida (suposición S5) | **EJECUTADA hasta la pantalla** (`fd9a7ab`, CI verde, publicada en `v0/`); cierra con la foto de la caja (`80` + `95`) | no |
| H-6 | H | **matriz por bytes a igual look, con la fluidez como gate** (reorientada por el reporte): VP9 × fps variable por segmento × H.264 piso relajado × zonas estáticas × paleta 4:2:0; emisión v1 con segmentos (WebM segmentado para VP9 → S11) + fila de referencia con los defaults | pendiente (precondición: H-13, H-11) | sí (variantes) |
| H-12 | H | **caché**: XHR → `Blob` → IndexedDB → `blob:`, con pineo por contenido, borrado de claves viejas y techo medido (10/25/50 MB). Vale 2,5 s de arranque en la caja | **EJECUTADA hasta la pantalla 2026-09-02** (`0ce2cb4` → `9011fe7`, CI verde, publicada en `v0/`); cierra con la foto de la caja antes y después de reiniciar (`84` + `95`, reinicio, `95` + `85`) | no |
| H-7 | H | **spec normativa `SPEC-VGEN.md`**: contenedor, manifiesto (texto tabulado, **no JSON**), segmentos, sprites, cues, huecos, perfil → camino de runtime | pendiente (precondición: H-10, H-11, H-6) | define bytes |
| H-8 | H | **muxer ES5 + player híbrido mínimo** (incluye «cambiar solo la música») | pendiente (precondición: H-7) | no |
| H-14 | H | **determinismo del carril H.264** (deuda contra el invariante 7): dos corridas dieron Baseline +22 B y Main −74 B con **misma ffmpeg y mismas opciones de x264**; VP9 salió byte-idéntico. Separar «no determinista» de «depende de la máquina» | **en curso 2026-09-02** (`0eb8dab`: workflow con `determinismo: true` + `--x264-extra`; **causa establecida el 2026-09-02**: determinista en la misma máquina (9/9 pares idénticos), **distinto por CPU** (AMD 7763 = AMD 9V74 ≠ Intel; el pack publicado es el Intel) y **`cpu-independent=1` lo cura** (AMD 9V74 = Intel 8370C = Intel 8573C, +0,016 % de bytes). Falta la decisión del operador: adoptar la opción en la receta (recomendado) o redefinir el invariante 7) | define bytes |
| W-26 | — | escape `?renderer=` en la raíz publicada + default para TV box | **cerrada en código 2026-09-02** (`522bdf8` → `730c5f4`, CI verde): la raíz respeta `?renderer=canvas2d`; la raíz servida no se republicó (REGISTRO) | no |

**Suspendidas por el cambio de dirección (2026-09-01)** — recuperables verbatim de
[`historico/RUNBOOK-IMPLEMENTACION-asclv-js.md`](historico/RUNBOOK-IMPLEMENTACION-asclv-js.md)
solo con decisión del operador: E-25..E-28 (F10), E-30/E-31/F11-1..5 (F11),
F8-1..5 (validación física del player JS), DIAG-001, y las opcionales
E-11/W-15/W-21/E-29. Nota para si se retoma F10: el mp4 hereda los píxeles del
`.asclv`, así que la calidad del máster (anti-banding) sigue teniendo efecto en
el producto híbrido.

## Tareas cerradas (archivadas 2026-08-31)

Las tablas completas de tareas cerradas (una fila por tarea con commit, fecha y
notas técnicas, **verbatim**) se archivaron en
[`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md)
para mantener corto este archivo. Regla intacta: si una tarea figura `cerrada`, no se
re-implementa — se extiende. Resumen por carril:

| Carril | Tareas | Estado | Resumen en ejecutados |
|---|---|---|---|
| Preparación | P-01..P-04 | cerradas 2026-08-27 | [`F0`](ejecutados/2026-08-27-F0-base-congelada.md) |
| E — encoder | E-01..E-24 (E-11 **opcional**, pendiente) | cerradas 2026-08-27..30 | [`F0`](ejecutados/2026-08-27-F0-base-congelada.md) · [`F1`](ejecutados/2026-08-27-F1-paleta-reservada-glifos-sidecar.md) · [`F2`](ejecutados/2026-08-28-F2-compresion-e08-10.md) · [`F3`](ejecutados/2026-08-29-F3-carril-calidad.md) · [`F5`](ejecutados/2026-08-30-F5-trellis-near-lossless.md) |
| W — frontend | W-01..W-14 (W-15 **opcional**, pendiente) | cerradas 2026-08-27..28 | [`W-01..05`](ejecutados/2026-08-27-W01-05-frontend.md) · [`F4`](ejecutados/2026-08-28-F4-frontend-w06-14.md) |
| F7 — runtime overlay (S-5) | F7-1..F7-4 + integración | cerradas 2026-08-28 | [`F7`](ejecutados/2026-08-28-F7-runtime-overlay.md) |
| INT-003 — parches genéricos | A..F | cerradas 2026-08-28 | [`INT-003`](ejecutados/2026-08-28-INT-003-parches-genericos.md) |
| INT-004 — texto nativo | A..B | cerradas 2026-08-28 | [`INT-004`](ejecutados/2026-08-28-INT-004-texto-nativo.md) |
| INT-006 — fondo sin reserva | A..C | cerradas 2026-08-28 | [`INT-006`](ejecutados/2026-08-28-INT-006-fondo-sin-reserva.md) |
| INT-007 — tipografía + logo giratorio | A..B | cerradas 2026-08-29 | [`F5`](ejecutados/2026-08-30-F5-trellis-near-lossless.md) |
| F6 — formato v3 (S-4) | F6-1..F6-4 | cerradas 2026-08-30..31 | [`F6`](ejecutados/2026-08-31-F6-formato-v3-S4.md) |

## Sincronización y fases finales

| ID | Qué | Estado | Fecha | Notas |
|---|---|---|---|---|
| S-1 | merge de F0 | cerrada | 2026-08-27 | historial lineal en el snapshot; equivale al merge |
| S-2 | habilitar artefactos `tile_size` ≠ 16 | cerrada | 2026-08-27 | W-08 en verde: `ReaderV2` abre los seis tamaños; E-09 puede generar artefactos |
| S-3 | desbloquear E-10 | cerrada | 2026-08-28 | W-02 estaba en verde desde la sesión 1; E-10 ejecutada y cerrada |
| S-4 | revisión única de formato (F6) + barrido definitivo de `tile_size` | cerrada | 2026-08-31 | F6-1/2/3/4 cerradas (Carril F6) y acto de cierre ejecutado: producto **1280@15 v3 tile=sweep** = `dcd6afb6…1632a` (24.458.884 B = 62,8 %, 35,02 dB, run 33352859235; sweep eligió regional 32/espacial 16 también a 1280), instalado en `outputs/` y publicado como raíz de iargen.com/player/ (puntero CACHE-001, reproducción v3 verificada en navegador). v3 ADOPTADO como formato de producto |
| S-5 | runtime del overlay (F7) | cerrada | 2026-08-28 | F7-1..F7-4 + integración en verde; gates de INT-002 cubiertos por la regresión (Instancia 014). Los dos gates físicos (costo p95 y MEM-001 en TV) se miden en F8-2/F8-4, donde el plan ya los prevé con y sin overlay |
| S-6 | validación física (F8) | **suspendida** (cambio de dirección 2026-09-01) | | era la validación del player JS en TV; el híbrido tendrá la suya (H-3) |
| S-8 | **F9 — aceleración del frontend** (W-16..W-25) | cerrada | 2026-08-31 | medida y publicada (28 keys). Diseño archivado: [`historico/DISENO-RENDER-INDEXADO.md`](historico/DISENO-RENDER-INDEXADO.md) |
| S-9 | **F10 — pérdida adaptativa por suavidad** (E-25..E-28) | **suspendida** (cambio de dirección 2026-09-01) | | diseño archivado: [`historico/DISENO-PERDIDA-ADAPTATIVA.md`](historico/DISENO-PERDIDA-ADAPTATIVA.md); si se retoma sigue valiendo — el mp4 hereda los píxeles del máster |
| S-10 | **F11 — formato v4: LOD por tile + transparencia** (E-30, F11-1..5) | **suspendida** (cambio de dirección 2026-09-01) | | diseño archivado: [`historico/DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](historico/DISENO-FORMATO-V4-LOD-Y-ALPHA.md); su motivación principal (aliviar el decoder JS) desapareció con el híbrido |
| H | **fase H — formato propio híbrido** (H-0, H-9..H-14, H-6..H-8, W-26) | en curso | 2026-09-01 | H-0 cerrada (nace este repo). **H-1..H-3 reemplazadas** por el debate de dirección (el alcance pasó a «formato propio códec-agnóstico») y **H-4/H-5 reemplazadas** la misma tarde: la sonda sintética hubiera fijado el formato contra una sola caja, así que se arranca **emitiendo** (pack v0). Norte: [`VISION-Y-OBJETIVOS.md`](VISION-Y-OBJETIVOS.md); el primer video: [`EMISION-V0.md`](EMISION-V0.md); método: [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md); cuerpos en [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md) §2 |
| S-7 | barrido de resolución 768 → 1280 → 1920 con el stack completo | cerrada | 2026-08-31 | Instancia 028: tres escalones aprobados a ojo; **producto = 1280 @15 fps** (`2a9201bf…b778`, 63 % de la fuente; el 1920 descartado por fluidez a 10 fps, no por imagen — vuelve a más fps como prueba futura y el front debe procesar cualquier resolución). Hallazgo central: la tasa por celda CAE al subir resolución (0,1451 → 0,1144 → 0,1023 B/celda/frame). Re-encode del producto diferido al cierre de S-4 (v3 + tile ganador) |

## Referencias de clips (SHA-256)

Todos los clips medidos, del vigente al histórico. «Reproducible» = re-encodear desde
`main` con esos flags devuelve ese SHA byte a byte (regla 5, verificada — nunca supuesta).

**Pack v0 (H-9, 2026-09-01, run `33566441576`)** — emitido del máster vigente con
`tools/emit_pieces.py`, publicado en `https://iargen.com/player/v0/`:

| Pieza | Bytes | SHA-256 |
|---|---:|---|
| `v0-h264-baseline.mp4` | 9.551.715 | `cf927d578ab993d468ada2cd2440d9a18b030a343e23ef5008ed39912ef04fdc` |
| `v0-h264-main.mp4` | 8.686.438 | `b9b1e1f542fe4f10ff44dc53f6eb2a297bcff9e357d9c277068a088e72451890` |
| `v0-vp9.webm` | 4.411.693 | `5be4650747fd511aa0b54b493c3a9a1d7c24f15c630ba7d22fc1acf42543830b` |
| `v0-vp9-alpha.webm` | 4.664.676 | `2b1fe6c3bfdee0cd0d3d07acec80bdcff3d877070ca839f21cbceccbbc76bc6c` |

**Ojo con «reproducible» acá:** VP9 y VP9+alfa **sí** salieron byte-idénticos entre
dos corridas; las dos piezas de H.264 **no** (Baseline +22 B, Main −74 B, con la
misma ffmpeg y las mismas opciones de x264). Es la deuda **H-14**, abierta por
evidencia y no por sospecha.

**Producto vigente (S-4/S-7 cerradas, 2026-08-31): 1280 @15 fps, formato v3,
tile=sweep (espacial 16 + regional 32) = `dcd6afb6…1632a`**
(`dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a`, 24.458.884 B =
**62,8 % del mp4 fuente**, 35,02 dB, Oklab 0,00901, err_temporal 0,00713,
proxy_banding 0,001522, run 33352859235, wall 59:54, RSS 1,6 GB; instalado en
`outputs/` con SHA verificado y publicado en iargen.com/player/ vía puntero
CACHE-001; reproducible con los defaults del workflow + `format=v3` + `tile=sweep`
+ extra `--palette-refit 5 --near-lossless 8 --cols 1280`).

Producto anterior 768 (near-lossless 8, v2 tile 16): `b081f4ba…f6a05e` (11.304.137 B,
35,10 dB, Oklab 0,00897, err_temporal 0,00705, proxy_banding 0,001587, run
33321490398, reproducible con los defaults pelados del workflow). Su transcodificación
v3 tile 32 (F6-2): `6f28a459…8784` (bundle 11.261.986 B, misma calidad, byte-idéntica
en dos runs) · diagonal espacial-32 `8b5d0f1e…e738` (11.276.362 B, peor, descartada).

Barrido S-7 (Instancia 028, cerrada): 1280@15 v2 `2a9201bf…b778` (24.530.460 B,
35,02 dB, run 33325334610 — antecesor directo del producto vigente) · 1280@12
`27ae0019…e828` (21.196.032 B, 34,95 dB, run 33326623591) · 1920@10 `87160987…8d4e`
(32.838.265 B, 34,81 dB, run 33333170964).

Candidatos y filas históricas: near-lossless 6 `db32e8c4…2157` (11.951.807 B, 35,37 dB)
y 5 `157bccf0…4c44` (12.339.798 B, 35,48 dB), no elegidos · near-lossless 4
`5a45592b…92d0` (12.840.889 B, ≈ producto temporal 4) · temporal 4 `221de28f…0373`
(12.846.465 B, 35,59 dB, tres runs byte-idénticos, producto anterior — reproducible con
`extra = --palette-refit 5 --trellis-temporal 4`) · temporal 2 `63fb7aae…adde`
(14.315.422 B, 35,75 dB, aprobado y superado el mismo día) · temporal 10 `5db38f9d…`
(10.778.521 B, 34,81 dB, descartado) · espacial 8/16 `28edb2ad…`/`c84dfe92…`
(Instancia 026, sin adopción en solitario) · base E-21 sin trellis `41c94170…79d5`
(17.170.673 B, 35,63 dB, dos runs byte-idénticos, reproducible con
`extra = --palette-refit 5`) · sin dither pre-E-21 `74be25ef…011f9` (17.168.633 B, fila
histórica: el emisor cambió con E-21 y ya no se reproduce desde main) · tramado refit 5
`adef9e53…c05bb` (17.379.859 B, 35,46 dB, reproducible con dither=auto) · dither budget
450 `aabd518a…8bf6` (17.246.050 B, descartado) · budget 0 `909ba629…f68e` (descartado:
41 B más que `off` y 4:43 más lento) · refit 5 + uint8-refine 3 `a95d0bbc…acbf`
(E-13 medido sin adoptar) · refit 3 `514be81e…a01aff` · dither exacto E-16
`0ed4cbbe…92f5` (medido sin adoptar) · P-02 sin refit `ebfe2eb4…4b36` (17.482.270 B,
reproducible con el flag en 0) · ultra 960 sin refit `31348a83…5688` (25.003.004 B,
superado; re-medir con refit 5 si se retoma) · panel v1 `7da584f1…5a51d` · parches v2
`c315a13a…8e63` + sidecar `678b392d…2c56` (demo INT-003/004). Los detalles de cada fila
están en el REGISTRO, por Instancia.

**Byte-identidad, historia** (regla 5): los runs 33220236164 (post-E-16), 33233492257
(post-E-18) y 33235096580 (post-E-19/E-20) reprodujeron byte a byte `adef9e53…c05bb`;
la Instancia 027 reprodujo `41c94170…` y `221de28f…` con el emisor post-E-24. Desde
E-21 el SHA de producto se movió **a propósito** (Instancia 024). Regresión vigente:
**342 pruebas Python (327 + 12 de F6-3 + 3 de F6-4) y 27 suites JavaScript**
(+`test_v3_cross`; CI verde de `6fd23b6`).

## Bitácora de decisiones de ejecución (historial append-only)

> Esta sección es historial: se agrega al pie, nunca se relee entera. Las filas del
> 2026-08-27 al 2026-08-30 se archivaron verbatim en
> [`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md);
> las decisiones nuevas se siguen anotando ACÁ, al pie de esta tabla.

| Fecha | Decisión | Motivo |
|---|---|---|
| 2026-08-31 | **F6-2 cerrada con los runs A/B del barrido 2D** (Instancia 029): run A (33350852865, espacial 16 + sweep regional) reprodujo **byte a byte** el `6f28a459…8784` del sweep original — regla 5 verificada también para el pipeline v3 completo — y run B (33350856477, espacial 32 + sweep regional) reprodujo el `8b5d0f1e…` del acoplado-32, confirmando que esa diagonal es la misma configuración y que es PEOR (+14.376 B). Ganador global: **espacial 16 + regional 32** (bundle 11.261.986 B = −0,37 % vs producto 768 v2, calidad idéntica). Decisión de receta: la config mixta se pinnea con `tile=sweep` (la elección del sweep es determinista) en vez de agregar un flag que decouple los dos ejes — cero código nuevo y el sweep documenta la elección en el log | con la fila de F6-2 la adopción de v3 quedó decidida y **el acto de cierre de S-4 se despachó en el momento**: run 33352859235 = encode único del producto 1280@15 (S-7) en `format=v3` + `tile=sweep` + extra `--palette-refit 5 --near-lossless 8 --cols 1280`. Al terminar: fila en el REGISTRO, instalación en `outputs/` y publicación al player con puntero CACHE-001 |
| 2026-08-31 | **S-4 CERRADA — v3 adoptado y el producto pasa a 1280@15 v3** (`dcd6afb6…1632a`, run 33352859235, wall 59:54, RSS 1,6 GB): el sweep a 1280 eligió el MISMO ganador que a 768 (regional 32, espacial 16, 58.456 tiles fusionados), y el v3 le ganó 71.576 B a su antecesor v2 `2a9201bf…` con calidad idéntica (35,02 dB). Instalación y publicación en el mismo acto: `outputs/` (clip + versionado + puntero) y subida al player raíz por la vía manual (token rotado vía API, 3 PUTs con `x-sha256` verificado por R2 — clip immutable + puntero + fallback `clip.asclv` actualizado —, token quemado con un valor aleatorio no registrado). Verificación en producción: puntero → `clip.dcd6afb66907.asclv` (Content-Length 24.458.884, immutable 1 año) y reproducción real en navegador (badge `ASCL v3 1280x720 @15fps`, frames avanzando, logo INT-007 girando) | primer v3 en producción: cierra S-4 con UNA sola versión nueva de decoder desplegada y el criterio del operador cumplido (su 1280@15 elegido en S-7, ahora 62,8 % de la fuente). Los subplayers 1280-15/1280-12/1920-10 conservan sus clips v2 como variantes; el operador puede comparar v2 vs v3 en el mismo dominio. Sigue F8 (TV físico) |
| 2026-08-31 | **Plan nuevo: F9, F10, F11 y DIAG-001** (Instancia 030). Auditoría completa del encoder, del frontend y del historial de ideas para no repetir lo descartado; el operador aprobó cuatro carriles y agregó uno. **F9** (front, sin tocar bytes): la conversión índice→RGBA cuesta ~14,5 M accesos por keyframe a 1920 y sube 8,3 MB — se ataca con LUT `Uint32`, textura de índices con lookup en el shader, reconstrucción de 4 taps y pacing. **F10**: la pérdida se reparte hoy en partes iguales, cuando el banding solo se ve en zonas suaves; se modula por el mapa de suavidad que ya existe y no se usa fuera del K-means. **F11**: LOD por tile (gana bytes **y** trabajo del decoder a la vez) y **transparencia** (feature nueva pedida por el operador), agrupadas en una sola revisión de formato v4. **DIAG-001** (escalado del huevo) queda **al final** por decisión explícita del operador | orden F9 → F10 → F11 → F8 → DIAG-001: F9 primero porque su ciclo de prueba dura minutos contra el clip ya publicado, en vez de una hora de runner. Se agrega el principio de que resolución y fps son elegibles **por video**, nunca fijados por receta (extiende la regla 9). Tres documentos de diseño nuevos; ninguna tarea empieza sin su medición (W-16 es precondición dura de F9) |
| 2026-08-31 | **Limpieza de documentación post-cierre** (pedido del operador: «ordená y limpiá manteniendo el historial, perdiendo lo mínimo posible»): las tablas completas de tareas cerradas (P/E/W/F7/INT-003..007/F6) y las filas de bitácora 2026-08-27..30 se movieron **verbatim** (extracción por rangos de línea, no transcripción) a `ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`; el estado quedó con lo vivo + resumen por carril + referencias de clips intactas (376 → ~180 líneas). El runbook de implementación perdió S-4/F6 y S-7 (cerradas) y quedó solo con F8 + opcionales; se agregó el ejecutado faltante de S-7 + deploy del player; índices y CLAUDE.md al día | cero pérdida: movido, no borrado — la evidencia canónica sigue siendo REGISTRO + ejecutados/; mismo patrón que la poda del 2026-08-30. Las «Referencias de clips» NO se archivan: son consulta activa (regla 5) |
| 2026-08-31 | **Revisión del plan + dos ideas nuevas anotadas para v4** (Instancia 031): el operador pidió el parecer sobre los diseños y una idea más. Se anotaron (a) **frames de solo-paleta** (E-31 análisis sin formato → F11-5 condicionada: fundidos/flashes como transformada de paleta, ~800 B por frame en vez de cientos de KB) y (b) **paletas por región** (idea del operador: N paletas de 256 con selector por tile, partición sin superposición — la región rica es dueña exclusiva de sus tiles y el fondo queda hueco debajo; gate: saturación real de las 256 en E-25). Descartado el salto a paleta de 512 (rompe el byte por celda: reescribir todos los opcodes, +30-70 % de bytes, doble subida). Ajustes de detalle cableados: E-30 excluye rampas suaves con el mapa de E-25; E-26 se mide contra el producto post-E-27; W-20 pre-decodifica **solo** keyframes | las dos ideas quedan con gate explícito para no relajar canonicidad ni cambiar formato «por si acaso»; lo medido sigue atribuyendo el escalonado a trellis (F10) y estirado fraccionario (W-19), no a falta de colores. El plan de ejecución no cambia: arranca W-16 |
| 2026-08-31 | **W-16 cerrada: F9 ya tiene banco** (Instancia 032, commit `f1ccfa3`, CI verde). `tools/bench_render.js` mide la conversión índice→RGBA sobre tres grillas × tres perfiles y compara el camino de bytes vigente contra el prototipo LUT `Uint32`; `frontend/diagnostic-player.html` (**F8-1 adelantada**) desglosa inflate/walk/RGBA/blit por frame con p50/p95, drops y tarde. Medición: keyframe a 1920 = **11,0 ms de pura conversión** en runner de CI; la LUT da **1,3×–3,3×** (≈2,2× en keyframe y tiles densos). Paridad byte a byte verificada en los 9 casos | el banco **publica** la tabla y **no** juzga tiempos (el runner comparte CPU: sería un test intermitente); lo que falla el CI es la paridad. La instrumentación vive entera en la página de diagnóstico, envolviendo métodos de la instancia: ningún archivo de producción se modifica para medir, así que lo medido es lo que corre en el TV. W-17 queda justificada con números antes de escribirse |
| 2026-08-31 | **W-17 cerrada: LUT `Uint32` en los dos readers** (Instancia 033, commit `8cecc7b`, CI verde). Medido con `bench-render` HEAD vs baseline `f1ccfa3` **en la misma corrida**: keyframe a 1920 **11,4 → 5,7 ms** (2,0×), tiles densos 6,2 → 3,3 (1,9×), disperso 1,14 → 0,85 (1,33×). Salida **byte-idéntica**, verificada corriendo los dos caminos sobre el mismo reader y el mismo frame | el destino es el selector del camino (vista `Uint32` alineada → palabra; Array plano o desalineado → bytes), y eso hace que la paridad sea comprobable sin duplicar corpus. La LUT se cachea por identidad de paleta, no por frame. El disperso gana poco porque el costo dominante es barrer todo `dirtyCellBits`: es el argumento para que **W-21 deje de ser opcional** |
| 2026-08-31 | **W-18 + W-19 implementadas** (Instancia 034, commit `07a94e2`, CI verde): en PIXEL la GPU recibe los **índices** (`LUMINANCE`) y la paleta como textura 256×1; el lookup y la mezcla de 4 taps viven en el shader. Verificado con **contexto WebGL real**: `paridad GL/2D: OK (delta max 0, camino indexado)` y etapa `rgba` en **0,00 ms** con el clip de producción. Decisión tomada acá, que el diseño no fijaba: en `soft` el **backing store sigue al tamaño de presentación** (si midiera lo mismo que la grilla, la mezcla sería un no-op y el estirado lo seguiría haciendo el compositor) | los tres modos de fallar en silencio quedaron con test: `UNPACK_ALIGNMENT` en 1, medio texel al indexar la paleta y `highp` con caída a `mediump`. La textura de índices **nunca** se filtra con LINEAR. **W-19 no se marca cerrada**: su criterio es el veredicto visual del operador en el TV, y eso no lo puede firmar nadie más |
| 2026-08-31 | **W-20 implementada, F9 con todo su código escrito** (Instancia 035, `798203a` + `1cb0e38`, CI verde). (a) La fase de presentación avanza con el reloj del **display** y se corrige lento contra el audio, que sigue siendo el maestro; un desvío > 2 cuadros resincroniza de una. (b) El próximo **keyframe** se decodifica en el tiempo muerto y se adopta **intercambiando readers**, no copiando celdas. Las dos piezas se apagan con `?pacing=off` y `?predecode=off` | el «buffer alterno de `cells`» del diseño terminó siendo un segundo reader sobre los mismos bytes: cada uno queda internamente consistente, así que no hubo que abrirle a la maquinaria dirty un modo fuera de línea ni tocar el invariante 4. Cuesta otro `cells` (2 MB a 1920) → **anotado para MEM-001**. El CI falló una vez por una aserción que exigía un bloque de texto **contiguo**: se reescribió por contenido y orden, que es lo que la propiedad realmente dice |
| 2026-08-31 | **Ruido reportado a ojo por el operador → dos defectos reales, y W-19 cerrada** (Instancia 036, commit `af6bfff`, CI verde). El CI estaba en verde y aun así había ruido en pantalla: (a) `_drawIndexed` cacheaba la vista de la banda sucia **solo por rango de filas**, así que tras un intercambio de readers de W-20 subía a la GPU las celdas del **reader anterior** (franjas con imagen de otro momento, a la cadencia de los keyframes); (b) la mezcla de 4 taps de `soft` necesita la fracción de una coordenada de hasta ~1920 texeles, imposible en `mediump`, y la caída a `mediump` era un fallback de compilación: el shader compilaba y dibujaba basura. Ahora la clave del cache incluye el **origen** del buffer y `soft` exige `highp` real (`getShaderPrecisionFormat`), si no dibuja `nearest` y el HUD lo avisa. Con eso puesto el operador vio «se ve igual» en `nearest` **y** en `?rec=soft`, y `paridad GL/2D: OK` en el navegador de su PC | dos lecciones que valen más que el arreglo: cachear por **rango** una vista sobre un buffer reemplazable es un alias silencioso —la identidad del buffer es parte de la clave—, y una caída de precisión es un fallback válido para **compilar** pero una fuente de basura para **calcular**. Consecuencia de producto: si el operador no distingue 4 taps de 1 tap, no se paga → **default `nearest`**, `soft` disponible por video. El `1280 soft` vs `1920` en TV se mueve a **F8**, que es la fase de TV físico; mantenerlo como bloqueo de F9 sería pedirle a esta fase un gate de la siguiente |
| 2026-08-31 | **W-20 cerrada con medición del operador en pantalla real** (Instancia 037). Clip de producción, `1280x720@15 · webgl/nearest · pacing on`, 497 presentaciones: **p95 de decode+render 14,90 ms contra 66,7 de presupuesto (22 %), drops 0, tarde 0**, `paridad GL/2D OK delta max 0`. Con W-19 cerrada el día anterior por veredicto visual, **F9 queda con todas sus tareas medidas** y su único pendiente es publicar el frontend | tres confirmaciones que valen más que el total: (a) `rgba` marcó **0,00 ms con el clip real** — W-18 no era efecto de banco, la conversión índice→RGBA desapareció del presupuesto; (b) `pre-key` marcó p95 **14,10 ms**, casi un frame entero, **con 0 drops**: el pre-decode corre en tiempo muerto como se diseñó, y publicarlo en fila aparte fue lo que permitió verificarlo en vez de suponerlo; (c) **el cuello de botella se movió a `inflate`** (8,70 de los 14,90 del frame, ~58 %) — después de W-17/W-18 lo caro es descomprimir, no convertir ni dibujar, y eso ordena cualquier optimización futura (`W-21` toca `walk`, ya en 3,20). Lo que la medición NO dice: es GPU de PC a 1280@15, no un TV; la holgura de 4,5× es justo el margen que **F8** debe confirmar |
| 2026-08-31 | **Frontend de F9 publicado, y directiva del operador sobre qué es una actualización** (Instancia 038). El operador fijó: «**no deberíamos perder cosas con las actualizaciones, porque son eso, actualizaciones; deben ser mejoras de lo que ya tenemos**», y además: guardar en el repo lo vivo de Cloudflare **antes** de tocarlo, y publicar con las herramientas ya cargadas en vez de pedirle pasos manuales. Se hizo primero la copia (`deploy/asciline-player/`: `worker.js` verbatim —**no existía fuera de Cloudflare**—, los 15 archivos servidos con sus `md5` iguales a los `etag` de R2, y `MANIFEST.tsv` con las 71 keys) y después la subida de 24 keys, las 24 verificadas byte-idénticas al repo; los 11 archivos no tocados conservan su `md5` | las dos directivas corrigieron el rumbo: yo proponía reemplazar el `live-player.html` publicado por `tv-player.html` (habría borrado overlay, textos y datachannel) y una ruta por CI con un secret pegado a mano. El manifiesto además desmintió al MAPA: **`index.html` ES `live-player.html`** en las 4 carpetas, y `tv-player.html` no estaba publicado en ninguna key; las variantes tienen copias byte-idénticas del código, así que toda actualización va a las 4 carpetas. Token efímero acuñado por API y **quemado** después (viejo → 403); el workflow `publish-frontend` se descartó y borró porque exigía persistir un secret. Consecuencia abierta: la raíz ganó W-17/W-18 pero **no W-20**, que vive en otra página → se porta, no se reemplaza |
| 2026-08-31 | **CI BLOQUEADO POR FACTURACIÓN DE GITHUB, no por código.** El commit `5fdfade` (solo docs) falló con los tres jobs muertos **a los 2 segundos y sin ejecutar ningún paso**. La anotación del run lo dice literal: «The job was not started because recent account payments have failed or your spending limit needs to be increased». El último commit que sí corrió y quedó **verde es `45122df`**, que ya incluye todo el código de F9 y la publicación | esto **frena el modelo de trabajo entero**: la regla es que una tarea cierra solo con CI en verde, y esta máquina no tiene Python ni Node para validar local. Mientras no se resuelva el límite de gasto en «Billing & plans», ningún cambio de código se puede dar por cerrado — se puede escribir, no verificar. Acción del operador, fuera del repo. Diagnóstico: los jobs sin pasos y con 2 s de duración son arranque fallido, no test roto; la anotación vive en `check-runs/<job>/annotations`, no en los logs (que vuelven vacíos) |
| 2026-08-31 | **Un solo motor de reproducción para las cuatro páginas** (Instancia 039, `3c46d3d` + `2753fd1` + `26b4170` + `1fe95a9`, **sin CI: sigue bloqueado**). El operador pidió «fusionar los backgrounds del front para que todos los reproductores tengan todas las mejoras». La cadencia y el pre-decode de W-20 estaban **copiados** en `tv-player.html` y en `diagnostic-player.html`, y **ausentes** en `live-player.html` —que es lo que sirve la raíz publicada— y en `player.html`. Se extrajo la maquinaria a `frontend/playloop.js` (W-22, con `tests/test_playloop.js`), se pasaron las dos páginas que la tenían (W-23) y la estrenaron las dos que no (W-24). Además W-25: el gate ES5 descartaba un `<script>` si la **coincidencia entera** contenía `src=`, así que un `var src=DEFAULT_SRC;` bastaba para que `player.html` y `diagnostic-player.html` no se analizaran nunca | tres cosas que la fusión hizo posibles y la copia impedía: (a) la raíz **por fin** tiene la cadencia, que era el único pendiente de F9; (b) el diagnostic mide **literalmente** el código de producción —antes medía una copia parecida, y una medición sobre otro código no dice nada del producto—; (c) el intercambio de readers convive con el overlay: va **entre `beforeSeek` y `afterSeek`** con `overlay.rebind(reader)` en el medio, porque la base guardada pertenece al reader que se va y restaurarla sobre el que llega escribiría celdas de otro cuadro. El gate nuevo no verifica el mecanismo sino la propiedad: **adoptar y no adoptar tienen que dar exactamente las mismas celdas**. Verificado sin CI hasta donde se puede: las 4 páginas cargan el clip de producción servido local sin errores de consola (overlay, texto e imagen activos), y las expresiones del gate ES5 corridas aparte sobre los 6 archivos tocados no dan hallazgos |
| 2026-08-31 | **La suscripción a Pro no destrabó el CI, y probablemente sea por a qué cuenta se factura.** El operador se suscribió a Pro; se relanzó el run bloqueado y se empujaron cuatro commits: los tres jobs vuelven a morir a los 2 s con la **misma** anotación de pagos/límite de gasto. Dato que lo explica: el repo es **privado** y su dueño es **`tablerosapp-ctrl`** (cuenta de usuario), mientras que quien empuja es **`leoIglesias-hash`** — GitHub cobra los minutos de un repo privado **al dueño del repo** | de ahí las dos salidas, las dos del operador: Pro + método de pago válido + límite de gasto > 0 **en `tablerosapp-ctrl`**, o hacer el repo **público** (minutos ilimitados). El token de esta sesión (scopes `gist, repo, workflow`) no puede leer la facturación de esa cuenta, así que el diagnóstico es estructural, no medido: se confirma o se descarta abriendo Billing & plans de `tablerosapp-ctrl` |
| 2026-08-31 | **El repo de trabajo se mudó a `leoIglesias-hash` y con eso el CI se destrabó** (Instancia 040). El operador: «me suscribí a Pro con `leoIglesias-hash`, ya está, hice cagada… ahora podrías descargar el proyecto y subirlo a mi github, para poder seguirlo desde ahí; luego lo sincronizamos cuando tengamos puntos de guardado, y al terminar dejo todo en `tablerosapp-ctrl`». Se creó **`leoIglesias-hash/ASCILINE-video`** (privado, vía API con la credencial ya guardada en el Credential Manager) y se espejó **todo**: `main`, `assets` (los insumos de encode), `feature/quality-optimization` y los **7 tags**. Remotos renombrados: **`origin` = el repo del operador** (donde se empuja y corre el CI), **`ctrl` = `tablerosapp-ctrl`** (destino final, se sincroniza en los puntos de guardado). El run de `866f2f1` corrió **completo y verde** (`py3.8`, `py3.11`, `py3.11 + zopfli`, 52 s), contra los 2 s sin ejecutar un paso de las últimas cuatro instancias | **confirma el diagnóstico de la Instancia 039 sin necesidad de leer facturación**: los minutos de un repo privado se cobran al **dueño del repo**, así que el Pro en `leoIglesias-hash` no servía mientras el repo fuera de `tablerosapp-ctrl`. Mudar el repo era además la salida más barata: no expone el código (sigue privado), no depende de arreglar pagos en una cuenta ajena y deja el original intacto como destino. Se canceló a mano el run que la rama vieja disparó de arrastre. Con el CI de vuelta, **W-22..W-25 pasan de `en curso (CI bloqueado)` a `cerrada`** y F9 queda con un solo pendiente: publicar |
| 2026-08-31 | **F9 CERRADA: frontend publicado en las cuatro carpetas, 28 keys** (Instancia 040). El operador aprobó publicar de forma explícita. El número de keys **se auditó en vez de estimarse**: se bajaron los 18 archivos de las 4 carpetas y se comparó SHA-256 contra el repo — 4 diferían (`live-player.html`/`index.html`, `tv-player.html`, `diagnostic-player.html`, `overlay.js`), 2 daban 404 (`playloop.js`, `player.html`) y los 12 restantes estaban idénticos. 7 por carpeta × 4 = **28**, contra las «25» que decían los runbooks. Subida con token efímero + `x-sha256` (R2 recalcula el digest), las 28 verificadas byte a byte después, token quemado | dos cosas para la próxima: (a) **auditar lo servido antes de publicar** es barato (68 GETs) y corrige una cuenta escrita a mano que ya estaba mal; (b) el burn del secret **tarda unos segundos en propagar** — el primer `PUT` con el token viejo devolvió `200` y recién el siguiente dio `403`. Dar por quemado un token con una sola prueba es un falso negativo de seguridad |
| 2026-08-31 | **DIAG-002 abierta y puesta ADELANTE DE TODO: pantallazos blancos en TV box** (reporte del operador, Instancia 040). Probó el player en un **WebView de TV box** y ve **flashes blancos entre las imágenes**: «eso es algo crítico… es muy grave y deberíamos estudiarlo». Se registra antes de investigar para que el reporte no se pierda | un flash blanco en un televisor rompe el producto: pesa más que cualquier ganancia de bytes o de milisegundos, así que se adelanta a F10. Dato de encuadre que **no** hay que perder: lo que el operador probó es lo que estaba publicado **antes** de esta instancia, o sea la raíz **sin** cadencia ni pre-decode. Si el motor nuevo mejora, empeora o no cambia el síntoma **hay que medirlo, no suponerlo** — y el nuevo `playloop.js` recién ahora está en la raíz |
| 2026-09-01 | **DECISIÓN DE DIRECCIÓN TOMADA + H-0: nace `ASCILINE-hybrid`** — el operador adoptó el carril mp4/híbrido tras el cuadro final de DIAG-002/003 («el paradigma cambió… necesitamos trabajar con mp4 pero logrando mejoras de reproductividad»). Se creó `leoIglesias-hash/ASCILINE-hybrid` (privado) clonando la historia completa (`main` + `assets`); los diseños/planes del paradigma JS se movieron **verbatim** a `docs/historico/` con README propio; runbooks, índice y CLAUDE.md reescritos para la fase H (H-1 diseño, H-2 investigación mp4, H-3 player híbrido, W-26 heredada); F10/F11/F8/DIAG-001 y opcionales quedan **suspendidas**, recuperables solo con decisión del operador | el repo anterior (`ASCILINE-video`) queda congelado como antecesor con aviso de continuación; conserva su valor como historia y evidencia. La filosofía no cambia: el encoder caro decide offline y el `.asclv` sigue de máster — cambia el transporte (mp4 emitido del máster, decodificado por hardware en el TV) y el invariante de un-solo-layer pasa a dos capas (video + canvas de intervención) por decisión explícita del operador. La rama `feature/quality-optimization` vieja no se migró (estancada; vive en los remotos del repo anterior) |
| 2026-09-01 | **EL ALCANCE SE AMPLÍA: de «player híbrido» a FORMATO PROPIO** (debate de dirección con el operador, mismo día que H-0, sin código). Sus palabras: «nuestro propio formato de video sería ideal… sacar de estos formatos cada cosa útil: **v9 la compresión, dash la compatibilidad, asciline la base que permite todo. encoder caro no importa, decoder con poco estrés**», y «estamos abiertos a nuevos paradigmas». Lo fijado: (a) **`<video>` es la única puerta al hardware** — todo termina en algo que `<video>` acepta nativo, nada se decodifica en CPU propia; (b) **códec-agnóstico desde el día uno** (piezas etiquetadas, el aparato elige; H.264 Baseline es el piso, no el centro); (c) de **DASH el modelo de datos** (Periods / AdaptationSets / Representations / segmentos por rango), no su runtime; (d) **base 1280×720 con fps variable** (decisión del operador); (e) **escalera de intervención N1–N4** con su límite imposible escrito; (f) **nada se normaliza sin medición**. Documentos nuevos: `VISION-Y-OBJETIVOS.md` (norte), `DISENO-FORMATO-VGEN.md` (diseño en obra, con tabla de decidido vs. gateado) y `PLAN-DE-MEDICION.md` (sondas, banco, registro de aparatos). H-1..H-3 **reemplazadas** por **H-4..H-8** | tres razones por las que el orden cambió a **medir primero**: (a) el proyecto ya se equivocó una vez por suponer capacidades — F9 completa, medida y publicada, y en la caja real 290 ms/cuadro contra 66,7; (b) la hipótesis más rentable es verificable en minutos: **si YouTube anda bien en la caja, esa caja tiene VP9 por hardware**, o sea que VP9 es su camino más rodado y no el exótico, lo que da vuelta la suposición de que H.264 era «lo compatible»; (c) hay bifurcaciones de diseño que no se pueden resolver escribiendo — si un canvas encima del `<video>` le baja el fps, la intervención va **al lado** y no encima, y eso cambia el layout de todo el producto. Fijar 1280×720 no es estético: es lo que hace **intercambiables** a las piezas (cabecera compartida) y evita que el decodificador se reconfigure a mitad de stream, causa clásica de tildado en SoCs baratos. El fps variable es gratis en el contenedor —la duración de cada cuadro es un dato, no bitstream— y baja el costo de decodificación de forma lineal. El caso «cambiar solo la música» resultó ser **el más fácil** del sistema, no el más difícil: es cambiar de pista de audio, y en su versión inmediata ni siquiera necesita el muxer |
| 2026-09-01 | **CORRECCIÓN DE MÉTODO: se descarta la sonda sintética y se arranca EMITIENDO** (mismo día, después de la documentación del alcance; sin código). El operador leyó el plan y frenó H-4: «el camino de H-4 no es el correcto porque nos basaríamos solo en 1 tv box, mejor tomar las bondades de cada encoder para crear el nuestro **y ya**. Y empezar con el primer video aunque sea basado en suposiciones: al probarlo podremos ir viendo si vamos en la dirección correcta paso a paso». Tiene razón en dos cosas: (a) medir una sola caja y normalizar contra ella es el **error simétrico** al de F9 —F9 supuso capacidades, esto hubiera sobreajustado a un aparato—; (b) reproducir material real responde más que un cuestionario (`canPlayType` dice «probablemente»; un video que corre 15 s sin caer cuadros dice que sí). **La sonda no se pospone: se disuelve dentro del primer video** — la página de v0 reporta lo mismo como subproducto, sobre material verdadero y en varios aparatos. Se escribe [`EMISION-V0.md`](EMISION-V0.md) (qué le tomamos a cada códec + las suposiciones **S1..S6 con su refutación escrita**) y se reescribe [`PLAN-DE-MEDICION.md`](PLAN-DE-MEDICION.md) («se mide reproduciendo, y nunca en un solo aparato»). **Invariante nuevo (VISION §8.11): ningún aparato solo define el formato** — puede refutar, no consagrar; para normalizar hacen falta ≥2 clases de aparato o la decisión del operador. **Regla 8 del runbook reformulada:** arrancar suponiendo está permitido y es el método; lo prohibido es **normalizar** una suposición sin haberla reproducido. **H-4/H-5 REEMPLAZADAS** (IDs no reusables); nuevo orden **H-9 → H-10 → H-11 → H-6 → H-12 → H-7 → H-8**. Hallazgo de diseño anotado al pasar: **el manifiesto de runtime no puede ser JSON** —el gate ES5 prohíbe `JSON`—, va en texto tabulado; queda como fila **decidida** en `DISENO-FORMATO-VGEN.md` §10. Próxima acción real: **H-9**, el pack v0. |
| 2026-09-01 | **H-9 CERRADA: existe el primer video del formato** (run `33559631360`, verde). Pack v0 emitido desde el máster `dcd6afb6…1632a` (bajado de la copia pineada del player y verificado por SHA-256): Baseline 9.551.693 B · Main 8.686.512 B (−9,1 %) · VP9 4.411.693 B (**−53,8 %**) · VP9+alfa 4.664.676 B; 231 cuadros, 2 min 22 s de runner. Tres lecturas: (a) **VP9 comprime a menos de la mitad** con la misma estructura y el mismo material; (b) **el DPB mínimo se paga en bitrate** — nuestro Baseline pesa 2,3× el `producto.mp4` que en la caja «reproduce muy bien», porque aquel salió con defaults de ffmpeg (GOP largo, cuadros B, varias referencias, calidad más floja) y este lleva CRF 20 + GOP cerrado 15 + sin B + `refs=1` a propósito; (c) Main gana 9,1 % con estructura idéntica, que es lo que Baseline paga por no usar CABAC. **Nada de esto normaliza nada:** son bytes, no fluidez, y la fluidez la dice H-10 en aparatos reales. Detalle y método en el REGISTRO (entrada H-9) y en [`EMISION-V0.md`](EMISION-V0.md) §3.b. |
| 2026-09-01 | **PACK V0 PUBLICADO en `https://iargen.com/player/v0/`** (H-10; el operador eligió publicar antes que servir por LAN). Hizo falta **redesplegar el worker** —primera vez desde que existe la copia en `deploy/`— porque no tenía `content-type` de video ni `Range`: publicar así habría dado un **falso negativo** (varios WebViews de TV miran el `content-type` antes de decidir si pueden reproducir, y algunos no arrancan sin rangos), o sea que el aparato podría haber «refutado» S1/S3 por culpa del servidor. Dos agregados y nada más: `mp4`/`webm`/`tsv` en la tabla de tipos, y `Range` → `206`/`416`/`accept-ranges` (la rama sin `Range` quedó idéntica). Orden respetado: copia guardada y commiteada (`bfa931c`) **antes** del deploy; `keep_bindings:["secret_text"]` para no perder el secret. Verificado después: raíz igual (200, 26.679 B), `Range: bytes=0-99` → `206 bytes 0-99/10999`, bindings `BUCKET` + `UPLOAD_TOKEN` intactas. **6 keys nuevas** bajo `v0/`, las 6 verificadas por SHA-256 contra el archivo local, con `video/mp4` y `video/webm` correctos; token efímero quemado (403 al primer intento). Nada preexistente se tocó. Detalle en el REGISTRO. |
| 2026-09-01 | **EL PACK V0 SUMA HLS Y DASH, y aparece una deuda de determinismo.** El operador preguntó si HLS/DASH estaba contemplado: lo estaba **a medias** —DASH como modelo de datos (decidido), pero el pack eran cuatro archivos progresivos y lo único que la página decía era `canPlayType`, que para m3u8 no vale como evidencia—. Se agregaron `hls-ts/`, `hls-fmp4/` (CMAF) y `dash/`, todos por **remux `-c copy`** desde la pieza Baseline: prueban **S7** (camino D: donde haya HLS/DASH nativo, el muxer ES5 de H-8 puede sobrar en ese perfil — por eso no podía ir después del muxer) y **S8** (piezas intercambiables sin recodificar). Sobrecarga: TS +2,6 %, CMAF y DASH **+0,04 %**. **Hallazgo:** los 16 segmentos de `hls-fmp4/` y los 16 de `dash/` son **byte-idénticos uno a uno** — un solo juego de piezas, dos manifiestos: la tesis del formato comprobada sin escribir muxer. **⚠ Deuda abierta (H-14):** la re-emisión mostró que el **invariante 7 no se cumple en H.264** — VP9 y VP9+alfa salieron byte-idénticos, pero Baseline (+22 B) y Main (−74 B) no, con **misma versión de ffmpeg y misma línea de opciones de x264** (`threads=1`); el primer byte distinto cae en las tablas de muestras, o sea que difiere el bitstream. Hipótesis sin comprobar: `mbtree` en punto flotante sobre runners con CPU distinto. **59 keys** publicadas y verificadas por SHA-256 (0 diferencias); hizo falta un **segundo redeploy del worker** para `m3u8`/`mpd`/`ts`/`m4s` (con HLS el tipo de la playlist es lo primero que mira el reproductor), guardado antes en `00deb9f`, raíz del player intacta. Detalle: verificar tipos con cache-buster — la caché de borde miente. |
| 2026-09-01 | **Ergonomia de control remoto** (pedido del operador, recordando que esto corre en un TV box): las paginas de diagnostico pasan a manejarse **por numero**, no por click —en un WebView de TV el click exige mover un puntero emulado, y las teclas numericas llegan directo—. Nuevo `frontend/keypad.js` **compartido** (la leccion de W-22..W-25 aplicada de entrada: el motor no se copia). **La regla del retardo es mejor que lo pedido:** se espera **solo** cuando el digito puede ser el comienzo de un codigo mas largo, asi que lo comun dispara al instante y solo los compuestos (`9+numero`) esperan; ademas OK dispara sin esperar y Volver limpia. Calibrable con `?delay=<ms>`. En `v0.html`: `1` correr todo, `2` HLS/DASH, `3` alfa, `4` blob:, `5..8` cada pieza, `0` cortar, `90..94` lo secundario, con la leyenda dibujada en pantalla. Nuevo **`frontend/ir.html`**: lanzador **autocontenido** que el operador sube a **otro servidor** (decision suya), por eso sin dependencias al lado y con **URLs absolutas**; se muda editando una linea (`BASE`), y acepta `?v=` para saltar directo. Suites nuevas `test_keypad.js` y `test_ir_page.js`; `test_v0_page.js` **falla si un digito comun queda demorado** por un compuesto que empieza igual. |
| 2026-09-01 | **`v0.html` pasa a UNA SOLA PANTALLA, sin scroll** (el operador: «como baja con scroll me pierdo la visión»). El problema era de diseño: la prueba de alfa metía un **segundo `<video>`** que empujaba la tabla fuera de pantalla, así que o se veía el video o se veían los números. Ahora: `overflow:hidden`, geometría en JS (16:9 exacto sin `object-fit`, que no existe en WebViews viejos), **tabla al lado del video**, **un solo `<video>`** para todas las piezas —la de alfa incluida, con el fondo verde detrás—, el `1` corre TODO en secuencia con indicador `3/7`, y la tecla **95** muestra el reporte a pantalla completa para fotografiarlo (en una TV no se puede copiar texto). La leyenda de teclas es además el botón táctil, para el celular. **Verificado contra la página publicada:** a 1280×720 el video mide 768×432 (ratio 1,778) y no hay scroll; a 3840×2160 la cuenta cierra igual. `test_v0_page.js` falla si vuelve el scroll, si aparece un segundo `<video>` o si la tabla deja de estar al lado. |
| 2026-09-01 | **PRIMER REPORTE DE APARATO: la TV box** (foto del operador, transcripta textual al REGISTRO). Android 9, WebView Chromium 70, panel 1280×720 con superficie 3840×2160. **Todo lo progresivo reproduce fluido por hardware** (0–2 caídos de ~155 en 10 s, deriva ≤ 2 ms, cero atascos reales, con la superficie 4K activa); **Main = Baseline → decodificador hardware** (el par de v0 aísla la entropía, no el DPB: los dos llevan `refs=1` sin B); **el arranque lo manda la cantidad de bytes por red** (H.264 2.985 ms por red contra **517 ms** desde `blob:`; VP9 931 ms); **VP9 y HLS-TS reproducen pero el contador de cuadros no los ve** (`total 0`) — su fluidez la firma el ojo; **HLS-TS nativo sí** (2.012 ms), **HLS-fMP4 nativo inservible** (14.223 ms, 2 atascos), **DASH nativo no**; MSE declarado para `avc1` y `vp9` **sin probar**; IndexedDB sí; sin rVFC ni `getVideoPlaybackQuality`. Suposiciones: S1, S8 sostenidas en la caja; el detector de S2 resuelto (hardware) y S2 reclasificada a bytes; S3 a medias (ojo); S4 pendiente del ojo; S7 sostenida para HLS-TS y refutada para fMP4/DASH; nuevas **S9..S12** (MSE, Blob concatenado, VP9 por MSE, intercambio/bucle). Se escribe **`PLAN-IMPLEMENTACION-VGEN.md`** y se abre **H-13** | tres cambios de rumbo que salen de los números y no de una opinión: (a) **la fluidez en esta clase está saturada** a 720p@15, así que pasa a ser un **gate** y la optimización es de **bytes a igual look y arranque**; (b) **VP9 al frente** donde reproduzca, H.264 Baseline de piso y único carril de HLS-TS; (c) **MSE es la próxima prueba y no requiere emitir nada** — los segmentos CMAF ya están publicados, y de paso se prueba si `init + segmentos` concatenados es un archivo que `<video>` reproduce (si sí, el muxer del camino A es una concatenación). Nada se consagra con un solo aparato (VISION §8.11): todo queda «sostenido en la caja» hasta segunda clase o decisión del operador. Las decisiones que él debe tomar están listadas en el plan, §6 |
| 2026-09-01 | **Respuestas del operador al primer reporte + nombre `.vgen`** (textuales en el REGISTRO). El alfa **compone** (S4); VP9 «perfecto, hasta más fluido» (S3 firmada por el ojo); HLS-TS «se traba mucho al iniciar» → el camino D sale del producto en esta clase; **«de momento el tv box es la base»** → decisión manual: la caja es la **clase principal** y lo que gana en ella queda consagrado (S1, S3, S4, S8), la PC refuta cuando se pruebe; contenido = **loop intervenido + publicidad que reemplaza y vuelve + incentivadores a demanda** → plan §2.7 con sus requisitos (piezas residentes, latencia de cambio a demanda como gate nuevo ≤ 1 s a confirmar, cues por pieza) y H-13 suma «cambio de pieza a demanda y vuelta al loop»; nombre **`.vgen`** → `DISENO-FORMATO-ASCLH.md` → `DISENO-FORMATO-VGEN.md`, `PLAN-IMPLEMENTACION-ASCLH.md` → `PLAN-IMPLEMENTACION-VGEN.md`, futura `SPEC-VGEN.md`; el nombre viejo se reemplaza solo en los documentos vigentes (registro y bitácora quedan como historia). Audio y gates: pendientes, explicados en simple | las respuestas cierran lo que un solo aparato no podía cerrar: el invariante §8.11 prevé la decisión manual y el operador la tomó. El símbolo de play que vio en la pieza con alfa se lee como el control nativo del WebView sobre un video **pausado** por la página al terminar los 10 s (hipótesis; H-13 deja de pausar y lo confirma). Los caminos del producto quedan en **A y B**; H-13 decide cuál hace el cambio de pieza |
| 2026-09-01 | **Audio, gates y compresiones ASCILINE — cierre de todas las decisiones del plan §6.** Operador: «va con audio… tipo radio… publicidades o contenido hablado intercediendo… sincronicidad en algunos momentos» → **dos clases de audio** (ambiente en `<audio>` aparte, continua; el propio de una pieza **muxeado en ella**; cues para lo hablado sobre el loop, tolerancia ≥ 1 cuadro), suposiciones **S13/S14** para la emisión v1. «Apruebo tus gates… el de cuadros un poquito más flexible» → **caídos ≤ 3 %**, el resto igual. «¿Aplicamos las compresiones de ASCILINE antes del vgen?» → **siempre se aplican** (toda pieza sale del máster); en el híbrido compran **bytes** (arranque, caché) e información para el emisor, no velocidad de decodificación (hardware, saturada). **H-13 afilada** en el runbook: módulo `vgenfeed.js`, teclas, columnas, tests, cierre | con esto no queda ninguna decisión pendiente y la próxima sesión (post-compact) ejecuta H-13 sin preguntar. El pedido del operador fue explícito: documentar todo antes del compact, y que la próxima tarea esté lista para «laburar» |
| 2026-09-01 (noche) | **H-13 CERRADA con la foto de la caja** (transcripta textual en el REGISTRO): MSE H.264 **2.033 ms por red, 156 cuadros, 0 atascos** (S9 consagrada; `changeType` sí); Blob `init+16` = archivo de 15,4 s, 1.286 ms desde memoria (S10 en dos clases; el arranque se re-mide contra un mp4 clásico); orden 1-8,13-16,9-12 **limpio por MSE `sequence`** (155, 0 atascos) y **no por Blob** (123 cuadros; «se tilda en una parte», operador) — dos clases, normalizado; **bucle por `loop`: 3 `waiting` en 3 vueltas, 497 ms de deriva, 1 congelado** → refutado; cambio por `src` **305 ms a VP9**, 1.468/1.180 ms a Baseline (bytes). Las filas `cambio*` miden 4 s a propósito (65 cuadros = 4 s a 15 fps), no un timer roto. El contador ahora cuenta VP9 (827 en 60 s) | queda escrito el muxer de H-8: **A = concatenación en orden canónico** (piezas enteras desde caché), **B = MSE `sequence`** (bucle e intercambio), cambio a demanda con la pieza residente y VP9, **D no**. Sigue **H-11**; en su visita: `92` + `97` seguidos y preguntar por el símbolo de play |
| 2026-09-01 (noche) | **H-11 EJECUTADA hasta la pantalla** (`fd9a7ab`, CI verde 3/3): canvas de intervención encima del `<video>`, mismo recuadro, buffer **al panel** (recuadro × `screen.width/innerWidth`, tope 1); tres cargas (nada / rect 26 %×30 % a 15 fps / pantalla completa una vez) sobre Baseline y VP9 = seis filas `capaN:<pieza>` con `pintadas N (WxH)`; teclas `930` (lote: capa ×6 + `blob:` + `blob concat` seguidos), `931`, `932`, `933` (a ojo); el `1` incluye las seis. Hallazgo al medir en la PC: con la pestaña **oculta** Chromium pausa el video mudo y frena los timers a 1 Hz (`capa0` sin canvas dio 0/6) → contador **`oculto`** en cada fila. La única corrida visible en la PC: `capa0:base` 0/156 a 522 ms y el rectángulo repintando en vivo | la PC refuta, no consagra: S5 la decide la foto de la caja. Publicado en `v0/` (una key, copia previa en `deploy/`). Próximo: la visita del operador (`930`, `95`, foto; `933` a ojo; ¿volvió el play?) y, con la foto, DISENO §9 encima/al lado y cierre de H-11 |
| 2026-09-02 | **Corrección del operador sobre la pantalla de H-11** (`b51cd24`): (a) **el mando vuelve a dos cifras** — las tres cifras (`930`..`933`) salían de tener una sola puerta; ahora el `8` es la segunda (conserva su acción, solo espera 900 ms u OK) y la capa vive en **`80`** (lote de la visita), **`81`**, **`82`**, **`83`** (a ojo), con un test que prohíbe cualquier código de tres cifras; (b) **la leyenda entra y jerarquiza** — cada tecla declara su tier (`now` lo que falta probar, grande, arriba y con el número invertido; `tool` las de siempre; `done` lo ya medido, chico y apagado), se dibuja agrupada por tier y la franja arranca más arriba (0,26). El desborde real venía del interlineado, que lo ponía el contenedor y no cada tecla | *«tenemos hasta 100 números antes de eso»* y *«si hay opciones ya probadas podrías achicarlas más que las que deben probarse, eso nos daría lugar y además me ayudaría a diferenciar qué querés que vea»*. Medido a 1272×668 (su geometría): 43 px libres antes del zócalo, antes se pasaba 25 px; a 16:9, 76 px. La visita a la caja es la misma, con otro número: `80` → `95` + foto → `83` a ojo → ¿volvió el play? |
| 2026-09-02 (madrugada) | **H-12 EJECUTADA hasta la pantalla** (`0ce2cb4` → `9011fe7`, CI verde 3/3; el operador dormía y pidió *«más puntos de prueba o mejoras»*). `frontend/vgencache.js` = la única puerta a IndexedDB: bajada con progreso, **ArrayBuffer pineado por contenido** (`id.sha12`), poda de lo que no esté en el manifiesto, techo con **ruido** (la base comprime), cuota por `queryUsageAndQuota`; la escritura se confirma **por la transacción** (un `QuotaExceededError` llega por `onabort`). Teclas **`84`** (guardar + desde caché + techo 10/25/50 MB), **`85`** (desde caché: **la tecla de después de reiniciar**), **`86`** (borrar); cabecera `cache … guardadas N` al cargar; filas sin video no son «ciegas». Leyenda con siete `now` (0,80 em) y `done` a siete por renglón: 35 px libres a 1272×668. **PC (refuta):** desde caché **105 ms** Baseline / 324 ms VP9; 50 MB entran; cuota 35/3123 MB. Publicado en `v0/` (`index.html` + `vgencache.js`, 62 keys; copia en `deploy/` antes). **Visita:** `84` → `95` foto; reiniciar; `95` foto + `85` → foto. |
| 2026-09-02 (madrugada) | **W-26 cerrada en código** (`522bdf8` → `730c5f4`, CI verde): `live-player.html` mira `?renderer=canvas2d` **antes** de crear el contexto WebGL y cae al piso. **La raíz servida no se republicó**: su `index.html` (24.950 B, md5 `534abb7e…`) ya era más viejo que el `live-player.html` del repo antes de este cambio, y el player JS «se mantiene, no crece»; republicarla es decisión del operador con auditoría previa de qué cambió. |
| 2026-09-02 (madrugada) | **H-14 con evidencia de CI** (`0eb8dab`: el workflow `emitir-v0` gana `determinismo: true` —solo las dos piezas H.264, dos veces en la misma corrida, comparadas byte a byte, con `lscpu` y la build de x264 en el log— y `--x264-extra` para probar `cpu-independent=1` sin tocar la receta). **Nueve corridas, causa establecida:** el encoder es **determinista en la misma máquina** (9/9 pares byte-idénticos) y **depende de la CPU**: AMD EPYC 7763 y 9V74 dan los mismos bytes entre sí (Baseline 9.551.693 B) y el Intel Xeon 6973P-C da otros (**9.551.715 B = el pack publicado**: H-9 salió de un Intel y su segunda corrida de un AMD; de ahí los +22/−74 B). **`cpu-independent=1` cura**: AMD 9V74, Intel Xeon 8370C e Intel Xeon 8573C dan bytes idénticos (`abe6caf9…` / `1f92c552…`), a +0,016 % / −0,06 % de bytes. **Pendiente del operador**: adoptarlo en la receta (recomendado; cambia el SHA de las dos piezas H.264, no lo que la caja decodifica) o redefinir el invariante 7. Tabla completa en el REGISTRO. |
