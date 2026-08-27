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
| P-02 | congelar las dos referencias | parcial | `5493455` | 2026-08-27 | `synthetic.baseline` congelada: SHA `c29e7728…5d1d7`. **Pendiente: el HQ.** El clip fuente real ya está local en `inputs/TKN-2443-GANADOR- 15seg-.mp4` (no se commitea); encodearlo y congelarlo requiere un entorno con Python (candidato: workflow manual de CI) |
| P-03 | `tools/bench_ref.py` | cerrada | `bfa2a1f` | 2026-08-27 | fila determinista verificada; PSNR/Oklab con `--source` |
| P-04 | Zopfli opcional | cerrada | `bf8cd58` | 2026-08-27 | documentado en requirements; instalado y verificado en el entorno de trabajo |

## Carril E — encoder

| ID | Tarea | Estado | Commit | Fecha | Notas |
|---|---|---|---|---|---|
| E-01 | `lexsort` en rama OpenCV | cerrada | `6b6b65a` | 2026-08-27 | ambas ramas ordenan vía `_sort_palette_centers`; test de paridad. **El SHA de artefactos kmeans-rgb con cv2 cambia** (nuevo canónico del sintético: `9cc88e55…`); RGB verificado byte-idéntico en 40/40 frames |
| E-02 | endurecer herramientas offline | cerrada | `d3f2bfd` | 2026-08-27 | los 7 puntos del runbook + 6 fixtures de corrupción. El fixture de benchmark declaraba flags no canónicos (per-frame + DELTA) y se corrigió a per-scene. Cierra F0 (encoder) |
| E-03 | `reserved` cableado, default 0 | pendiente | | | |
| E-04 | exclusión del rango reservado (8 funciones) | pendiente | | | |
| E-05 | rects protegidos en dither | pendiente | | | |
| E-06 | horneado de glifos | pendiente | | | |
| E-07 | sidecar `ASCLSLOT` | pendiente | | | cierra F1 |
| E-08 | Zopfli en 5 puntos, simultáneo | pendiente | | | |
| E-09 | `tile_size` parametrizado + barrido provisional | pendiente | | | artefactos ≠16 recién tras S-2 |
| E-10 | keyframes en cortes de escena | bloqueada (W-02) | | | además: habilitar `need_color_descriptor` |
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
| W-06 | `inflate.js` bit-buffer + tabla | pendiente | | | |
| W-07 | cachear buffers de inflate | pendiente | | | |
| W-08 | `tile_size` flexible en `ReaderV2` | pendiente | | | desbloquea artefactos de E-09 |
| W-09 | una pasada en `_walkRegional` | pendiente | | | conservar validación transaccional |
| W-10 | `clearBitset` + atajo <256 en v2 | pendiente | | | |
| W-11 | limpieza de caminos calientes v2 | pendiente | | | |
| W-12 | salto por byte en DELTA_MASK | pendiente | | | |
| W-13 | `markRectDirty` en ambos readers | pendiente | | | desbloquea F7 |
| W-14 | seguridad y robustez del player | pendiente | | | cierra F4 |
| W-15 | camino ASCII de Canvas2D | opcional | | | |

## Sincronización y fases finales

| ID | Qué | Estado | Fecha | Notas |
|---|---|---|---|---|
| S-1 | merge de F0 | cerrada | 2026-08-27 | historial lineal en el snapshot; equivale al merge |
| S-2 | habilitar artefactos `tile_size` ≠ 16 | pendiente | | |
| S-3 | desbloquear E-10 | pendiente | | |
| S-4 | revisión única de formato (F6) + barrido definitivo de `tile_size` | pendiente | | |
| S-5 | runtime del overlay (F7) | pendiente | | |
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

## Próxima acción

1. Carril E: **E-03** (parámetro `reserved`, default 0). Carril W: **W-06** (reescritura
   de `inflate.js`, ahora que W-05 está en verde).
2. Completar **P-02** (HQ): definir el workflow manual de CI que encodea el clip real y
   publica el `.asclv` + SHA-256 como artifact descargable.

> El mecanismo de continuidad quedó resuelto: el código de la sesión 1 ya está en `main`
> (`906b010`); los parches de `entrega-2026-08-27/` son solo respaldo histórico.

Regresión al cierre de esta sesión: **125 pruebas Python y 13 suites JavaScript, en verde**
(base: 115 y 11).
