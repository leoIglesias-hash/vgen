# Estado de ejecución del runbook

Este archivo es la memoria entre sesiones. Se actualiza **al cerrar cada tarea**, no al
final del día. La próxima sesión de trabajo —humana o asistida— arranca leyendo este
archivo, no reconstruyendo el contexto.

Reglas de uso:

1. Una fila por tarea del [`RUNBOOK-IMPLEMENTACION.md`](RUNBOOK-IMPLEMENTACION.md).
2. Estados válidos: `pendiente`, `en curso`, `cerrada`, `bloqueada (<por qué>)`,
   `archivada (<evidencia>)`, `opcional`.
3. Una tarea `cerrada` cumple la definición de terminado del runbook §5; no se marca antes.
4. Toda decisión que desvíe del runbook se anota en la bitácora de abajo con fecha y
   motivo. El runbook no se edita en silencio.

## Procedencia del código

| Sesión | Fecha | Base de trabajo | Notas |
|---|---|---|---|
| planificación | 2026-08-27 | snapshot ZIP `ASCILINE-video-main` (referencias `archivo:línea` del runbook corresponden a este árbol) | auditoría, diseño INT-001, plan y runbook; sin cambios de código |
| implementación 1 | 2026-08-27 | mismo snapshot, git local `5493455` (baseline) | 8 tareas cerradas; parches en `entrega-2026-08-27/patches/`, aplicables con `git am` sobre el repo real |
| sincronización | 2026-08-27 | clon real en `Escritorio\\repo` (baseline == snapshot, verificado) | `git am` no se aplicó; los 22 archivos finales se escribieron directo en el árbol de trabajo. Historia por tarea preservada solo en los parches; el repo la recibe como un commit |
| implementación 2 | 2026-08-27 | clon real de GitHub, `906b010` | máquina sin Python/Node **a propósito**: la regresión se valida en GitHub Actions en cada push; commits directos a `main`, un commit por tarea |

> Al iniciar cada sesión de implementación: agregar una fila con el commit o snapshot
> sobre el que se trabaja. Si el árbol cambió desde el 2026-08-27, localizar las
> referencias por nombre de función, no por número de línea.

## Preparación

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| P-01 | ramas y línea base | cerrada (adaptada) | `5493455` | 2026-08-27 | sin repo real: git local sobre el snapshot, un commit por tarea con ID; regresión base 115+11 en verde |
| P-02 | congelar las dos referencias | cerrada (adaptada) | `7286399` | 2026-08-27 | `synthetic.baseline`: SHA `c29e7728…5d1d7` (canónico kmeans-rgb+cv2 tras E-01: `9cc88e55…`). **HQ nuevo y reproducible**: `TKN-2443` encodeado por workflow `encode` run #1 (graphic-hq 768×432, 15 fps, adaptive/kmeans-oklab, dither auto, v2): 18.829.899 B, 231 frames, 94 keyframes, PSNR 34.29, Oklab 0.00793, SHA `f3051baa…1527`. Fila completa en el registro. El HQ histórico (`6FF3E71E…`) queda como evidencia no regenerable |
| P-03 | `tools/bench_ref.py` | cerrada | `bfa2a1f` | 2026-08-27 | fila determinista verificada; PSNR/Oklab con `--source` |
| P-04 | Zopfli opcional | cerrada | `bf8cd58` | 2026-08-27 | documentado en requirements; instalado y verificado en el entorno de trabajo |

## Carril E — encoder

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| E-01 | `lexsort` en rama OpenCV | cerrada | `6b6b65a` | 2026-08-27 | ambas ramas ordenan vía `_sort_palette_centers`; test de paridad. **El SHA de artefactos kmeans-rgb con cv2 cambia** (nuevo canónico del sintético: `9cc88e55…`); RGB verificado byte-idéntico en 40/40 frames |
| E-02 | endurecer herramientas offline | cerrada | `d3f2bfd` | 2026-08-27 | los 7 puntos del runbook + 6 fixtures de corrupción. El fixture de benchmark declaraba flags no canónicos (per-frame + DELTA) y se corrigió a per-scene. Cierra F0 (encoder) |
| E-03 | `reserved` cableado, default 0 | cerrada | `08234f1` | 2026-08-27 | cableado en las 9 funciones de la cadena de paleta; byte-identidad con `reserved=0` verificada por test en los tres caminos (global/adaptive/per-frame); `pal_size >= reserved+22`; `reserved>0` lanza `NotImplementedError` hasta E-04 (guard anti no-op). CI `regression` #9 en verde |
| E-04 | exclusión del rango reservado (8 funciones) | cerrada | `8badec4`+`c6e55a8` | 2026-08-27 | reserva centralizada en `make_global_palette`: base `pal_size-reserved` + `reserved_colors` del operador estampadas al final (INV-4); cuantizadores, pal_img y PairLUT del dither solo ven la base (INV-3 por construcción). Test 4 estrategias × 4 modos + dither. El CI atrapó el desajuste dither/paleta y se corrigió (`c6e55a8`); regresión en verde |
| E-05 | rects protegidos en dither | cerrada | `7879f05` | 2026-08-27 | `rects_mask` + `protected_rects` en `selective_tile_mask` y `apply_selective_dither`; rects fuera de grilla rechazados; sin rects la salida es byte-idéntica (test). CI en verde |
| E-06 | horneado de glifos | cerrada | `bc57e04`+`b0c2058` | 2026-08-27 | `tools/bake_glyphs.py`: supersample 8×, cobertura normalizada al pico del glifo (entera), cuantización a 246..251, glifo 10 transparente. Dos corridas byte-idénticas verificadas con `cmp` en CI; tabla 8×12 SHA `2ee438f4…042c` (workflow `bake-glyphs`). **Inspección visual aprobada** (dígitos legibles, antialias correcto) y anotada en el registro. CI en verde |
| E-07 | sidecar `ASCLSLOT` | cerrada | `1d46353` | 2026-08-27 | `make_slots.py` + `slots.js` (espejo ES5); 8 fixtures negativos compartidos con veredicto idéntico en ambos validadores; sin carga parcial; CRC + verificación cruzada `reserved_rgb`. **Cierra F1** (resumen en `ejecutados/`). CI en verde |
| E-08 | Zopfli en 5 puntos, simultáneo | cerrada | `8d4489d` | 2026-08-28 | `backend/deflate_util.best_deflate` compartido por los 5 puntos (encoder ×3, predictor v2, regional v2); simetría de `transcode_ascl_bytes` verificada por test de identidad de función; pata de CI extra `py3.11 + zopfli` (verde con y sin el paquete). **Δbytes HQ: 18.829.899 → 17.482.270 B (−7,2%)**, PSNR/Oklab idénticos, SHA `ebfe2eb4…4b36` (Instancia 012). Encode con Zopfli tarda ~40 min de CI |
| E-09 | `tile_size` parametrizado + barrido provisional | cerrada | `d639948`+`29b0a40` | 2026-08-28 | transcode acepta 4..32 (mismo rango que W-08), ganador emitido en byte 26, `transcode_ascl_bytes_sweep` determinista (empate → tile menor); `--tile-size`/`--tile-sweep` en CLI y make_clip; input `tile` en workflow `encode`. Round-trip exacto en los 6 tamaños por test. Barrido sobre ambas referencias en Instancia 013 (HQ: ganador 4 por 335 B, marginal; sintética: ganador 16, −2,73%). CI en verde |
| E-10 | keyframes en cortes de escena | cerrada | `1523f4d` | 2026-08-28 | opt-in `--scene-keyframes` (default off = bytes idénticos, verificado por test): `need_color_descriptor` se calcula siempre con el flag, `hard_cut` fuerza keyframe, `--keyint` expuesto también en make_clip para GOPs largos. Test: corte parcial sintético pasa de cadena DELTA 7 a 3, keyframes 1→2, celdas decodificadas idénticas con y sin el flag. **Cierra F2 (E-08..E-10)**. CI en verde |
| E-11 | flags de audio | opcional | | | |
| E-12 | refit de paleta a asignación real | pendiente | | | |
| E-13 | Lloyd en dominio uint8 | pendiente | | | |
| E-14 | paleta sobre todos los píxeles, dos pasadas | pendiente | | | resuelve también el OOM del modo global |
| E-15 | estabilidad temporal, 4 algoritmos | pendiente | | | |
| E-16 | `PairLUT` exacto | pendiente | | | |
| E-17 | presupuesto de dither en bytes | pendiente | | | cierra V1-OPT-02 |
| E-18 | interacción dither/threshold | pendiente | | | cierra F3 |
| E-19 | orden canónico del pipeline | pendiente | | | |
| E-20 | threshold en ΔE-Oklab | pendiente | | | |
| E-21 | jerarquía de costo del trellis | pendiente | | | |
| E-22 | trellis temporal | pendiente | | | |
| E-23 | trellis espacial | pendiente | | | |
| E-24 | `--near-lossless` ΔE conservador | pendiente | | | si el ahorro no alcanza, F5 se archiva |

## Carril W — frontend

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| W-01 | gate ES5 ampliado | cerrada | `5b33899` | 2026-08-27 | 12 patrones nuevos, cada uno verificado con fixture que lo viola. Límite documentado: coma final no detectable sobre strings blanqueados |
| W-02 | atajo a keyframe en `ReaderV1` | cerrada | `094f0a3` | 2026-08-27 | decodifica 4 frames donde antes 6+ (suite `test_reader_v1_seek.js`); matriz idéntica al camino lento. **Desbloquea E-10** |
| W-03 | rollback transaccional de `seek()` v1 | cerrada | `094f0a3` | 2026-08-27 | frame corrupto deja el reader consistente; test incluido |
| W-04 | `_scratch` proporcional, 1 reintento | cerrada | `edc07c4` | 2026-08-27 | **desvío del runbook** (ver bitácora): reservar `_scratchMax` rompía el contrato adaptativo testeado; en su lugar, primer desborde → camino dinámico una vez. 2 pasadas máx (antes 4), RAM proporcional |
| W-05 | fuzzing permanente de `inflate.js` | cerrada | `14dcaa8` | 2026-08-27 | 4000 mutaciones deterministas + casos dirigidos + bomba; ~300 ms, cableado en run_all. **Desbloquea W-06** |
| W-06 | `inflate.js` bit-buffer + tabla | cerrada | `ee1d104` | 2026-08-27 | bit-buffer 32 bits + LUT de 9 bits con fallback canónico que conserva los errores históricos exactos; fuzzing W-05 y todas las suites en verde (`c6e55a8`). Medido en CI (`bench-inflate` vs `90e4b43`): corpus total 3.292→1.418 ms (**2,3×**), perfil gradientes 25,5→72,3 MB/s (**2,8×**) |
| W-07 | cachear buffers de inflate | cerrada | `1856a7c` | 2026-08-27 | árboles lt/dt/código, scratch de longitudes y offs compartidos a nivel módulo; zlib validado sin subarray (decodifica in situ con `d.end`). `test_inflate_alloc.js`: 0 allocaciones tipadas en 50 frames dinámicos, cableado en run_all. CI en verde |
| W-08 | `tile_size` flexible en `ReaderV2` | cerrada | `abb1d65` | 2026-08-27 | validación pasa de `==16` a rango 4..32; test con los seis tamaños del barrido de E-09 sobre grilla 37×29 (tiles de borde) decodificados celda a celda + seis inválidos rechazados. **Habilita S-2** (artefactos de E-09). CI en verde |
| W-09 | una pasada en `_walkRegional` | cerrada | `d0b64eb`+`d216909` | 2026-08-28 | pasada de validación intacta; la de aplicación (`apply=true`) ya no revalida packed/PAL8/MASK ni recorre mapas. Nuevo `tools/bench_reader_v2.js` + workflow `bench-reader`: total 492,9→434,8 ms (−12%), keyframe mixto 615→437 µs/frame (−29%). Corrupción sigue sin dejar matriz a medias (suite existente). CI en verde |
| W-10 | `clearBitset` + atajo <256 en v2 | cerrada | `83924e1` | 2026-08-28 | `clearBytes` por bloques `set(zeroBlock)` (medido 20× en v1); barrido de validación de keyframe RAW/ZLIB salteado con paleta de 256. CI en verde |
| W-11 | limpieza de caminos calientes v2 | cerrada | `fbb38db` | 2026-08-28 | los 8 puntos de la tabla del runbook (uvarint con tabla, `_markDirty` guardado, `_markDirtyCell` sin div/mod en camino caliente, packed sin divisiones, predictores sin recomputar, `_markFull` coherente). Bench vs W-09: total 439,5→293,5 ms (**−33%**; acumulado desde pre-W-09 ≈ −40%). CI en verde |
| W-12 | salto por byte en DELTA_MASK | cerrada | `b8c812d`+`ab96b8c` | 2026-08-28 | ambos readers saltan bytes de máscara en cero. Bench (caso `lmask`, ~5% densidad): 169,4→80,6 µs/frame (**−52%**, sobre el ~29% previsto). CI en verde |
| W-13 | `markRectDirty` en ambos readers | cerrada | `dcce1e7` | 2026-08-28 | API simétrica; v2 promueve a tile con cobertura total conservando la disyunción celda/tile; `test_reader_dirty_rect.js` cableado en run_all. CI en verde. **Desbloquea F7 (S-5: F1 + W-13 cerradas)** |
| W-14 | seguridad y robustez del player | cerrada | `c7a3e01`+`eb9f193`+`47a1b60` | 2026-08-28 | los 8 puntos: CRC v1 ≠ 0 exigido en TV (+ inventario verificado), par requestFrame/cancelFrame con window como receptor, `webglcontextrestored` vuelve a WebGL, `dispose()` en pickRenderer, loop con try/catch que pausa audio, sin parámetro de origen por query, `maxLength` obligatorio en API pública de inflate, árbol Huffman sub-suscripto rechazado (RFC 1951; árbol fijo de distancias corregido a 32 símbolos). Cada punto con su test (página, runtime simulado o stream artesanal). **Cierra F4 (W-01..W-14)**. CI en verde |
| W-15 | camino ASCII de Canvas2D | opcional | | | |

## Sincronización y fases finales

| ID | Qué | Estado | Fecha | Notas |
|---|---|---|---|---|
| S-1 | merge de F0 | cerrada | 2026-08-27 | historial lineal en el snapshot; equivale al merge |
| S-2 | habilitar artefactos `tile_size` ≠ 16 | cerrada | 2026-08-27 | W-08 en verde: `ReaderV2` abre los seis tamaños; E-09 puede generar artefactos |
| S-3 | desbloquear E-10 | cerrada | 2026-08-28 | W-02 estaba en verde desde la sesión 1; E-10 ejecutada y cerrada |
| S-4 | revisión única de formato (F6) + barrido definitivo de `tile_size` | pendiente | | requiere F3 (E-12..E-18) además de F2/F4 ya cerradas |
| S-5 | runtime del overlay (F7) | **habilitada** | 2026-08-28 | F1 y W-13 cerradas; puede arrancar el runtime real del overlay |
| S-6 | validación física (F8) | pendiente | | |

## Bitácora de decisiones de ejecución

| Fecha | Decisión | Motivo |
| 2026-08-27 | Trabajo sobre snapshot con git local y un commit por tarea (IDs E-/W- en el mensaje); los dos carriles comparten historial lineal | no hay acceso al repo privado desde el entorno de trabajo; la bisección por carril se conserva por ID de commit. Al decidirse el mecanismo de continuidad, aplicar `patches/` con `git am` |
| 2026-08-27 | W-04 se implementó como «primer desborde → una pasada dinámica con tamaño real», no como «reservar `_scratchMax`» | el test de `test_reader_safety.js` protege el contrato adaptativo y la evidencia §8 del roadmap (331 KB reales vs 1,6 MB defensivo) muestra que es una decisión deliberada del proyecto; el runbook queda corregido por esta vía |
| 2026-08-27 | E-01 cambia el SHA de artefactos `kmeans-rgb` generados con OpenCV (la paleta ahora sale ordenada); el RGB reconstruido es idéntico | es el efecto buscado del fix de reproducibilidad; el nuevo SHA canónico del sintético queda registrado en P-02 |
| 2026-08-27 | El fixture de `test_benchmark_quality_v1` pasó de flags per-frame a per-scene | declaraba paleta per-frame junto a un DELTA_MASK sin paleta, combinación que la spec no admite (DELTA solo existe con paleta temporal o global) y que el decoder endurecido rechaza |
|---|---|---|
| 2026-08-27 | E-11 y W-15 pasan a opcionales, fuera de los gates de F2 y F4 | E-11: el audio es el 1% del bundle HQ. W-15: los modos `ascii-*` no están en el camino de producción |
| 2026-08-27 | el barrido de `tile_size` de E-09 es provisional; el definitivo va en S-4 | el trellis espacial (E-23) cambia la estadística de colores por tile |
| 2026-08-27 | todo test nuevo se cablea en `tests/run_all.py` y CI en el mismo commit (regla 7) | un test que no corre en la regresión no protege nada |
| 2026-08-27 | la validación física se mantiene al final (F8), sin prueba de humo intermedia | decisión del operador; el acceso al TV real no condiciona el arranque |
| 2026-08-27 | validación **solo por CI**: la máquina de trabajo no tiene Python ni Node; una tarea se cierra con el workflow `regression` en verde sobre su push | decisión del operador (no instalar entornos locales); el repo es privado y el plan Free de Actions alcanza de sobra para el volumen de pushes del proyecto |
| 2026-08-27 | commits directos a `main` (un commit por tarea, ID en el mensaje); las dos ramas del runbook §0.1 quedan sin efecto | decisión del operador; continúa el historial lineal que ya traía el repo |
| 2026-08-27 | se crea `docs/ejecutados/` (archivo de lotes cerrados) y `CLAUDE.md` en la raíz como guía de arranque post-compact | el estado vivo queda corto y navegable; la evidencia de lo cerrado no se relee en cada sesión |
| 2026-08-27 | la referencia HQ pasa a ser **reproducible**: se regenera con el workflow `encode` desde la rama `assets` (fuente TKN-2443) en lugar de congelar un binario irrecuperable | el `clip.asclv` del release v0.2 quedó en una máquina anterior; P-02 exigía congelar antes de tocar el encoder y esta vía lo cumple con SHA verificable en CI |
| 2026-08-27 | el `preview.mp4` del workflow `encode` es **opcional y apagado por defecto** | pregunta del operador: el producto es el `.asclv`; el mp4 es solo QA visual decodificada. La verificación real se hace con `frontend/player.html` sobre el `.asclv` |
| 2026-08-27 | se agrega `frontend/demo-overlay.html`: **demo de laboratorio** del mecanismo INT-001 (glifos E-06 escritos como índices sobre la matriz, celdas restauradas tras cada draw) | pedido del operador de ver números sobre el video ya. NO es el runtime F7 (S-5): usa nearest-index sobre la paleta vigente porque el clip de referencia tiene `reserved=0`. Al implementar F7, esta demo se reemplaza o se recicla como página de prueba |

## Próxima acción

1. **F7 (runtime del overlay)** — S-5 habilitada: reemplazar la demo de laboratorio por el
   runtime real (paleta con `reserved=10`, sidecar ASCLSLOT, `markRectDirty` de W-13).
   Es lo que el operador quiere ver funcionando.
2. Carril E (F3): **E-12** (refit de paleta a la asignación real) y siguientes E-13..E-18.
3. Al re-generar el artefacto de producción: encode con `zopfli=on` + `tile=sweep`
   (la referencia HQ actual con Zopfli es SHA `ebfe2eb4…4b36`, 17.482.270 B).

> El mecanismo de continuidad quedó resuelto: el código de la sesión 1 ya está en `main`
> (`906b010`); los parches de `entrega-2026-08-27/` son solo respaldo histórico.

Regresión al cierre de esta sesión: **125 pruebas Python y 13 suites JavaScript, en verde**
(base: 115 y 11).
