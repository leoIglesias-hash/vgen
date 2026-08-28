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
| E-12 | refit de paleta a asignación real | cerrada | `09c4261` | 2026-08-28 | opt-in `--palette-refit 0..10` (default 0 = bytes idénticos): Lloyd acotado tras cada paleta con la misma regla de asignación del encode (Oklab exacto/LUT o Pillow), media por `np.bincount`, aceptación solo si baja el error en la métrica del algoritmo; reservadas intactas (INV-4), pal_img solo-base (INV-3); enhebrado global/block/adaptive/per-frame (incl. median-cut). Bench 768 `overlay=off` (Instancia 018): refit 3 → 35,39 dB / 0,00734; **refit 5 → 35,46 dB / 0,00732 y −0,59 % bytes** (17.379.859 B, `adef9e53…c05bb`) vs 34,29 / 0,00793 de P-02; fondo re-encodeado e instalado en `outputs/`. CI en verde |
| E-13 | Lloyd en dominio uint8 | cerrada | `a64c7ce` | 2026-08-28 | `_closing_lloyd_uint8` en `build_perceptual_palette`: itera el tramo final (asignar → promediar en Oklab → gamut map → redondear → reparar duplicados) restringido a paletas sRGB representables, aceptando solo si baja la inercia ponderada (nunca degrada; orden de entradas conservado → alineación temporal válida). Opt-in `--palette-uint8-refine 0..10`, solo kmeans-oklab. Bench 768 con refit 5 + refine 3 (Instancia 019, `a95d0bbc…acbf`): PSNR igual, Oklab −0,5 % (0,00728), bytes +0,36 % → el producto sigue con refit 5 solo. CI en verde |
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

## Carril F7 — runtime del overlay (S-5)

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| F7-1 | estado y orden por frame (§9.2) | cerrada | `b5775d0`+`34f72b6` | 2026-08-28 | `frontend/overlay.js`: restaurar → seek → guardar/pintar/marcar; control negativo en test (saltear el paso 1 diverge). CI en verde |
| F7-2 | API ES5 attach/setField/setValues/clearField/clear/detach | cerrada | `b5775d0`+`34f72b6` | 2026-08-28 | attach devuelve null ante meta o bundle inválido (verifica cola 246..255 de la paleta contra `reserved_rgb`); todo-o-nada; sin allocaciones en el loop estable (identidad de buffers testeada). `test_overlay_runtime.js` sobre ambos readers |
| F7-3 | canal de datos (5 pasos, serial monotónico, backoff) | cerrada | `df6229a` | 2026-08-28 | `frontend/datachannel.js` + `test_overlay_datachannel.js`: corpus §13 completo; backoff exponencial (techo 5 min) solo ante error de red; el serial solo avanza con carga aceptada |
| F7-4 | referencia Python byte-idéntica | cerrada | `35a54b3` | 2026-08-28 | `backend/overlay_ref.py` + fixtures cruzados: clip real del encoder (`reserved=10`, 246..255), 8 frames byte-idénticos Python/JS con cargas en f0 y f3; `clear()` vuelve al video base exacto |
| F7-int | integración de producto | cerrada | `7954bc8`+`243600b`+`fe055de` | 2026-08-28 | `make_clip --reserved 10` (RGB canónicos de `overlay_palette`), panel de 20 números (`tools/make_panel.py` + `backend/overlay_panel.py`), input `overlay` en workflow `encode` (publica `clip.slots`), `live-player.html` reemplaza la demo de laboratorio, y el dither excluye los rects del panel (`protect_panel`, INT-001 §11) |

## Carril INT-003 — parches genéricos de imagen (vía corta)

Diseño cerrado con el operador (D1..D6, 2026-08-28) en
[`DISENO-PARCHES-GENERICOS.md`](DISENO-PARCHES-GENERICOS.md); tareas en
`RUNBOOK-IMPLEMENTACION.md` §4-INT-003. La ruleta va con `ASCLVID3` (F6/S-4).

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| INT-003-A | reserva ampliada a 32 (224..255) | cerrada | `7156fd9` | 2026-08-28 | cola F7 (246..255) bit-idéntica dentro de la tabla de 32; `--reserved` acepta 0/10/32; costo medido en el sintético: −0,47 dB PSNR y archivo ~5% menor (Instancia 015) |
| INT-003-B | ASCLSLOT v2 Python (parches heterogéneos, kind, presupuestos) | cerrada | `735eee3` | 2026-08-28 | `build_v2`/`_validate_v2` en `make_slots.py`; presupuesto 5% por frame (barrido de eventos) + RAM 25%; solape espacial solo con ventanas disjuntas; corpus con un rechazo por regla |
| INT-003-C | slots.js espejo v2 | cerrada | `5e03091` | 2026-08-28 | corpus completo generado por Python (35 fixtures) y verificado byte a byte en JS con el mismo veredicto/mensaje; despacho por byte de versión, v1 intacta |
| INT-003-D | runtime v2 + referencia Python (NONE, elección, presencia) | cerrada | `8c3e55f` | 2026-08-28 | `overlay.js` normaliza v1/v2 a una sola forma interna (v1 byte-idéntico, suite F7 sin tocar); `values` u16 con `NONE=65535` (no pinta, no guarda base, no marca sucio); fixtures cruzados con clip real `reserved=32`: 8 frames byte-idénticos; `datachannel.js` sin cambios (longitud v2 vía `digitCount`) |
| INT-003-E | bake_patches.py (fuente libre + PNG → reserva 32) | cerrada | `7f0e3d1` | 2026-08-28 | texto con cualquier TTF y color + PNG con alpha → nearest Oklab en 224..254, alpha→255; determinista; los parches horneados alimentan un sidecar v2 válido |
| INT-003-F | integración: workflow `overlay=patches`, live-player, cierre de etapa | cerrada | `da28408` | 2026-08-28 | `make_patch_pack.py` (panel v2 + 3 números grandes serif por tercios + palabra de elección), `live-player.html` paramétrico, workflow `overlay=off/panel/patches`. Clip HQ `patches` publicado (run 33176566955): 16.465.367 B SHA `c315a13a…8e63` + sidecar v2 15.511 B SHA `678b392d…2c56`; verificado en navegador (Instancia 016), player local levantado |

## Carril INT-004 — texto nativo en el mismo canvas

Pedido del operador (2026-08-28, tras ver la demo INT-003): el texto se ve
pixelado dentro de la matriz (el piso físico es la celda) — se dibuja nativo
con Canvas2D sobre el MISMO canvas, después del frame. Diseño en
`DISENO-PARCHES-GENERICOS.md` §10; tareas en el runbook §4-INT-004.

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| INT-004-A | `frontend/textlayer.js` (create/setText/markDirty/draw, ES5, todo-o-nada) | cerrada | `21df177` | 2026-08-28 | `ASCILINETextLayer.create(items)` todo-o-nada; `setText` valida y conserva (INV-7); `markDirty` marca solo cajas con texto dentro de grilla; `draw` stroke→fill con `maxWidth` de la caja y cache de fuente/anclajes por `cellPx` (cero allocaciones en el camino caliente); suite `test_textlayer.js` cableada en `run_all.py`; gate ES5 en verde |
| INT-004-B | integración en live-player (Canvas2D cuando hay texto; demo lado a lado con la matriz) | cerrada | `76ffe45` + fix `07bc0da` | 2026-08-28 | con sidecar v2, los campos de dígitos con slots ≥20 celdas se espejan como texto serif con borde al costado de cada posición; todo payload aceptado (botón o canal) alimenta matriz Y texto (wrap de `setValues`/`clear`); `pickRenderer` va a Canvas2D con `pixelScale=zoom` (backing real cols·s×rows·s: put chico + `drawImage` del canvas sobre sí mismo — sin segundo canvas); orden por frame `seekTo → markDirty(texto) → renderer.draw → textLayer.draw` cubierto por `test_live_player_page.js`; `test_frontend_renderers.js` cubre `pixelScale` (default 1 idéntico al histórico) |

## Carril INT-006 — fondo sin reserva + texto standalone

Pedido del operador (2026-08-28, tras ver la demo INT-004): re-procesar el
fondo SIN la reserva de números de matriz (ya no sirve: el texto es nativo),
con la máxima calidad de las herramientas existentes, dejando las fuentes
interviniendo como ahora; después pasa una imagen para probar la
intervención gráfica. Tareas en el runbook §4-INT-006.

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| INT-006-A | fondo HQ `overlay=off` (768 y candidato 960) + registro + outputs limpio | cerrada | (solo dispatch) | 2026-08-28 | **768 reproduce byte a byte la referencia P-02** (`ebfe2eb4…4b36`, 17.482.270 B; PSNR 34,29 / Oklab 0,00793, run 33193293258); **960** `31348a83…5688` (25.003.004 B; 34,40 / 0,00776, run 33193299286) queda como dato — el 768 sigue de producto (valores del operador). `outputs/` limpio: clip 768 con SHA verificado, `clip.slots`/`data.txt` borrados, `logo.png` queda. Registro: **Instancia 017** |
| INT-006-B | `textfeed.js` + live-player standalone (texto sin sidecar, sim + canal) | cerrada | `49e2b4a` + fix `2c81856` | 2026-08-28 | `ASCILINETextFeed.create(capa,campos)` → `digitCount`/`setValues` todo-o-nada (misma interfaz que consume `datachannel.js`, sin cambios); sin overlay de matriz el player declara 3 campos de 2 dígitos por tercios (dimensionados por cols/rows) y botón+canal los alimentan; suite `test_textfeed.js` cableada; el fix quita un backtick de comentario que volteó el gate ES5 del test de página (CI rojo → verde en el siguiente push) |
| INT-006-C | intervención de la imagen del operador (decisión D7) | cerrada | `3e51ce8` | 2026-08-28 | el operador entregó `inputs/logonuevo150.png` (logo TeleKino) y **D7 se resuelve en (a) nativa**: `drawImage` del PNG (`outputs/logo.png`, opcional) sobre el MISMO canvas después del texto, caja en celdas (cols/4, aspecto preservado, esquina sup. der.) marcada sucia por frame; solo activa con texto declarado (renderer ya Canvas2D); 404 = nada cambia (INV-7); verificado en navegador sobre el clip de parches (play/sim/zoom/clear sin errores de consola); (c) INT-005/época sigue como definitivo para la ruleta |

## Sincronización y fases finales

| ID | Qué | Estado | Fecha | Notas |
|---|---|---|---|---|
| S-1 | merge de F0 | cerrada | 2026-08-27 | historial lineal en el snapshot; equivale al merge |
| S-2 | habilitar artefactos `tile_size` ≠ 16 | cerrada | 2026-08-27 | W-08 en verde: `ReaderV2` abre los seis tamaños; E-09 puede generar artefactos |
| S-3 | desbloquear E-10 | cerrada | 2026-08-28 | W-02 estaba en verde desde la sesión 1; E-10 ejecutada y cerrada |
| S-4 | revisión única de formato (F6) + barrido definitivo de `tile_size` | pendiente | | requiere F3 (E-12..E-18) además de F2/F4 ya cerradas |
| S-5 | runtime del overlay (F7) | cerrada | 2026-08-28 | F7-1..F7-4 + integración en verde; gates de INT-002 cubiertos por la regresión (Instancia 014). Los dos gates físicos (costo p95 y MEM-001 en TV) se miden en F8-2/F8-4, donde el plan ya los prevé con y sin overlay |
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
| 2026-08-28 | S-5 se cierra con los gates de INT-002 verificables en CI; el costo p95 y MEM-001 (físicos, en TV) se difieren a F8-2/F8-4 | esos dos gates requieren el hardware real; el plan ya prevé medirlos allí con y sin overlay. La RAM auxiliar en CI es la declarada (3.880 B) por construcción y con identidad de buffers testeada |
| 2026-08-28 | el runtime F7 usa el **sidecar** (fase §7.1); la migración a `ASCLVID3` queda para F6 (S-4) como estaba planificado | permite rediseñar el panel sin re-encodear; los readers actuales rechazan ASCLVID3 limpiamente |
| 2026-08-28 | `make_clip --reserved 10` activa también la protección del panel en el dither (`protect_panel`); los RGB reservados canónicos viven en `backend/overlay_palette.py` y la geometría del panel en `backend/overlay_panel.py` (única fuente para sidecar y dither) | INT-001 §11: el base bajo el panel no deriva; una sola fuente de verdad evita que sidecar y exclusión se desalineen |
| 2026-08-28 | El operador pide generalizar el overlay a **parches de imagen arbitrarios** (tipografía libre, random de momento/posición, ruleta que coincide con el resultado). Queda como propuesta INT-003 en `DISENO-PARCHES-GENERICOS.md`, con las decisiones D1..D6 abiertas | pedido posterior al cierre de F7; el runtime por frame no cambia (pinta índices y restaura bytes) — lo que se generaliza es metadata, horneado y canal. No arrancar sin resolver D1..D6 con el operador |
| 2026-08-28 | **D1..D6 resueltas con el operador**: D1 = ampliar la reserva a 32 (224..255, las 10 actuales conservan índice y RGB); D2/D3/D6 = vía corta ahora con presupuesto 5% **por frame** + techo de RAM 25%, ruleta con `ASCLVID3` (F6); D4 = slots candidatos fijos (solape espacial permitido solo con ventanas disjuntas); D5 = canal todo-numérico con dígito de presencia para campos de elección | respuestas del operador en sesión; el diseño concreto (spec ASCLSLOT v2, colores 224..245, wire) quedó en `DISENO-PARCHES-GENERICOS.md` y las tareas INT-003-A..F en el runbook de implementación |
| 2026-08-28 | **Revisión post-demo con el operador**: los TEXTOS pasan a dibujarse nativos con Canvas2D sobre el MISMO canvas (INT-004) — un solo elemento canvas, la regla «jamás un segundo canvas ni DOM overlay» se mantiene, pero el texto ya no vive en la matriz (no byte-verificable; propiedad documentada). Cuando hay texto nativo se elige el renderer Canvas2D (el piso): WebGL no gana funciones que Canvas2D no tenga | el piso físico de nitidez dentro de la matriz es la celda (~65x90 px un dígito de 26x36 en 1080p) y el horneado v2 sin antialias lo evidencia; el operador preguntó por el mismo canvas y es viable. La matriz queda para GRÁFICOS |
| 2026-08-28 | La caída de calidad de la reserva de 32 (Instancias 015/016) se resuelve a futuro con **INT-005 (parches por época, F6)**: el elemento interventor se declara ANTES del encode con su ventana temporal y se cuantiza contra las paletas de las épocas de esa ventana — paleta completa sin reservar entradas. Idea del operador. Mientras tanto la reserva 32 sigue vigente y E-12 recupera calidad de la base | «al procesar el video debería procesarse al mismo tiempo la fracción que interviene… le diríamos al procesador que va del minuto tal al tal» — evita el costo permanente de paleta y es el modelo natural para la ruleta en `ASCLVID3` |
| 2026-08-28 | **Desvío técnico de INT-004-B**: en modo PIXEL el backing store del Canvas2D era cols×rows (el zoom era solo CSS), así que el texto nativo se habría pixelado igual. Se agrega `renderer.pixelScale` (opt-in del player, default 1 byte-idéntico): backing cols·s×rows·s, frame chico con `putImageData` + un `drawImage` del canvas **sobre sí mismo** (la spec exige snapshot del origen) — sin segundo canvas, la regla se mantiene. Con escala el put es siempre completo y el player marca TODAS las cajas de texto declaradas por frame (no solo las con texto) para que borrar un texto no deje fantasma | sin esto INT-004 no entregaba nitidez real; el costo (put completo + blit por frame) es del live-player de demo — `tv-player.html` no se toca y con `pixelScale=1` el camino histórico es idéntico |
| 2026-08-28 | **Fix post-verificación en navegador** (`07bc0da`): «Limpiar panel» había pasado de `renderer.draw` directo a `drawFrame` y los dígitos de la matriz persistían tras clear — `clear()` restaura cells y deja los rects marcados, pero el `seek` del mismo frame dentro de `drawFrame` resetea los dirty sets y perdía esos marks (canvas/rgba viejos). Se dibuja de nuevo directo, marcando además las cajas de texto | encontrado probando el player en navegador antes de entregar; el orden por frame normal no cambia (los marks del overlay ocurren en `afterSeek`, después del seek); test de página nuevo fija el camino sin re-seek |
| 2026-08-28 | La raíz de `tools/serve-local.ps1` pasa de `player.html` a `live-player.html` (`c9ea17e`) | el operador abrió `localhost:8123/` y vio el player viejo de archivos; lo que se revisa al cierre de etapa es el runtime real |
| 2026-08-28 | **D7 resuelta en (a) — imagen nativa** (`3e51ce8`): el operador entregó el logo (`inputs/logonuevo150.png`) y la prueba se hace con `drawImage` sobre el MISMO canvas después del texto, como recomendaba el diseño §11 — cero costo de paleta, coherente con la decisión del texto (el gráfico deja de ser byte-verificable: misma propiedad documentada). La opción (c) INT-005/época sigue como definitiva para la ruleta; (b) reserva 32 queda disponible si el operador la pide al ver el resultado | «luego te paso una imagen y probamos procesarla»: la vía (a) prueba ya sin re-encodear ni pagar −0,24 dB; el operador valida al ver el player |
| 2026-08-28 | CI rojo en `49e2b4a` (INT-006-B): un backtick en un comentario del script inline volteó el gate ES5 de `test_live_player_page.js`; fix hacia adelante en `2c81856` (verde) | el gate barre `let/const/class/=>/backtick` también dentro de comentarios: los comentarios del inline no llevan backticks |
| 2026-08-28 | **Nueva dirección del operador (post-demo INT-004)**: «volver a procesar el video de fondo… está con la intervención de píxeles con números y eso ya no nos sirve… procesalo para que tenga más calidad, la mayor calidad posible con las herramientas que fuimos desarrollando y dejamos las fuentes activas interviniendo como ahora; luego te paso una imagen y probamos procesarla». Nace el carril **INT-006** (A: fondo `overlay=off` con bench 768 vs 960; B: texto standalone sin sidecar vía `textfeed.js`; C: imagen → decisión D7 nativa/reserva/época) | con el texto nativo, la reserva de 32 solo servía a los números de matriz: quitarla recupera los 256 colores de la base (−0,24 dB recuperados) sin perder la intervención. E-12 pasa a ejecutarse DESPUÉS de INT-006 y amerita re-encode del fondo al cerrar |
| 2026-08-28 | **E-12 cierra con el refit 5 como fondo de producto**: el 768 con `--palette-refit 5` (35,46 dB / Oklab 0,00732 / 17.379.859 B) gana +1,17 dB y −0,59 % de bytes sobre P-02, y supera al 960 ultra sin refit con 31 % menos bytes; se instala en `outputs/` (SHA `adef9e53…c05bb` verificado) cumpliendo el «al cerrar E-12, re-encodear el fondo» en el mismo cierre. El flag queda **opt-in (default 0)** para preservar la reproducibilidad byte a byte de las referencias históricas; el workflow lo pasa por `extra` | la aceptación monótona en la métrica del algoritmo garantiza que el refit nunca degrada (propiedad testeada en los 4 algoritmos); refit 3 quedó también medido (35,39 dB, `514be81e…`) por si el costo de encode importara. La comparación 768 vs 960 de la Instancia 017 queda desactualizada: re-medir el 960 con refit antes de reabrirla |
| 2026-08-28 | **E-13 medido y NO adoptado en el producto**: el cierre de Lloyd uint8 (`--palette-uint8-refine 3` sobre refit 5) deja PSNR igual, baja Oklab −0,5 % y sube bytes +0,36 % (Instancia 019, `a95d0bbc…acbf`); el fondo sigue con refit 5 solo. La inercia de muestra baja siempre por construcción (gate de aceptación); la ganancia sobre el clip real es marginal | mecánica lista y testeada para cuando convenga (S-4 reevalúa combinaciones con el trellis de F5); mantener el default en 0 preserva la reproducibilidad de las referencias |

## Próxima acción

1. **Carril E (F3): E-14** (paleta sobre todos los píxeles en dos
   pasadas — `_weighted_samples` sin el límite de 65.536 muestras y sin
   materializar el video completo en RAM; medir RSS máximo con
   graphic-ultra). Siguen E-15..E-18. La **ruleta** sigue siendo INT-005
   en F6/S-4. F5 y F8 sin cambios.
2. Decisión abierta para el operador: el fondo ahora es el **768 refit 5**
   (35,46 dB), que supera al 960 ultra sin refit (34,40 dB) con 31 %
   menos bytes — si retoma la idea del 960, hay que re-medirlo con
   `--palette-refit 5` antes de comparar.
3. Referencias HQ vigentes: **producto = 768 refit 5 `adef9e53…c05bb`
   (17.379.859 B, instalada en `outputs/`, run 33203086375)** · 768
   refit 5 + uint8-refine 3 `a95d0bbc…acbf` (17.442.264 B, Oklab 0,00728,
   run 33207479295, E-13 medido sin adoptar) · 768
   refit 3 `514be81e…a01aff` (17.425.768 B, run 33203084602) · sin refit
   determinista P-02 `ebfe2eb4…4b36` (17.482.270 B, sigue reproducible
   con el flag en 0) · ultra 960 sin refit `31348a83…5688` (25.003.004 B,
   run 33193299286, superado) · panel v1 `7da584f1…5a51d` (17.197.813 B)
   · parches v2 `c315a13a…8e63` (16.465.367 B) + sidecar `678b392d…2c56`
   (demo de INT-003/004).

> El mecanismo de continuidad quedó resuelto: el código de la sesión 1 ya está en `main`
> (`906b010`); los parches de `entrega-2026-08-27/` son solo respaldo histórico.

Regresión al cierre de esta sesión: **219 pruebas Python y 26 suites JavaScript, en verde**
(base: 115 y 11). Último commit de tarea: `a64c7ce` (E-13, CI verde confirmado
2026-08-28); `outputs/clip.asclv` = fondo 768 **refit 5** (`adef9e53…c05bb`,
SHA verificado) servido por el player standalone en `localhost:8123`.
