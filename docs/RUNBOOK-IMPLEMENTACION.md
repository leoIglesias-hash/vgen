# Runbook de implementación

Estado: **podado el 2026-08-30, re-podado el 2026-08-31 (F6/S-4 y S-7 cerradas), ampliado
el 2026-08-31 con el plan nuevo (F9, F10, F11 y DIAG-001)**.
Este archivo contiene SOLO las reglas de ejecución y las tareas que quedan por hacer:
**F9 (S-8), F10 (S-9), F11 (S-10), F8 (S-6), DIAG-001 y las opcionales E-11/W-15**.
Los cuerpos de las tareas ya ejecutadas
(P-01..P-04, E-01..E-24, W-01..W-14, F6, F7, INT-003/004/006/007, S-7, deploy del
player) se retiraron: su resumen operativo está en
[`ejecutados/`](ejecutados/README.md), su fila de cierre en las tablas archivadas
([`ejecutados/2026-08-31-tablas-de-tareas-cerradas.md`](ejecutados/2026-08-31-tablas-de-tareas-cerradas.md))
y su evidencia en
[`REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](REGISTRO-DE-PRUEBAS-Y-DECISIONES.md). El texto
completo original vive en el historial Git (hasta el commit anterior a cada poda).

Este documento no argumenta ni justifica: para eso están
[`PLAN-UNIFICADO-TIERS-E-INTERVENCION.md`](PLAN-UNIFICADO-TIERS-E-INTERVENCION.md) y
[`DISENO-INTERVENCION-MATRICIAL.md`](DISENO-INTERVENCION-MATRICIAL.md). Acá está qué
tocar, cómo verificarlo y cuándo una tarea se considera cerrada.

## 0. Reglas de ejecución

1. **Commits directos a `main`, un commit por tarea.** Mensaje: `<ID>: <título>`. Si una
   tarea necesita varios commits, todos llevan el mismo ID. (El modelo original de dos
   ramas quedó sin efecto por decisión del operador, 2026-08-27.)
2. **Regresión antes de cerrar.** La máquina de trabajo no tiene Python ni Node
   **a propósito**: la regresión completa corre en GitHub Actions (workflow `regression`)
   en cada push. Una tarea se cierra solo con ese CI en verde; si falla, se corrige hacia
   adelante.
3. **Fila de registro obligatoria** para toda tarea marcada Δbytes. Plantilla en §6.
4. **Una tarea no empieza si su precondición no está cerrada.**
5. **Ninguna tarea se cierra «porque compila».** El criterio de cierre está escrito y es
   verificable.
6. **Todo test nuevo se cablea en `tests/run_all.py` en el mismo commit.** Un test que no
   corre en la regresión no cuenta como test.
7. **Procedencia del código por sesión.** Al iniciar una sesión se anota en
   `RUNBOOK-ESTADO.md` sobre qué commit se trabaja. Las referencias `archivo:línea`
   antiguas se localizan por nombre de función, nunca por número de línea a ciegas.

## 1. Trabajo en curso (definido fuera de este archivo)

- **En ejecución: F9 (S-8)**, con `W-16` ya cerrada; la próxima tarea es `W-17`. El
  detalle vivo y el orden entre fases están en `RUNBOOK-ESTADO.md` §Próxima acción.
- **Del operador:** probar `iargen.com/player/` en celular y Smart TV (antesala de F8).

### Principio de resolución y fps (operador, 2026-08-31 — extiende la regla 9)

**La resolución y los fps son elegibles por video, siempre, y nunca quedan fijados por
una receta.** El destino real son televisores de 1920, así que toda grilla se estira: lo
que se elige por video es *cuánta densidad conviene pagar*, y esa comparación
(1280 bien reconstruido contra 1920 nativo) es parte del trabajo de cada clip, no una
decisión tomada de una vez para siempre. El front debe procesar cualquier combinación
que se le pase; ninguna tarea puede asumir la grilla del producto vigente.

## 2. Tareas opcionales (no bloquean nada)

### E-11 — Flags de audio (OPCIONAL)

- En el HQ el audio es ~1 % del bundle; solo importa en perfiles de 320 columnas.
- **Archivo:** `backend/encoder.py` (llamada a ffmpeg del audio).
- **Acción:** exponer `--audio-bitrate`, `--audio-mono` y `--audio-samplerate`. Default
  sin cambios (`-q:a 4`).
- **Cierre:** el default produce audio byte-idéntico al actual. Δbytes: sí, solo si se usan.

### W-15 — Camino ASCII de Canvas2D (OPCIONAL)

- Solo afecta a los modos `ascii-*`, que el camino `pixel` de producción no usa. Se hace
  únicamente si los modos ASCII vuelven a ser objetivo del producto.
- **Archivo:** `frontend/render-canvas2d.js` (camino de glifos).
- **Acción:** cachear las cadenas `"rgb(r,g,b)"` por entrada de paleta y los
  `ramp.charAt(i)` en arrays; agrupar por color para minimizar cambios de `fillStyle`;
  limitar el redibujo a `dirtyY0..dirtyY1` (hoy ignora el dirty set).
- **Cierre:** salida visual idéntica; mejora medida.

## 3. Fases pendientes

Orden acordado con el operador (2026-08-31): **F9 → F10 → F11 → F8 → DIAG-001**. F9 va
primero porque no toca bytes, se valida contra el clip que ya está en producción y su
ciclo de prueba dura minutos en vez de una hora de runner.

### F9 — Aceleración del frontend (S-8)

Diseño completo: [`DISENO-RENDER-INDEXADO.md`](DISENO-RENDER-INDEXADO.md). Ninguna tarea
de esta fase cambia el formato ni exige re-encodear.

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **W-17** | `frontend/reader.js`, `frontend/reader-v2.js` | LUT `Uint32Array(256)` de paleta con endianness detectada una vez; escritura por palabra sobre vista `Uint32` del destino; fallback byte a byte obligatorio. El prototipo verificado ya vive en `tools/bench_render.js` (`makeLut`/`lutFull`/`lutChanged`) | salida **byte-idéntica** sobre el corpus (test de paridad) + fila de `bench-render` contra el baseline `f1ccfa3` |
| **W-18** | `frontend/render-webgl.js` | índices como textura `LUMINANCE` (subida directa de `cells`) + paleta como textura 256×1 RGBA + lookup en el fragment shader. `UNPACK_ALIGNMENT 1`, corrección de medio texel, `highp` con fallback a `mediump`. Camino RGBA actual **se conserva** como fallback | paridad de píxeles con Canvas2D en modo `nearest` (`readPixels` sobre frame sintético); conversión en CPU eliminada y upload ×4 menor, medidos |
| **W-19** | `frontend/render-webgl.js`, `frontend/render-canvas2d.js`, `frontend/tv-player.html` | modo `soft` = 4 taps NEAREST + 4 lookups + mezcla en espacio de color (**nunca interpolar índices**); modo `nearest` idéntico a hoy; `fitCanvas` gana escalado entero por query string como herramienta de comparación | el operador compara en el TV 1280 `nearest` / 1280 `soft` / 1920 nativo sobre el mismo video |
| **W-20** | `frontend/tv-player.html` | presentación anclada a la cadencia del display con corrección lenta contra el audio; pre-decode **solo del próximo keyframe** en el tiempo muerto, a un buffer alterno **fijo** de `cells` (no viola el invariante 7; adelantar deltas exigiría base definida sin romper el invariante 4 y se diseñaría aparte) | en el diagnostic, a 1920: drops < 0,1 % y p95 de decode+render bajo el presupuesto de frame |
| **W-21** | `frontend/reader-v2.js`, ambos renderers | dirty rect en X (hoy la subida es banda de ancho completo: `x0/x1` no se calculan en ningún lado) | misma imagen; subida medida menor en corpus con cambios localizados. **Opcional dentro de F9** |

Precondición dura **ya cumplida**: `W-16` cerrada el 2026-08-31 (`f1ccfa3`, CI verde) —
`tools/bench_render.js` (banco de la conversión índice→RGBA; corre en `run_all.py` y
publica su tabla en cada push, con el workflow `bench-render` para la corrida larga y el
HEAD-vs-baseline) y `frontend/diagnostic-player.html` (**F8-1 adelantada**: desglose por
etapa con p50/p95, drops y frames tarde). Ninguna otra tarea de F9 se cierra sin su fila
de medición (reglas 5 y 6 del proyecto). W-18 y W-19 se implementan juntas: la textura de
índices rompe el modo `soft` actual si la reconstrucción no la acompaña.

### F10 — Pérdida adaptativa por suavidad (S-9)

Diseño completo: [`DISENO-PERDIDA-ADAPTATIVA.md`](DISENO-PERDIDA-ADAPTATIVA.md). Emite
ASCL v3 igual que hoy: el decoder no se entera. Comparación siempre contra el producto
vigente `dcd6afb6…1632a` (24.458.884 B, 35,02 dB, `proxy_banding` 0,001522).

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **E-25** | `backend/perceptual_palette.py`, `backend/encoder.py`, `backend/make_clip.py` | exponer `--gradient-boost` (default 3.0 = valor actual) y calcular el mapa de suavidad una vez por frame, disponible para las etapas siguientes | con el default, salida **byte-idéntica**. Δbytes solo con otros valores |
| **E-27** | `backend/trellis.py` | guard: el trellis espacial no fusiona el valor menos frecuente si el tile es rampa suave (es la causa directa del escalonado en degradés) | `proxy_banding` baja; bytes ≈ iguales (< 0,1 %). Fila de registro |
| **E-26** | `backend/trellis.py` | `--near-lossless-shape k` (default 0 = comportamiento exacto de hoy): presupuesto por celda `budget * (1 - k * suavidad)` en las tres etapas del trellis | a igual o menor cantidad de bytes, `proxy_banding` baja de forma medible. **Línea base: el producto post-E-27** (medir contra el vigente le atribuiría mérito doble). Fila de registro |
| **E-28** | `backend/dither.py`, `backend/encoder.py` | dither dirigido **solo a mesetas detectadas**, con `--dither-byte-budget` bajo y aceptación por `proxy_banding` (métrica que no existía cuando el operador rechazó el dither global de 211 KB) | decisión visual del operador con previews. La pregunta es «¿desapareció el escalonado del huevo?», no «¿se ve mejor el clip?» |
| **E-29** | `backend/ascl_v2.py` | término de costo de decodificación en la elección de tag: penalizar `PREDICT_*` (dos pasadas completas sobre todas las celdas) frente a `REGIONAL_DELTA` con SPARSE | bytes ≈ iguales (< 0,2 %); peor caso por frame menor en `bench_reader_v2.js`. **Opcional** |

Orden: E-25 → E-27 → E-26 → E-28 → E-29.

### F11 — Formato v4: LOD por tile y transparencia (S-10)

Diseño completo:
[`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md). Una sola
revisión de formato para las dos features, por la misma razón que F6 agrupó todo en v3.
**Depende de F9 cerrada** (la LUT de W-17 es lo que hace que el alpha no cueste nada).

| ID | Archivo | Acción | Cierre |
|---|---|---|---|
| **E-30** | `backend/encoder.py`, `backend/make_clip.py` | `--lod-tile <umbral>` (0 = off, default): hornear bloques 2×2 idénticos en tiles de bajo detalle, en la cuantización y **antes** del trellis. Promedio en Oklab; histéresis temporal para que un tile no alterne. La selección **excluye rampas suaves** con el mapa de E-25 (plano = LOD sí, degradé = LOD no) para no reintroducir el banding que F10 saca. **Sin cambio de formato**: mide el beneficio de bytes antes de comprometerse a v4 | el default reproduce la salida actual **byte a byte**; con el flag, bytes menores + decisión visual. Fila de registro |
| **E-31** | `backend/` (análisis offline) | contar los frames del clip real que son candidatos a **solo-paleta** (frame N ≈ transformada global en Oklab del N−1, residuo bajo umbral — fundidos y flashes, hoy el peor caso simultáneo de bytes y trabajo del front) y cuántos bytes cuestan hoy. **Sin cambio de formato, Δbytes: no** (solo reporta) | tabla de candidatos + techo de ahorro; fila de registro. Es el gate de F11-5 |
| **F11-1** | `backend/regional_codec_v2.py`, `frontend/reader-v2.js` | opcode `0x08 LOD2` con sub-stream a `(tile/2)²` reutilizando los candidatos existentes. El decoder valida tile par, tile completo (los truncados de borde no admiten LOD2) y consumo exacto del sub-stream | round-trip exacto; bytes menores que E-30 solo; **trabajo del decoder ×4 menor** en tiles LOD, medido en `bench_reader_v2.js` |
| **F11-5** | `backend/ascl_v2.py`, `frontend/reader-v2.js` | permiso de paleta en frame delta (o tag `PALETTE_ONLY`), gateado por versión ≥ 4: un fundido pasa de cientos de KB + subida completa por frame a **~800 B + rebuild de LUT/re-subida de textura de paleta**. Espejo JS + fuzzing dentro de F11-3 | round-trip exacto. **Condicionada: solo se ejecuta si E-31 muestra techo real y el operador aprueba** — la canonicidad no se relaja «por si acaso» |
| **F11-2** | `backend/encoder.py`, `backend/make_clip.py`, `frontend/*` | transparencia: `cell_fmt = 4` (paleta RGBA) con `version = 4`; `--alpha` (lectura por ffmpeg `rawvideo/rgba`, cv2 descarta el alpha) y `--alpha-levels N` (default 4; 2 = binario). K-means solo sobre alpha > 0 y color **no** premultiplicado. WebGL con `alpha: true` solo si el clip lo declara. **Prohibido combinar con `--reserved`** en esta versión (error explícito) | clip de personaje sobre fondo transparente reproducido en el player; decoders anteriores lo **rechazan** (por versión y por `cell_fmt`), nunca lo muestran a medias |
| **F11-3** | `frontend/reader-v2.js`, `frontend/reader-factory.js`, `backend/ascl_bundle.py`, `tests/test_v4_cross.js` | espejo JS completo, despacho por versión, `.ascl` v4 dentro del envelope, cross-test Python↔JS de matriz y RGBA, fuzzing del opcode y de la paleta RGBA | cross-test en verde; todo campo nuevo cubierto por fuzzing |
| **F11-4** | workflow `encode` | barrido sobre el clip real (1280 y 1920), fila por variante, previews | decisión visual del operador; si adopta, producto a v4 y publicación con puntero CACHE-001 |

> **Idea anotada sin tarea** (operador, 2026-08-31): **paletas por región** — N paletas
> de 256 con selector de 1 byte por tile, partición sin superposición (la región rica es
> dueña exclusiva de sus tiles; el grupo base no codifica nada debajo). Se promueve a
> tarea **solo si** E-25 muestra saturación real de las 256 entradas. Detalle:
> [`DISENO-FORMATO-V4-LOD-Y-ALPHA.md`](DISENO-FORMATO-V4-LOD-Y-ALPHA.md) §10.

### DIAG-001 — Causa del escalonado del huevo (**al final**, por decisión del operador)

El operador decidió (2026-08-31) que el escalado se mira **al último**, después de F9-F11.
Se deja anotado el procedimiento para no reconstruirlo: decodificar el `.asclv` vigente a
resolución nativa (`ascl_decode.py --mp4 --scale 1`, o el workflow `encode` con
`preview: true`) y comparar contra el player a pantalla completa.

- limpio en el MP4 nativo y escalonado en el player → causa el **escalado** (W-19 lo cubre);
- ya escalonado en el MP4 → causa la **paleta/trellis** (F10 lo cubre);
- solo escalonado cuando el huevo se mueve → causa el **trellis temporal / sample-and-hold**.

Probablemente para cuando se ejecute ya esté resuelto por F9 y F10; DIAG-001 es la
verificación de que efectivamente lo está.

### S-6 — Validación física (F8)

| ID | Tarea |
|---|---|
| F8-1 | `frontend/diagnostic-player.html`, ES5, separado de `tv-player.html` — **se adelanta y se ejecuta dentro de `W-16`**, porque F9 no se puede medir sin él |
| F8-2 | Matriz física con las resoluciones de producto: **1280@15** (producto), 768 y 640 de referencia, y el **1920** (el front procesa cualquier resolución/fps; el 1920 se re-prueba a más fps); Canvas2D y WebGL1, y además **con y sin** las rutas de F9 (textura de índices, reconstrucción `soft`, pacing), 30 minutos |
| F8-3 | Go/no-go de v2/**v3**/**v4** (`TV-02`) contra los artefactos **ya optimizados** |
| F8-4 | `MEM-001`: memoria por componente, con y sin overlay |
| F8-5 | Regenerar el artefacto de release **después** del último cambio de codec |

Gates físicos heredados de INT-002: costo p95 por frame del overlay nativo (decide si
INT-005 se implementa) y MEM-001 con y sin overlay.

**INT-005 (parches por época)** sigue **condicionado** (dirección del operador,
2026-08-30): el overlay nativo Canvas2D (texto + imagen sobre el mismo canvas,
INT-004/006/007) es la vía preferida; INT-005 solo se implementa si los gates físicos
de F8 muestran que el dibujo nativo por frame no rinde en el TV real.

**Sigue vetado hasta tener benchmark neto en TV:** `PAL5`/`PAL6` para el hueco de
17-255 colores por tile (candidato de una revisión de formato futura, estimación
25-37 % en tiles de gradiente; quedó fuera de F6 a propósito).

## 5. Definición de terminado

Una tarea está cerrada cuando, y solo cuando:

1. la regresión completa pasa (CI en verde sobre su push);
2. su criterio de cierre escrito se cumple y se verificó, no se supuso;
3. si es Δbytes, su fila está en el registro;
4. el commit lleva su ID;
5. si tocó el frontend, el gate ES5 ampliado pasa;
6. si tocó `inflate.js` o un reader, el fuzzing pasa.

## 6. Plantilla de fila de registro

```text
| ID | fecha | commit | referencia | parámetros | bytes .ascl | bytes .asclv |
  bytes/celda | keyframes | cadena delta máx | PSNR RGB | error Oklab |
  err_temporal | proxy_banding | SHA-256 | conclusión y alcance |
```

Una conclusión queda ligada a su configuración. Si cambia el modo, la grilla, los FPS, la
paleta, el dithering o el codec, se revalida.

El avance se registra en [`RUNBOOK-ESTADO.md`](RUNBOOK-ESTADO.md): una fila por tarea,
actualizada al cerrar cada una. Ese archivo —no la memoria de nadie— es lo que le dice a
la próxima sesión dónde quedó todo.
