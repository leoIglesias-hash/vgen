# ASCILINE-video — guía de sesión (leer esto primero, siempre)

Convierte video **offline** (Python) a un formato propio `.ascl`/`.asclv` que un player
**ES5 sin dependencias** reproduce en Smart TVs antiguos. Encoder caro, decoder trivial:
el TV nunca cuantiza ni decide, solo ejecuta.

## Arranque post-compact — en este orden, sin leer de más

1. [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md) — dónde quedó todo, próxima acción, bitácora de desvíos.
2. [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md) — **solo la tarea a ejecutar** (archivo, acción, criterio de cierre).
3. [`docs/ejecutados/`](docs/ejecutados/) — lo ya cumplido con su evidencia; consultar, no releer.
4. [`docs/MAPA-DEL-PROYECTO.md`](docs/MAPA-DEL-PROYECTO.md) — solo si falta orientación estructural.
5. Spec de formato / diseño de intervención — solo si la tarea toca bytes u overlay.

## Modelo de trabajo (acordado con el operador, 2026-08-27)

- **Esta máquina no tiene Python ni Node, a propósito.** Toda la regresión (tests Python +
  suites JS) se valida en **GitHub Actions** (workflow `regression`) en cada push.
  Una tarea se cierra **solo con CI en verde**; si CI falla, se corrige hacia adelante.
- **Commits directos a `main`**, un commit por tarea, mensaje `<ID>: <título>`.
  Push tras cada tarea; el CI de ese push es la regresión de cierre.
- Al cerrar una tarea: actualizar su fila en `RUNBOOK-ESTADO.md`; al cerrar una fase o
  lote, sumar el resumen a `docs/ejecutados/`.
- Todo test nuevo se cablea en `tests/run_all.py` **en el mismo commit** (regla 7).
- Los videos de producto **no se commitean a `main`** (`.gitignore` ya lo impone). El
  clip HQ fuente vive local en `inputs/TKN-2443-GANADOR- 15seg-.mp4` y en la rama
  huérfana **`assets`** del repo (solo insumos de encode). Receta de
  producto vigente (2026-08-29): 768 graphic-hq, adaptive kmeans-oklab,
  tile 16, `--palette-refit 5`, `--dither off`,
  **`--trellis-temporal 4`**, zopfli, overlay=off — exactamente los
  defaults del workflow `encode` — → `221de28f…0373` (12.846.465 B,
  35,59 dB, **33,0 % del mp4 fuente**).
- **Generar un clip para ver:** workflow `encode` (Actions → encode → Run workflow).
  Encodea desde la rama `assets` con el perfil HQ por defecto y publica `clip.asclv`,
  la fila de `bench_ref`, el SHA-256 y un `preview.mp4` como artifacts descargables.
- **Al cerrar cada etapa, levantar el player para el operador** (pedido 2026-08-28):
  bajar el último `clip.asclv` del CI a `outputs/` (verificar SHA), correr
  `tools/serve-local.ps1` (puerto 8123, layout plano, **`Cache-Control: no-store`**
  para que nunca vea caché vieja) y avisarle que abra `http://localhost:8123/`.
- **Documentación siempre al día antes de cualquier compact:** estado, registro,
  ejecutados y este archivo se actualizan al cierre de cada tarea/etapa, nunca "después".

## Ayuda-memoria — no perder de vista nunca

1. **Retrocompatibilidad JS:** frontend en sintaxis **ES5.1 estricta**, piso ECMAScript
   2015 de features: sin `fetch`/`Promise`/`Worker`/`WASM`/`JSON`/arrow/`let`/`const`/
   template strings. El gate `tests/test_frontend_compatibility.js` lo verifica; correrlo
   mentalmente antes de escribir cada línea de frontend.
2. **Un solo layer (un solo elemento canvas):** la intervención GRÁFICA escribe índices
   sobre la **misma matriz de celdas** del video, con paleta reservada paramétrica
   (10 → 246..255 o 32 → 224..255; la 255 siempre transparente). Jamás un segundo
   canvas ni un DOM overlay. Desde INT-004 (2026-08-28), los TEXTOS se dibujan
   nativos con la API de texto de Canvas2D **sobre ese mismo canvas**, después del
   frame (no viven en la matriz; con texto nativo el renderer es Canvas2D).
3. **Optimización siempre en el front, pero ganando calidad de imagen:** el costo se paga
   offline (Oklab, K-means, dither, trellis); el front solo se optimiza para hacer *menos
   trabajo por frame*, nunca degradando la imagen ya decidida por el encoder.
4. **Validar todo antes de mutar:** corrupción = excepción tipada; `cells` jamás queda a
   medias. Esta propiedad no se sacrifica por velocidad (fusionar pasadas sí, perder la
   transaccionalidad no).
5. **Determinismo y medición:** mismo input → mismos bytes. Una mejora sin fila de
   `tools/bench_ref.py` registrada no existe. Byte-idéntico se verifica, no se supone.
6. **Canvas2D es el piso; WebGL1 solo acelera**, nunca agrega función.
7. **Ningún buffer nuevo proporcional al frame por cuadro** en el loop estable.
8. **Canonicidad forzada del formato:** uvarint no canónico, padding ≠ 0 u offsets no
   crecientes se **rechazan**. El decoder confía en cero campos.
9. Los valores manuales del operador (cols, fps, colores) prevalecen sobre cualquier
   automatismo.

Referencia completa de invariantes: `docs/MAPA-DEL-PROYECTO.md` §7 y
`docs/PLAN-IMPLEMENTACION-OPTIMIZACION.md`.

## Estado de fases (resumen grueso — el detalle vive en RUNBOOK-ESTADO)

- ✅ F0 · **F1** (paleta reservada, glifos, sidecar) · **F2** (E-08 Zopfli −7,2%,
  E-09 tile_size 4..32 + barrido, E-10 keyframes por corte) · **F4** (W-01..14:
  inflate 2,3×, walk regional ≈−40%, markRectDirty, robustez player) ·
  **F7/S-5** (runtime del overlay: overlay.js + datachannel.js + referencia
  Python byte-idéntica; `make_clip --reserved 10`, panel de 20 números,
  workflow `encode` con `overlay=on` publica `clip.asclv`+`clip.slots`;
  `live-player.html` lo reproduce) · S-1/S-2/S-3 · P-02 (HQ reproducible;
  con Zopfli: 17.482.270 B, `ebfe2eb4…4b36`)
- ✅ **INT-003 (vía corta)**: reserva de 32 (224..255, cola F7 intacta),
  ASCLSLOT v2 (parches heterogéneos, kind dígitos/elección, presupuestos por
  frame), runtime v2 con NONE y presencia (v1 byte-idéntico), `bake_patches`
  (cualquier TTF/PNG → Oklab), `make_patch_pack` demo, workflow
  `overlay=off/panel/patches`. La **ruleta** va con ASCLVID3 (F6/S-4).
  Evidencia: `docs/ejecutados/2026-08-28-INT-003-parches-genericos.md`.
- ✅ **INT-004 (texto nativo)**: `textlayer.js` (`21df177`) + integración en
  live-player (`76ffe45`) — campos grandes del sidecar v2 espejados como
  texto serif nítido al costado de la matriz, mismos payloads para ambos;
  con texto el renderer es Canvas2D con `pixelScale=zoom` (backing real,
  put chico + drawImage del canvas sobre sí mismo, sin segundo canvas).
  Evidencia: `docs/ejecutados/2026-08-28-INT-004-texto-nativo.md`.
- ✅ **INT-006 (carril completo, 2026-08-28)**: (A) fondo re-encodeado
  `overlay=off` — el **768 reproduce byte a byte la referencia P-02**
  (`ebfe2eb4…4b36`, 17.482.270 B, instalado en `outputs/`; PSNR 34,29) y
  el **960** quedó medido (`31348a83…5688`, 25,0 MB, 34,40) por si el
  operador lo prefiere; `clip.slots`/`data.txt` borrados. (B) texto
  standalone: `textfeed.js` (`49e2b4a`+fix `2c81856`) — sin sidecar el
  player declara 3 campos de 2 dígitos por tercios; botón+canal los
  alimentan (`datachannel.js` intacto). (C) **D7=a imagen nativa**
  (`3e51ce8`): `outputs/logo.png` opcional con drawImage sobre el MISMO
  canvas tras el texto; (c) INT-005/época sigue definitivo para la
  ruleta. Evidencia: `docs/ejecutados/2026-08-28-INT-006-…` +
  Instancia 017.
- ✅ **E-12 (refit de paleta, 2026-08-28)**: `--palette-refit 0..10`
  opt-in (`09c4261`) — Lloyd acotado tras cada paleta con la regla de
  asignación real del encode y aceptación monótona (nunca degrada);
  reservadas intactas. Bench 768 `overlay=off` (Instancia 018):
  **refit 5 = 35,46 dB / Oklab 0,00732 / 17.379.859 B**
  (`adef9e53…c05bb`) vs 34,29 / 0,00793 de P-02 → **+1,17 dB con menos
  bytes**; instalado en `outputs/` como fondo de producto. P-02 sigue
  reproducible con el flag en 0.
- ✅ **E-13 (Lloyd uint8, 2026-08-28)**: `--palette-uint8-refine 0..10`
  opt-in (`a64c7ce`) — cierra el Lloyd restringido a paletas sRGB
  representables con aceptación monótona por inercia. Medido sobre
  refit 5 (Instancia 019, `a95d0bbc…`): PSNR igual, Oklab −0,5 %,
  bytes +0,36 % → **no adoptado**; el producto sigue con refit 5 solo.
- ✅ **E-14 (dos pasadas, 2026-08-28)**: modo global sin materializar
  (`f324f1e`) — `StreamingColorAggregate` + `sample_aggregate` ajustan la
  paleta kmeans-oklab sobre TODOS los píxeles (sin cap de 65.536);
  Pillow/RGB reproducen byte a byte el muestreo histórico. Instancia 020:
  **RSS 886 → 433 MB (−51 %)**, Oklab −4,5 %, PSNR RGB −0,27 dB (desvío
  registrado en bitácora; global no es el modo de producto).
- ✅ **E-15 (estabilidad temporal ×4, 2026-08-28)**: `_stabilize_rgb_palette`
  (`91a0e68`) — alineación 1:1 + fusión por `temporal_strength` en
  kmeans-rgb/median-cut/fast-octree (block, adaptive y per-frame).
  Instancia 021: fronteras −31 %/−93 % en sintético; clip real kmeans-rgb
  −1,25 % bytes, PSNR −1,04 dB por el blending (knob
  `--adaptive-stability-max 0` = solo alineación). Producto sin cambios.
- ✅ **E-16 (PairLUT exacto, 2026-08-28)**: `exact_pairs` trama desde la
  base real del cuantizador (muere el gate 555). Bench de producto
  (Instancia 022, `0ed4cbbe…`): **−0,21 dB, +4,1 % Oklab, +6 % bytes,
  +39 % tiempo → NO adoptado**; la exactitud quedó **opt-in
  `--dither-exact`** y el default vuelve a la LUT histórica
  byte-idéntica (el producto `adef9e53…` sigue reproducible desde main).
  Se reevalúa con E-17.
- ✅ **E-17 (presupuesto de dither en bytes, 2026-08-29)**: opt-in
  `--dither-byte-budget N` (default `None` = byte-idéntico); mide los
  bytes reales del frame con la estructura del emisor y recorta por
  bisección. **Mecanismo validado** (Instancia 023): 450 B/frame
  conserva el 40 % de las celdas tramadas y cae proporcionalmente entre
  los extremos. `budget 0` = dither off pero 4:43 más lento y 41 B más
  grande → descartado como receta. **No se adoptó nada**: el bench
  ordena hacia «sin dither», pero `psnr_rgb_db` y `err_oklab_medio` son
  promedios por píxel ciegos al banding, así que la elección
  on/450/off es visual y está en manos del operador. **Resuelta 2026-08-29:
  el operador eligió OFF** — el fondo de producto pasa a `74be25ef…011f9`
  (17.168.633 B, 35,63 dB, Oklab 0,00721, instalado en `outputs/`); el
  default `dither` del workflow `encode` pasa a `off` (la receta de
  producto es defaults + `extra=--palette-refit 5`).
- ✅ **E-18 (dither vs threshold, 2026-08-29)**: el revert del threshold
  ya no pisa celdas que el dither movió (`keep &= ~dither_changed_mask`),
  con contadores propios. No toca el producto (`--threshold` default 0).
  **Con E-17 y E-18, F3 (E-12..E-18) queda cerrada.**
- ✅ **E-19 (orden canónico, 2026-08-29)**: `backend/trellis.py` con
  `CANONICAL_STAGES` como dato importable y el `--threshold` absorbido
  como caso degenerado del trellis; E-20..E-23 extienden ese módulo, no
  agregan pasadas al bucle. Refactor puro.
- ✅ **E-20 (umbral en ΔE-Oklab, 2026-08-29)**: `--threshold-metric
  {rgb,oklab}` con **default `rgb`** (los valores ya elegidos por el
  operador no se reinterpretan, regla 9); la paleta se convierte una vez
  por paleta, así que Oklab no cuesta más por frame. **Sin fila de bench
  todavía: no cambia ninguna receta.**
- 🔒 **Byte-identidad del producto verificada 3 veces** (regla 5):
  `adef9e53…c05bb` reproducido post-E-16, post-E-18 y post-E-19/E-20
  (run 33235096580 desde `73c67ad`). El refactor no movió un byte.
- ✅ **INT-007 (2026-08-29, `faf2390`)**: tipografía Palatino bold con
  sombra translúcida (`weight`/`shadow` en textlayer.js, derrame < 1
  celda, markDirty expandido) y `outputs/logo.png` girando como ruleta
  simulada (ángulo determinista por frame, cuadrado circunscripto
  marcado sucio). Verificado en navegador; la ruleta REAL sigue en F6.
- ✅ **E-21 (2026-08-29, `7e6fd8e`, ADOPTADA)**: jerarquía de costo en
  `trellis.py` (`COST_LADDER`: `proxy_cost` entropía orden 0 para
  E-22/E-23, `finalist_deflate` zlib-9 determinista, `champion_deflate`
  best_deflate SOLO al ganador); emisor v1, predictores v2 y transcode
  eligen en zlib-9 y pagan un campeón por frame. Instancia 024:
  **PSNR/Oklab idénticos, +2.040 B (+0,012 %), wall 44:21 → 20:18
  (−54 %)** → producto `41c94170…79d5`; `74be25ef…` queda histórica (el
  emisor cambió). Sin Zopfli la salida es byte-idéntica a la histórica.
- ✅ **E-22 (2026-08-29, `9ab95f6`, ADOPTADA con presupuesto 4)**: el
  índice del frame anterior como segundo candidato — se emite si el
  error EXTRA contra el pixel objetivo no supera el presupuesto (la
  celda sale del DELTA; extra negativo = sale mejorando). Barrido
  (Instancia 025) y decisión visual del operador en dos pasos el mismo
  día (aprobó el 2 y luego el 4: «el más agresivo se ve perfecto, no
  noto la diferencia»): **producto = presupuesto 4 → `221de28f…0373`,
  −25,2 % de bytes por −0,04 dB** (determinismo re-verificado); el 2
  (`63fb7aae…`, +0,12 dB) quedó aprobado y superado; 10 descartado
  (−0,82 dB). Pidió barrer presupuestos más agresivos (5/6/8) en E-24.
  Default CLI 0 = byte-idéntico; el workflow lo pasa por `extra`.
- ✅ **E-23 (2026-08-29, `626694a`, opt-in `--trellis-spatial`)**: en
  tiles con 17/5/3 valores distintos, fusionar el más raro cruza a un
  opcode más barato del regional v2; se fuerza en el ENCODER (el
  transcode sigue lossless exacto). Aislado (Instancia 026): −0,32 %
  por −0,01 dB (satura entre 8 y 16) → sin adopción en solitario, es
  ingrediente de E-24. Default 0 = byte-idéntico.
- ▶ **E-24 en curso (2026-08-30, `29ad7f8`+`271dd19`, CI verde):**
  `bench_ref.py` ganó `err_temporal` y `proxy_banding` (por fin ven
  arrastre y banding; el proxy NO castiga al dither) y `make_clip`
  ganó `--near-lossless N` (temporal+espacial al mismo presupuesto,
  0 = byte-idéntico, no se mezcla con los flags explícitos). Barrido
  Instancia 027: baseline `41c94170…` y producto `221de28f…`
  reproducidos byte a byte con columnas nuevas; nl4 ≈ producto
  (−0,04 %, el espacial no suma); **nl5 = −3,9 % bytes, nl6 = −7,0 %,
  nl8 = −12,0 % (−0,49 dB, banding +18 %)**. El salto
  baseline→producto (+4,7 % err_temporal, +30 % banding) es el que el
  operador ya juzgó invisible — 5 y 6 agregan mucho menos que eso.
  **Falta SOLO su decisión visual sobre
  `outputs/preview-e24-nl{5,6,8}.mp4`**; con ella cierra E-24 y F5
  (si se queda con temporal 4, F5 se archiva con su evidencia).
  Decisión abierta extra: si retoma el 960, re-medirlo con refit 5.
- 📌 **S-7 agendada**: barrido de resolución 768 → 1280 → 1920 **después
  de F5**, con el objetivo del operador de subir densidad sin perder
  peso. Dato de referencia: la fuente mp4 pesa 38.966.462 B y el
  producto 768 pesa 12.846.465 B = **33,0 % del original** (con el
  trellis temporal 4 adoptado). El 1920
  estimado a la tasa actual ≈ 107 MB (2,7× la fuente) y no entra en el
  `timeout-minutes: 120`; se arranca por 1280 para medir la curva.
- La caída de calidad de la reserva de 32 se resolverá en F6 con **INT-005
  (parches por época)**: el gráfico se declara antes del encode con su
  ventana y se cuantiza contra las paletas de esas épocas (sin reserva).
- Pendiente: F5 (E-19..E-24), F6 (S-4), S-7 (resolución, tras F5),
  F8 (necesita F6; F7 ya está).
  Opcionales: E-11, W-15. Gates físicos de INT-002 (p95, MEM-001) → F8
