# Plan unificado — optimización de tiers e intervención matricial

Estado: propuesta de planificación, 2026-08-27. Sin implementación.

Ordena en una sola cola los 19 ítems de optimización auditados y los 7 pasos de
`DISENO-INTERVENCION-MATRICIAL.md`, de modo que ninguna tarea deba rehacerse por una
decisión tomada después.

Documentos que este plan respeta y no reemplaza:

| Tema | Documento |
|---|---|
| principios e invariantes | `PLAN-IMPLEMENTACION-OPTIMIZACION.md` |
| backlog, dependencias y gates vigentes | `HOJA-DE-RUTA-TECNICA-V2.md` |
| formato v1/v2 | `ASCL-format-spec.md` |
| intervención matricial | `DISENO-INTERVENCION-MATRICIAL.md` |
| decisiones append-only | `REGISTRO-DE-PRUEBAS-Y-DECISIONES.md` |

## 0. Método

Tres reglas que gobiernan todo el plan:

1. **Una sola revisión de formato.** Todo cambio que altere bytes interpretados por el
   reader se agrupa en una única revisión. No se despliegan tres versiones de decoder
   sucesivas a equipos físicos.
2. **Una medición por cambio.** Cada tarea que altera el artefacto se mide aislada contra
   la referencia congelada de F0. Un cambio sin su fila en el registro no avanza.
3. **Dos carriles en paralelo.** El carril de encoder (F1, F2, F3, F5) y el de frontend
   (F4) son independientes hasta F7 y avanzan simultáneamente. Decisión tomada el
   2026-08-27. Es lo más rápido en total y tiene un costo asumido: con dos frentes de
   cambio abiertos, aislar la causa de una regresión es más difícil. Se compensa con la
   disciplina de la regla 2 y con una condición adicional: **ningún commit mezcla los dos
   carriles**, de modo que toda regresión pueda bisecarse por carril.

## 1. Colisiones detectadas

Esta sección es el motivo del plan. Cada colisión implica un orden obligatorio o una fusión
de tareas.

### C-1 — La reserva de paleta precede a todo trabajo de paleta

El refit de Lloyd, el cierre en uint8, la estabilidad temporal y la reparación de
duplicados reasignan entradas de paleta. Escritas sin conocer el rango reservado
`246..255`, hay que rehacerlas al agregar el overlay.

**Consecuencia:** el cableado del parámetro `reserved` atraviesa el encoder en F1, con
valor `0` por defecto y comportamiento idéntico al actual. Recién después se toca la
calidad de paleta.

### C-2 — Alargar el GOP sin el atajo a keyframe empeora el atraso

Poner keyframes en los cortes de escena permite GOPs más largos entre cortes. Pero
`reader.js` no salta hacia adelante: una cadena delta más larga hace que un TV atrasado
decodifique más frames por cada seek, exactamente el fallo medido (90 frames decodificados
donde el óptimo eran 11).

**Consecuencia:** los keyframes por corte de escena **no pueden desplegarse antes** que el
atajo a keyframe del reader v1. Si se hace al revés, se degrada la reproducción en el
equipo más lento justo mientras se celebra un ahorro de bytes.

### C-3 — Zopfli debe aplicarse a los dos lados de la comparación v1/v2

`ascl_v2.transcode_ascl_bytes` reemplaza un payload v1 solo si el candidato v2 es
estrictamente menor. Si el payload v1 heredado se comprime con Zopfli y el candidato v2
con `zlib -9`, v2 pierde por una asimetría de herramienta, no de representación.

**Consecuencia:** Zopfli entra simultáneamente en `encoder.py`, `ascl_v2.py` y
`regional_codec_v2.py`. No se despliega en un solo archivo.

### C-4 — "Paleta sobre todos los píxeles" y "modo global no cabe en RAM" son la misma tarea

`_weighted_samples` limita a 65.536 muestras de unos 12 frames; `--palette global`
materializa el video entero en RAM (~2,8 GB en 90 s de `graphic-ultra`). La solución de
ambas es la misma: dos pasadas con agregación de colores únicos. Un clip de 900 frames a
320x180 tiene ~52 M píxeles pero típicamente menos de 200 k colores únicos.

**Consecuencia:** se fusionan en una sola tarea. Resolver una sin la otra deja el trabajo
a medio hacer.

### C-5 — Trellis no puede puntuar con el compresor final

El trellis evalúa millones de candidatos. Zopfli cuesta unas cien veces más que `zlib -9`
por invocación; ponerlo dentro del bucle no es "lento", es inviable, y el permiso de gastar
CPU offline no lo cambia.

**Consecuencia:** jerarquía explícita de costo — proxy barato (celdas cambiadas, entropía
local) para explorar, `zlib -9` para elegir entre finalistas, Zopfli **solo** sobre el
ganador ya elegido.

### C-6 — El orden del pipeline de cuantización debe fijarse antes del trellis

Hoy el orden es cuantizar, ditherear y recién después aplicar `--threshold`, que revierte
celdas al valor previo y rompe parcialmente el patrón Bayer de forma distinta en cada
frame. El trellis ocupa conceptualmente el mismo lugar que `--threshold` y agravaría la
interacción.

**Consecuencia:** se congela el orden canónico antes de implementar el trellis, y
`--threshold` queda absorbido como caso degenerado en lugar de convivir con él.

### C-7 — El corpus de fuzzing precede a la reescritura de `inflate.js`

`inflate.js` es el 41-43% del tiempo de decode y su reescritura con bit-buffer y tabla de
lookup toca el componente más crítico del frontend. La auditoría corrió 20.000 mutaciones
sin hangs ni accesos fuera de rango, pero ese corpus fue transitorio.

**Consecuencia:** el harness de fuzzing se incorpora como test permanente **antes** de
tocar una línea del inflate, no después.

### C-8 — El gate de sintaxis ES5 precede al trabajo de frontend

`test_frontend_compatibility.js` no detecta `TypedArray.prototype.fill/copyWithin/slice`,
`Object.keys`, `Array.isArray`, `Math.trunc/imul`, `Uint8ClampedArray`, `JSON.*` ni comas
finales. El código está limpio hoy; el gate no impediría la regresión mañana, justo cuando
se reescriben inflate, readers y overlay.

**Consecuencia:** ampliar la lista negra es la primera tarea del carril de frontend.

## 2. Fases

Leyenda de columnas: **Δbytes** = altera el artefacto y exige medición aislada;
**dec** = toca el decodificador desplegado en el TV.

### F0 — Congelar la base

Nada de esto altera calidad ni formato. Va primero porque fija la referencia contra la que
se mide todo lo demás y elimina una fuente de no reproducibilidad.

| ID | Tarea | Archivo | Δbytes | dec |
|---|---|---|:--:|:--:|
| F0-1 | Congelar clip de referencia, hash, parámetros y commit | registro | — | — |
| F0-2 | `_kmeans_rgb_palette` no ordena los centros en la rama OpenCV | `encoder.py:271-283` | sí | no |
| F0-3 | `iter_video_frames` acepta `src_fps` NaN o absurdo | `encoder.py:681` | no | no |
| F0-4 | `encode_image` ignora `palette_mode` en silencio | `encoder.py:743` | no | no |
| F0-5 | `_initial_centers` puede devolver centros duplicados | `perceptual_palette.py:347` | sí | no |
| F0-6 | `ascl_decode.py` calcula CRC y no aborta; infla sin cota; no valida índices | `ascl_decode.py:101-185` | no | no |
| F0-7 | `ascl_bundle` lee el archivo completo sin cota; `_publish_mode` no cubre `PermissionError` | `ascl_bundle.py:35,100` | no | no |
| F0-8 | `ascl_decode.write_mp4` hardcodea `ffmpeg` | `ascl_decode.py:218` | no | no |

F0-2 es la más importante de la fase: el mismo input produce archivos distintos según haya
OpenCV o no, y `kmeans-rgb` es el default de `make_clip.py`. Cualquier medición tomada
antes de este arreglo compara contra una base que no es reproducible.

**Gate F0:** dos corridas del clip de referencia en entornos con y sin OpenCV producen
SHA-256 idéntico. Regresión completa en verde.

### F1 — Reserva de paleta y regiones protegidas

Habilita INT-001 y desbloquea F3 y F5. Con `reserved = 0` el comportamiento es
byte-idéntico al actual, así que la fase no altera ningún artefacto existente.

| ID | Tarea | Archivo | Δbytes | dec |
|---|---|---|:--:|:--:|
| F1-1 | Parámetro `reserved` cableado por todo el encoder, default `0` | `encoder.py`, `perceptual_palette.py` | no | no |
| F1-2 | Exclusión en las ocho funciones de `DISENO-INTERVENCION-MATRICIAL.md` §4.2 | ídem | no | no |
| F1-3 | INV-3: el video base no elige índices reservados | `encoder.py:498` | sí (solo con overlay) | no |
| F1-4 | Rects protegidos como máscara adicional del dither | `dither.py:696-726` | no | no |
| F1-5 | Horneado determinista de glifos desde fuente real | herramienta nueva | — | — |
| F1-6 | Generador y validador de sidecar `ASCLSLOT` (Python y JavaScript) | herramienta nueva | — | no |

**Gate F1:** con `reserved=0`, SHA-256 idéntico a F0. Con `reserved=10`, ninguna celda base
usa índice `>= 246` en las cuatro estrategias de paleta y en todas las épocas de un clip
adaptativo. Cada restricción del validador tiene su fixture negativo.

### F2 — Bytes sin riesgo

Encoder puro salvo una línea del reader. Ninguna decisión de esta fase depende de la
paleta ni del overlay.

| ID | Tarea | Archivo | Δbytes | dec |
|---|---|---|:--:|:--:|
| F2-1 | Zopfli en los cinco puntos de compresión, simultáneo (C-3) | `encoder.py`, `ascl_v2.py`, `regional_codec_v2.py` | sí | no |
| F2-2 | Búsqueda exhaustiva de `tile_size` en `{4,8,12,16,24,32}` | `ascl_v2.py:57,137,462` | sí | no |
| F2-3 | Relajar el rechazo de `tile_size != 16` | `reader-v2.js:176` | no | **sí** |
| F2-4 | Keyframe forzado en cada corte de escena detectado; GOP variable | `encoder.py:903,1088` | sí | no |
| F2-5 | Exponer `--audio-bitrate`, `--audio-mono`, `--audio-samplerate` | `encoder.py:656` | sí | no |

F2-3 es un cambio de una línea, pero es el único de la fase que se despliega al TV: entra
en la revisión única de formato junto con F6.

F2-4 **no se despliega antes que F4-2** (C-2).

F2-5 tiene impacto marginal en el perfil HQ —el audio es el 1% del bundle de referencia— y
relevante en perfiles de 320 columnas. Se incluye por completitud, no por prioridad.

**Gate F2:** cada tarea con su fila de medición aislada. `bytes(v2) <= bytes(v1)` sigue
verificado. La distribución de tags del clip de referencia se registra antes y después.

### F3 — Calidad de paleta y dithering

Todo respeta el rango reservado desde el primer día gracias a F1.

| ID | Tarea | Archivo | Δbytes | dec |
|---|---|---|:--:|:--:|
| F3-1 | Refit de paleta a la asignación real (`bincount`), 3-5 iteraciones | `encoder.py:498` | sí | no |
| F3-2 | Cerrar Lloyd en dominio uint8 tras el redondeo a sRGB | `perceptual_palette.py:472-521` | sí | no |
| F3-3 | Paleta sobre todos los píxeles por agregación de únicos, en dos pasadas (C-4) | `perceptual_palette.py:234`, `encoder.py:829` | sí | no |
| F3-4 | Estabilidad temporal para los cuatro algoritmos, no solo `kmeans-oklab` | `encoder.py:286` | sí | no |
| F3-5 | `PairLUT` exacto por píxel en lugar de RGB555 | `dither.py:287-344,721` | sí | no |
| F3-6 | Presupuesto de dither en **bytes** además de celdas (`V1-OPT-02` del backlog) | `dither.py` | sí | no |

F3-4 corrige algo que hoy afecta al camino por defecto: `make_clip.py` usa `kmeans-rgb`,
que no propaga `previous_palette`, de modo que la paleta se recrea de cero en cada bloque.

F3-6 es el ítem que ya figuraba pendiente en el backlog vigente; se integra acá porque
comparte código con F3-5.

**Gate F3:** PSNR RGB y error Oklab por tarea contra la referencia. Ninguna tarea que
mejore calidad puede aumentar bytes por encima de un techo acordado sin decisión explícita.
Determinismo verificado en dos corridas.

### F4 — Frontend: fluidez, memoria y seguridad

Carril paralelo a F1-F3. No depende del encoder.

| ID | Tarea | Archivo | Δbytes | dec |
|---|---|---|:--:|:--:|
| F4-0 | Ampliar la lista negra del gate ES5 (C-8) | `tests/test_frontend_compatibility.js:62` | — | — |
| F4-1 | Incorporar el harness de fuzzing como test permanente (C-7) | `tests/` | — | — |
| F4-2 | Atajo a keyframe hacia adelante en `ReaderV1` | `reader.js:461` | no | **sí** |
| F4-3 | Rollback transaccional de `seek()` en `ReaderV1` | `reader.js:449-478` | no | **sí** |
| F4-4 | Dimensionar `_scratch` con el `_scratchMax` ya calculado | `reader.js:200,281` | no | **sí** |
| F4-5 | `inflate.js` con bit-buffer de 32 bits y tabla de lookup de 9 bits | `inflate.js:121-148` | no | **sí** |
| F4-6 | Cachear buffers de `inflate` a nivel módulo | `inflate.js:31,210,247` | no | **sí** |
| F4-7 | Una sola pasada en `_walkRegional` | `reader-v2.js:736` | no | **sí** |
| F4-8 | Recuperar `clearBitset` con `set(zeroBlock)` en v2 | `reader-v2.js:99,756` | no | **sí** |
| F4-9 | Recuperar el atajo `paletteEntries < 256` en v2 | `reader-v2.js:402,721` | no | **sí** |
| F4-10 | Guardar el barrido de 256 celdas de `_markDirty` tras `_dCellCount` | `reader-v2.js:324` | no | **sí** |
| F4-11 | Eliminar div/mod por píxel en los bucles calientes | `reader-v2.js:349,420,537,643` | no | **sí** |
| F4-12 | Salto por byte en el walk de DELTA_MASK | `reader.js:419`, `reader-v2.js:606` | no | **sí** |
| F4-13 | `markRectDirty(x,y,w,h)` simétrico en ambos readers | `reader.js`, `reader-v2.js` | no | **sí** |
| F4-14 | Exigir CRC distinto de cero en v1 desde el player | `tv-player.html` | no | **sí** |
| F4-15 | Emparejar `requestFrame`/`cancelFrame` como par | `tv-player.html:107`, `player.html:76` | no | **sí** |
| F4-16 | Manejar `webglcontextrestored` | `tv-player.html:262` | no | **sí** |
| F4-17 | `player.html`: `dispose()` de renderer, sin `?src=`, captura en el loop | `player.html:109,198,257` | no | **sí** |
| F4-18 | `dirtyCount = 0` cuando `dirtyFull` | `reader-v2.js:369` | no | **sí** |
| F4-19 | `maxLength` obligatorio en la API pública de `inflate` | `inflate.js:15` | no | **sí** |
| F4-20 | Rechazar árbol Huffman sub-suscripto (RFC 1951) | `inflate.js:45` | no | **sí** |
| F4-21 | Camino ASCII de Canvas2D: cachear colores y glifos, respetar dirty | `render-canvas2d.js:134` | no | **sí** |

F4-2 es la corrección de estabilidad más importante del proyecto y **bloquea F2-4** (C-2).

F4-21 solo afecta a los modos `ascii-*`; el camino `pixel` de producción no lo usa. Va
último dentro de la fase.

**Gate F4:** CRC de `cells` y salida RGBA idénticos a la implementación vigente en toda la
regresión. Sin regresión de p95 mayor al 5% en ningún camino. Fuzzing en verde. Gate ES5
ampliado en verde.

### F5 — Trellis y near-lossless

Depende de F1 (rango reservado y rects protegidos), F2 (GOP estable) y de la decisión de
orden canónico (C-6). Es la tarea de mayor ganancia potencial y la de mayor riesgo.

| ID | Tarea | Δbytes | dec |
|---|---|:--:|:--:|
| F5-1 | Congelar el orden del pipeline de cuantización; absorber `--threshold` | sí | no |
| F5-2 | `--threshold` en ΔE-Oklab en lugar de euclídea RGB | sí | no |
| F5-3 | Trellis temporal: segundo candidato si iguala la celda del frame anterior | sí | no |
| F5-4 | Trellis espacial: forzar los cruces 17→16, 5→4 y 3→2 por tile | sí | no |
| F5-5 | Jerarquía de costo proxy / `zlib -9` / Zopfli (C-5) | — | no |
| F5-6 | Perfil `--near-lossless` con presupuesto **ΔE conservador**, opt-in | sí | no |

### Presupuesto ΔE

Decisión tomada el 2026-08-27: **presupuesto conservador**. Una celda solo cambia si el
segundo candidato está perceptualmente muy cerca en Oklab, de modo que la diferencia sea
invisible incluso en gradientes suaves y el clip no exija una re-inspección visual para
aprobarse.

Esto acota deliberadamente el ahorro. La consecuencia práctica es que F5 deja de ser la
tarea de mayor ganancia y pasa a ser una mejora acotada y segura: si el ahorro medido no
justifica su complejidad, F5 puede archivarse sin afectar al resto del plan, porque ninguna
otra fase depende de ella.

El umbral concreto se fija con evidencia, no por adelantado: se implementa parametrizado,
se barre un rango de ΔE sobre el clip de referencia y se elige el mayor valor cuyo error
temporal y proxy de banding no se distingan del baseline. El valor elegido queda registrado
con su medición.

F5 produce una matriz v1 **distinta** de la aprobada, así que no es exacta respecto del
original. No rompe la invariante de v2: el transcodificador sigue siendo exacto respecto de
la matriz v1 que reciba, sea cual sea. Debe quedar escrito para que nadie lea el ahorro de
F5 como una mejora del codec v2.

**Gate F5:** ΔE máximo por celda dentro del presupuesto conservador declarado; error
temporal sin regresión medible frente al baseline; proxy de banding sin empeorar; el ahorro
se reporta separado del de F2 y F3. Si el ahorro no supera un mínimo acordado, F5 se
archiva con su evidencia en lugar de promoverse.

### F6 — Revisión única de formato

Se agrupa todo lo que el TV debe entender distinto, para desplegar **una** versión de
decoder (regla 1 de §0).

| ID | Tarea | Δbytes | dec |
|---|---|:--:|:--:|
| F6-1 | `SPARSE` con offsets diferenciales en lugar de absolutos | sí | **sí** |
| F6-2 | `tile_size` flexible declarado en el header (cierre de F2-3) | sí | **sí** |
| F6-3 | Envelope `ASCLVID3` con `meta_len`; migrar el sidecar adentro | sí | **sí** |
| F6-4 | Nombre versionado `clip.<sha>.asclv` e invalidación de caché (`CACHE-001`) | — | — |

`PAL5`/`PAL6` para el hueco de 17-255 colores por tile **no entra**: el §17 del roadmap lo
mantiene vetado hasta tener benchmark neto en TV. Queda anotado como candidato de la
revisión siguiente, con la estimación de 25-37% en tiles de gradiente.

**Gate F6:** readers viejos rechazan `ASCLVID3` de forma limpia por magic desconocido.
Round-trip Python/JavaScript byte-exacto. Corpus de corrupción ampliado a los campos
nuevos. Prueba de caché fría y caliente.

### F7 — Runtime de la intervención (INT-002)

Depende de F1 (metadata y glifos), F4-2 y F4-13 (atajo a keyframe y marcado de rects).

| ID | Tarea |
|---|---|
| F7-1 | Estado del overlay y orden por frame de `DISENO-INTERVENCION-MATRICIAL.md` §9.2 |
| F7-2 | API ES5 `attach/setField/setValues/clearField/clear/detach` |
| F7-3 | Canal de datos con validación estricta, serial monotónico y backoff |
| F7-4 | Referencia Python: misma matriz con overlay dada la misma metadata y cadena |

**Gate F7:** los gates de INT-002 del documento de diseño, sin excepción. En particular:
restauración exacta byte a byte contra la reproducción sin overlay, y reproducción intacta
con el canal caído, corrupto o repetido.

### F8 — Validación física

| ID | Tarea |
|---|---|
| F8-1 | `frontend/diagnostic-player.html` con exportación manual (`VAL-001`) |
| F8-2 | Matriz física 640 y 768, Canvas2D y WebGL1, 30 minutos |
| F8-3 | Go/no-go de v2 (`TV-02`) con los artefactos ya optimizados |
| F8-4 | `MEM-001`: memoria por componente, con y sin overlay |
| F8-5 | Regenerar el artefacto de release **después** del último cambio de codec |

F8-5 cumple la regla del §14 del roadmap: ningún binario final se genera antes del último
cambio del codec.

## 3. Dependencias

```text
F0 ──> F1 ──> F3
       │
       └────> F5 <── F2
                     │
F0 ──> F2 ───────────┘
       ▲
F4-2 ──┘   (C-2: F2-4 no sale antes que F4-2)

F4-0 ──> F4-1 ──> F4-5           (C-8, C-7)
F4-2, F4-13 ──> F7 <── F1
F2-3, F6-1..3 ──> F6 (revisión única) ──> F8-5
```

Cadena crítica: **F0 → F1 → F3/F5 → F6 → F8**. El carril F4 corre en paralelo desde el
final de F0 y solo se sincroniza en F6 y F7.

Ejecución en paralelo acordada, con dos salvaguardas:

- ningún commit mezcla carril de encoder y carril de frontend, para poder bisecar por
  carril ante una regresión;
- la regresión completa (115 pruebas Python y las suites JavaScript) corre en cada
  integración de ambos carriles, no solo al cerrar una fase.

El único punto donde el paralelismo exige coordinación explícita es C-2: F2-4 queda
retenido hasta que F4-2 esté integrado y verde.

## 4. Protocolo de medición

Por cada tarea marcada con Δbytes, una fila en el registro con:

- bytes `.ascl` y `.asclv`, bytes por celda, distribución de tags;
- PSNR RGB y error Oklab cuando cambie calidad;
- keyframes y longitud máxima de cadena delta;
- decode y conversión p50/p95 en Node como dato orientativo, nunca como conclusión de TV;
- SHA-256, commit, parámetros y motivo.

Se conserva la disciplina vigente: una conclusión queda ligada a su configuración, y si
cambia el modo, la grilla, los FPS, la paleta, el dithering o el codec, se revalida.

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| La reescritura de `inflate.js` introduce un fallo sutil de decodificación | F4-1 antes que F4-5; corpus permanente; round-trip contra zlib nativo |
| Zopfli reduce el margen de v2 y la promoción de v2 pierde sentido | C-3: ambos lados con el mismo compresor; TV-02 decide con datos posteriores a F2 |
| El trellis degrada la calidad de forma no percibida por el proxy | F5 es opt-in y separado; presupuesto ΔE conservador calibrado con evidencia; nunca default |
| Exigir CRC distinto de cero rompe artefactos antiguos | `write_ascl` siempre escribió un CRC real; verificar el inventario antes de activar |
| `ASCLVID3` invalida la caché de los equipos desplegados | F6-4 planifica el nombre versionado junto con el cambio |
| La reserva de paleta empeora clips de gradiente exigente | `reserved` es por clip; un clip sin overlay usa las 256 |
| El plan se ejecuta sin medir y las ganancias se atribuyen mal | Regla 2 de §0; ninguna tarea Δbytes cierra sin su fila |
| Los dos carriles en paralelo dificultan aislar una regresión | Ningún commit mezcla carriles; regresión completa en cada integración |

## 6. Fuera de este plan

- `PAL5`/`PAL6` y otros packings de bits: vetados por §17 hasta benchmark en TV;
- remap exacto de IDs de paleta: experimento cerrado en -0,9569%, no default;
- filtros PNG por fila, estrategias alternativas de zlib y remap aislado: medidos y
  descartados con evidencia;
- carga parcial y HTTP Range: siguen detrás de `MEM-001`;
- diccionario preset de zlib: requiere habilitar FDICT en `inflate.js`, único cambio no
  trivial del decoder de toda la auditoría; se evalúa recién después de F6;
- streaming, Worker, WASM, WebGL2 y Service Worker: fuera de los invariantes.
