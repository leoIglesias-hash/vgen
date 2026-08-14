# Hoja de ruta técnica — cierre de ASCL v1 y evolución a v2

Estado: plan activo desde 2026-08-14. Primera revisión v2 implementada localmente;
benchmark de producto y promoción todavía pendientes.

Base v1 recuperable: commit `abb0451`, tag `tv-runtime-hq-v1`.

Este documento es la cola técnica activa: define qué implementar, en qué orden y qué
evidencia se exige para aceptar cada paso. No reemplaza las especificaciones ni copia sus
tablas. Las fuentes de verdad son:

| Tema | Documento |
|---|---|
| principios y arquitectura | `PLAN-IMPLEMENTACION-OPTIMIZACION.md` |
| formato v1/v2 | `ASCL-format-spec.md` |
| revisión v2 implementada | `DISENO-ASCL-V2-TILES.md` |
| resultados actuales | `BENCHMARK-V1-ADAPTATIVO-OKLAB.md` |
| decisiones por instancia | `REGISTRO-DE-PRUEBAS-Y-DECISIONES.md` |
| hosting | `DESPLIEGUE.md` |

Si una nota histórica contradice esta hoja o el registro de decisiones, prevalecen estos
dos documentos más recientes. Al terminar una tarea se agrega la evidencia al registro;
no se borran las conclusiones anteriores.

## 1. Base cerrada e invariantes

- El artefacto distribuido es un único `.asclv` cacheable. `ASCLVID1` o `ASCLVID2`
  contienen el `.ascl` de igual versión y el audio MP3.
- V1 sigue siendo el default de producción. V2 local admite `mode=PIXEL`, con índices de
  un byte y hasta 256 colores, sin volver a cuantizar la matriz v1.
- Oklab, bloques adaptativos, estabilidad y dithering se calculan offline. El reader no
  ejecuta esos algoritmos.
- Canvas2D es el piso. WebGL1 es opcional; ambos reciben la misma matriz y deben ofrecer
  la misma función visual.
- El cliente usa sintaxis ES5.1 y corre en ECMAScript 2015. No se exige `fetch`, Promise,
  Worker, WASM, WebGL2, Service Worker ni Streams.
- FPS, celdas, colores y calidad siguen editables. Un perfil no pisa un valor manual.
- No se implementará visión artificial, detección/rotación de objetos ni otra capa DOM.
- Una mejora no avanza si solo cambia complejidad sin reducir bytes, RAM o costo de
  reproducción bajo una métrica acordada.

Artefactos de control:

| Perfil | Artefacto | Función |
|---|---|---|
| eficiente | `TKN-2441-GANADOR-v1-adaptive-oklab-efficient-640.asclv` | piso de RAM/descarga |
| HQ | `TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv` | candidato visual recomendado |
| anterior | `TKN-2441-GANADOR-graphic-kmeans-block5.asclv` | control RGB block5 |

## 2. Decisión sobre el frontend actual

### Estado actual: frontend dual

`reader.js` permanece como ReaderV1. `reader-v2.js` y `reader-factory.js` despachan por
versión sin cambiar los renderers. `player.html` y `tv-player.html` aceptan envelopes
`ASCLVID1` y `ASCLVID2`. Para publicar un clip:

1. subir el `.asclv` elegido;
2. conservar el nombre esperado por `DEFAULT_SRC` o cambiar solo esa constante;
3. servirlo por HTTP con tipo binario y política de caché coherente;
4. desplegar también `reader-v2.js` y `reader-factory.js` si se servirá v2;
5. no separar ni convertir el audio incluido.

El mismo frontend abre HQ v1 o v2. La promoción de v2 sigue condicionada a pruebas
físicas; `--format v1` permanece como salida predeterminada.

### Cambios futuros del frontend

- instrumentación en una página de diagnóstico separada del player de producción;
- motor matricial de slots cuando existan metadata y fixtures;
- carga parcial solo si las mediciones demuestran que el XHR completo es el límite real.

Ninguno puede introducir una función disponible solo en WebGL. Una optimización opcional
puede tener fallback, pero la matriz y el resultado funcional deben ser comunes.

## 3. Métricas y gates comunes

Toda comparación v1/v2 usa exactamente las mismas matrices y paletas. La comparación de
calidad pertenece al encoder; la comparación de codec mide representación y reproducción.
No se mezclan ambas variables en un mismo experimento.

### Offline

- bytes `.ascl`, `.asclv`, bytes/s y bytes/celda;
- keyframes, longitud máxima de cadena delta y comandos por tipo;
- PSNR RGB, error Oklab, baja frecuencia, banding y error temporal cuando cambie calidad;
- tiempo y memoria del encoder como datos operativos, no como costo del TV;
- fuente/hash, commit, parámetros, CRC y SHA-256 de cada artefacto.

### En dispositivo

- descarga y primer frame con caché fría/caliente;
- RAM antes de cargar, al abrir y durante loop;
- decode, conversión RGBA y render p50/p95 por separado;
- frames descartados por el reloj de audio;
- crecimiento de memoria tras 30 minutos;
- renderer pedido y renderer efectivo;
- errores XHR, Blob, audio, fullscreen y contexto WebGL.

Para `fps` cuadros por segundo:

```text
frame_budget_ms = 1000 / fps
```

El objetivo inicial es `decode + render p95 <= 0,60 * frame_budget_ms` en el dispositivo
más lento aceptado. A 15 FPS equivale a 40 ms de 66,67 ms. El margen restante cubre audio,
eventos, GC y variación del WebView.

Se rechaza una variante si cambia una matriz que debía ser lossless, exige APIs sin
fallback, crea otro framebuffer completo, asigna memoria proporcional al frame durante
playback estable, rompe v1/seek/audio/cache, o mejora solo WebGL empeorando Canvas2D.

## 4. VAL-001 — validación física y perfil v1

Objetivo: decidir por familia de equipo si 768 puede ser general o si corresponde 640.

### Entregables

- `frontend/diagnostic-player.html`, ES5 y separado de `tv-player.html`;
- exportación manual JSON/texto, sin requerir servidor de telemetría;
- inventario con marca/modelo, año, WebView, resolución y renderer efectivo;
- prueba de 30 minutos con audio en 640 y 768; 960 solo como techo opcional;
- inspección de las 26 fronteras de paleta del candidato adaptativo.

### Instrumentación

- `performance.now()` con fallback a `Date`;
- tiempo alrededor de `reader.seek()` y `renderer.draw()`;
- frames objetivo omitidos;
- pérdida/restauración de contexto WebGL;
- dimensiones, FPS y bytes descargados;
- memoria solo si el motor expone una API confiable; su ausencia no falla la prueba.

### Aceptación

- video completo y audio sincronizado en Canvas2D;
- WebGL1, si existe, mantiene la misma función visual;
- frames descartados <0,1% después del calentamiento;
- p95 dentro del 60% del presupuesto;
- sin crecimiento sostenido >5% entre minutos 5 y 30 cuando pueda medirse;
- cero fallos de memoria, Blob, XHR o contexto.

768 será general solo en familias que pasen. 640 queda como perfil de compatibilidad; no
se elimina para simular uniformidad entre capacidades físicas distintas.

## 5. VAL-002 — corpus y calibración de calidad

El TKN permitió fijar una instancia, no un default universal. Se necesita un corpus con
fuentes y SHA-256 que cubra:

- animación plana/logos;
- fotografía y cámara;
- gradientes oscuros y cielos;
- texto pequeño;
- movimiento localizado y movimiento total;
- cortes fuertes y escenas casi estáticas.

En cada clip se compara estabilidad `0,25` contra `0,10` y, cuando sea necesario, `0`.
Se mantienen FPS, celdas y colores constantes y se miden flicker, Delta Oklab, error de
baja frecuencia, banding y bytes. Un valor se promueve a default solo si no hay regresión
material en ninguna clase o si queda limitado a un perfil explícito.

## 6. V1-01 — endurecimiento del reader antes de v2

Objetivo: congelar un piso confiable para atribuir correctamente cualquier fallo posterior.

### Trabajo

- rechazar una `version` distinta de 1 en `ReaderV1`;
- validar modo, dimensiones, frames, `data_off`, offsets, bloques, paletas, payloads
  inflados e índices antes de usarlos;
- imponer límites antes de reservar o inflar;
- exigir offsets crecientes dentro de la vista `.ascl`;
- rechazar DELTA sin base, datos truncados y valores fuera de paleta;
- agregar fixtures corruptos y fuzzing determinista Python/JavaScript;
- hacer normativa la distinción `.ascl` interior / `.asclv` con audio.

### Gate

- todos los fixtures v1 actuales abren;
- corrupción falla explícitamente, sin loops ni reservas descontroladas;
- seek en ambas direcciones coincide byte a byte con Python;
- la API de los renderers no cambia.

## 7. V1-OPT-01/02 — selector y presupuesto real

### Selector offline por restricciones

Entradas: rango de FPS, resoluciones, colores, paleta, estabilidad, dithering, formato,
tile futuro, límite de bytes, RAM teórica y clase de dispositivo. Los valores fijados por
el usuario son restricciones duras.

El procesador prueba segmentos representativos, descarta violaciones y codifica completo
solo el frente de Pareto:

```text
min(bytes, decode_cost, ram_estimate, perceptual_error, temporal_error)
```

Debe emitir un sidecar determinista con parámetros, métricas y motivo de descarte. El
candidato automático queda dentro de 3% del mejor peso manual conocido y 2% de su error
perceptual, o explica qué restricción impidió alcanzarlo.

### Presupuesto de dithering en bytes

El límite actual de celdas evita exceso visual, pero no garantiza tamaño. El encoder debe
comparar los bytes reales del frame/bloque con dither frente a baseline y rechazarlo si
supera un presupuesto configurable. El límite de bytes y el 5% de celdas se aplican juntos;
ninguno reemplaza al otro.

## 8. V1-RUNTIME-01 — reducir RAM y trabajo sin cambiar formato

Esta tarea sí modifica internamente el frontend, pero no es necesaria para abrir los
artefactos actuales. Debe completarse antes de atribuir a v2 ganancias que también son
posibles sobre v1.

### Trabajo

- consultar offsets con `DataView` o una vista tipada, evitando un `Array` de números
  JavaScript por frame;
- reemplazar el mapa de keyframes por un bitset o tabla tipada acotada;
- implementar `inflateInto(source, scratch, maxLength) -> actualLength` con destino
  reutilizable. ZLIB full exige longitud exacta; DELTA limita a `N*(4+bpc)` y DELTA_MASK
  a `ceil(N/8)+N*bpc`, y cada tag valida después su longitud real;
- reutilizar scratch para DELTA y DELTA_MASK;
- producir dirty tiles lógicos también para v1;
- convertir RGBA por bandas/corridas usando el mismo dirty set en Canvas2D y WebGL1;
- verificar `MAX_TEXTURE_SIZE` y degradar a Canvas si WebGL se pierde durante playback.

### Gate

- CRC de `cells` y salida RGBA idénticos a la implementación vigente;
- ningún buffer nuevo de frame completo por cuadro en el loop estable; `cells`, RGBA,
  bitsets y scratch proporcional se permiten como estado persistente acotado/reutilizado;
- p95 sin regresión mayor a 5%;
- reducción >=20% del pico transitorio de inflate en el equipo más lento;
- cambios de paleta y keyframes fuerzan actualización completa;
- fallback WebGL→Canvas conserva frame y reloj de audio.

### Estado local 2026-08-14

Implementado sobre v1, pendiente de VAL-001 físico:

- offsets por `DataView`, keyframes en bitset y reader/CRC defensivo;
- DELTA v1 mantiene offsets históricos en cualquier orden y repetidos con última escritura
  válida, sin renunciar a validar el payload completo antes de mutar `cells`;
- inflate tipado reutilizable y adaptativo: HQ usa 331.776 B de scratch frente a un
  límite defensivo de 1.658.880 B;
- bitset de una celda por bit y conversión RGBA exacta para DELTA/MASK;
- mismo dirty state en Canvas2D/WebGL1, sentinel vacío sin draw y fallback legacy;
- contexto WebGL liviano, `MAX_TEXTURE_SIZE`, probes iniciales y fallback en playback;
- liberación explícita de reader, audio, Canvas y GPU antes de renovar la descarga.

En HQ 768 las bandas por sí solas solo evitaban 0,44% de filas por dispersión espacial.
El bitset exacto evitó 46,14% de conversiones y redujo aproximadamente 19% la etapa de
conversión y 4,7% decode+conversión en Node. No se extrapola a GPU ni TV. Dirty tiles v2
siguen siendo necesarios para reducir uploads cuando el contenido sea regional.

## 9. V2-00/01/02 — codec regional y referencia Python

### Estado: implementado localmente

La primera revisión ya convierte de manera secuencial una matriz v1 `PIXEL` aprobada a
v2 sin volver a cuantizar. Decisiones cerradas en esta revisión:

- header interior de 32 B, `version=2`, byte 26 `tile_size=16`, byte 27 flags `0x01`;
- CRC obligatorio sobre header `0..27` y cuerpo `32..EOF`;
- envelope `ASCLVID2` de 16 B, sin directorio ni chunks;
- tags 0..3 como fallback v1; 4..7 regionales; 8/9 predictores;
- opcodes `SKIP_RUN`, `SOLID`, `SPARSE`, `MASK`, `PACK1`, `PACK2`, `PAL4`, `PAL8`;
- LEB128 uint32 canónico y bits LSB-first;
- selección estricta por bytes, conservando el payload anterior en empate;
- garantía estructural de que v2 no crece respecto del v1 de entrada;
- decoder Python independiente y validación transaccional.

`PACK4` no es otro opcode: el nombre normativo es `PAL4`. Solo `SKIP_RUN` lleva una
corrida; `SOLID` cubre un tile y no existe `SOLID_RUN`. Una repetición completa es un
`SKIP_RUN(tile_count)`, no un opcode propio.

Los predictores exactos implementados son LEFT, TOP y GRADIENT para keyframes, y
PREVIOUS_SUB/PREVIOUS_XOR para deltas. Toda aritmética es modular `uint8`; la paleta y el
RGB reconstruido no cambian.

El transcodificador conserva cada tag/payload v1 original y solo lo reemplaza con una
representación v2 estrictamente menor. La comparación es mecánica; no requiere una persona,
IA ni proxy visual.

### Evidencia local cerrada y gate que permanece

- artefacto HQ v2 final registrado: 17.935.305 B, SHA-256
  `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A`;
- igualdad completa Python/JavaScript: RGBA 231/231 y audio 180.857 B byte-exacto;
- distribución final: 89 ZLIB, 141 DELTA_MASK y 1 REGIONAL_DELTA_RAW;
- medir costo de decode, scratch y dirty set frente a v1 **en los TV reales**;
- conservar todos los tests de corrupción y entrada incompresible;
- no promover un experimento de remap solo porque reduzca bytes.

El remap exacto de IDs de paleta se evaluó aparte: 89/89 GOP obtuvieron un candidato
menor y el bundle estimado pasaría de 17.935.310 a 17.763.683 B (-171.627 B; -0,9569%),
con RGB byte-exacto en 231/231 frames. Requirió 94 tags predictores y 414,4 s offline. No
es default ni forma parte del transcodificador actual: menos de 1% no justifica asumir
mayor CPU del TV sin benchmark físico.

Near-lossless, `HOLD_TICKS`, `TILE_DICT`, `PAL_PATCH`, `REMAP_RECT`, FPS por segmentos y
otros tiles quedan para revisiones posteriores. No comparten el gate del transcode exacto.

## 10. V2-03/04 — ReaderV2 y dirty común

### Estado: implementado localmente

`reader-factory.js` despacha `version=1 -> ReaderV1`, `version=2 -> ReaderV2` y rechaza
otras versiones. `ReaderV2` usa sintaxis ES5, una matriz lógica `Uint8Array` y los mismos
renderers Canvas2D/WebGL1.

El dirty state es híbrido:

- celdas exactas para DELTA, DELTA_MASK, SPARSE, MASK y predictores delta;
- tiles para comandos regionales densos;
- full para keyframes o cambio de paleta;
- unión acumulada al hacer seek o saltar frames.

El stream regional se valida en una primera pasada y se aplica en la segunda. Inflate usa
un scratch tipado que puede crecer bajo bounds y luego se reutiliza. El gate corregido no
promete “cero buffers proporcionales” —la matriz, RGBA, bitsets y scratch dependen de N—;
exige **no reservar un nuevo buffer de frame completo por cuadro en el loop estable**.

### Gates pendientes de producto

- CRC/matriz/paleta idénticos a Python por frame y seek sobre HQ final
  (**cumplido local; falta repetir en dispositivo**);
- regresión v1 completa y rechazo de corrupción antes de mutar estado;
- igualdad funcional Canvas2D/WebGL1;
- p95 v2 no supera v1 más de 5% en movimiento total;
- RAM pico no supera v1 y el scratch deja de crecer tras el calentamiento;
- en movimiento localizado reduce trabajo convertido/subido o cae al camino full exacto.

## 11. TV-02 — decisión go/no-go v2

Se producen pares v1/v2 640 y 768 con la misma matriz y se repite VAL-001.

### Go recomendado

- matriz/paleta idénticas;
- reducción mediana de bytes >=10%;
- p95 dentro del 60% del frame;
- RAM pico <=v1;
- drops <=v1 +0,1 puntos porcentuales;
- sin regresión de caché, audio, fullscreen o Canvas2D.

### Go especializado

Si solo mejora movimiento localizado en >=20% de bytes o escrituras, queda como perfil
explícito y no se selecciona fuera del dominio medido.

### No-Go

Si la ganancia depende de WebGL, aumenta RAM o no supera el costo de comandos en TVs, el
default sigue siendo v1. Se conserva el prototipo y la evidencia; no se fuerza migración.

## 12. INT-001/002 — intervención matricial local

Antes del runtime se crea `DISENO-INTERVENCION-MATRICIAL.md`. Un slot inicial declara:

```text
slot_id
x, y, width, height
start_frame, end_frame
palette_epoch_map
asset_table
flags: visible, programable, transparencia
```

El primer prototipo admite rectángulos sin solapamiento. Los assets son parches de índices
precalculados por época de paleta; el TV no cuantiza RGB ni detecta objetos. Transparencia
binaria conserva la celda base.

La primera revisión `ASCLVID2` no contiene secciones `SLOT/META/VIDO/AUDI`: su envelope
de 16 B solo declara las longitudes ASCL y audio. `INT-001` debe definir una revisión
posterior del interior o una nueva versión que conserve un solo archivo cacheable. No puede
agregar trailing bytes al v2 actual porque los readers los rechazan deliberadamente.

### Orden por frame

1. restaurar desde un buffer pequeño el rectángulo base anterior;
2. decodificar el frame sobre la matriz única;
3. guardar solo el rectángulo base actual;
4. aplicar el asset seleccionado en esas celdas;
5. marcar sus dirty tiles;
6. presentar normalmente.

Así una intervención no contamina el estado de un DELTA posterior. La memoria auxiliar es
la suma de áreas activas, nunca otro `cols * rows`.

API ES5 propuesta:

```text
setSlot(slotId, assetId)
setSlotAtFrame(slotId, assetId, frameIndex)
clearSlot(slotId)
getSlot(slotId)
```

### Gate

- un canvas y una matriz lógica;
- mismo CRC intervenido en ambos renderers;
- restauración exacta al limpiar o hacer seek;
- costo p95 de slots <10% del frame;
- RAM acotada por áreas declaradas;
- IDs inválidos no escriben fuera del slot.

## 13. MEM/CACHE/FMT — memoria, caché y límite de tamaño

V2 por tiles no elimina por sí solo la residencia del XHR completo, Blob de audio, matriz,
RGBA y backing store/textura. `MEM-001` debe medir cada componente por separado antes de
afirmar que el límite de memoria quedó resuelto.

### Caché inmediata

- nombre versionado `clip.<sha-corto>.asclv` + `Cache-Control: public, max-age=31536000,
  immutable`;
- si producción exige `clip.asclv`, usar ETag/revalidación o query de versión; un nombre
  mutable no debe servirse como `immutable`;
- verificar `Content-Length`, `Accept-Ranges`, caché fría/caliente e invalidación.

Estado local: `tv-player.html` ya permite renovar `./outputs/clip.asclv` desde un menú
oculto. Libera la instancia anterior, rota un query token persistente y solicita
`no-cache`, sin Service Worker ni `fetch`. No puede borrar la caché HTTP global y cada
token anterior puede seguir almacenado; ETag/política PHP y la prueba fría/caliente siguen
pendientes de CACHE-001.

### Límite de 4 GiB

V2 acepta y valida tempranamente el límite `<4 GiB` porque usa offsets uint32. HTTP Range
reduce buffers y arranque, pero no permite direccionar bytes posteriores a ese límite.
Superarlo requiere otro formato/envelope o segmentación y queda para una versión posterior;
no se introducen enteros de 64 bits al runtime ES5 sin evidencia.

### Gate para Range

Investigar carga parcial solo si una familia falla por pico de RAM o arranque. Debe usar
la misma URL con `Content-Encoding: identity`, enviar ETag/`If-Range`, validar `206` y el
`Content-Range` exacto, y caer al buffer completo si recibe `200` o un rango inconsistente.
No exige MediaSource, Streams ni Service Worker. El audio puede pedirse por el rango
calculado como `16 + ascl_len .. EOF` y tener una copia acotada para crear su Blob; no
existe una sección `AUDI` en el envelope actual. Algunas cachés unen ranges en RAM: la
reducción debe medirse, no suponerse.

IndexedDB puede ser opcional tras detección. HTTP cache sigue siendo el piso universal.

## 14. Seguridad y reproducibilidad

- límites para dimensiones, celdas, frames, paletas, offsets, bloques, slots e inflate;
- corpus truncado, opcodes desconocidos y bombas de descompresión;
- encoder determinista o semilla registrada;
- tests que rechacen sintaxis/APIs no permitidas en `frontend/`;
- benchmark JSON/Markdown reproducible;
- fuente/hash, commit, parámetros y conclusión por instancia;
- ningún binario final generado antes del último cambio del codec.

## 15. Backlog priorizado

| ID | Estado | Entregable siguiente | Gate |
|---|---|---|---|
| VAL-001 | pendiente | matriz física 640/768 | §4 |
| VAL-002 | pendiente | corpus y estabilidad 0/0,10/0,25 | §5 |
| V1-01 | código listo | cierre físico del reader v1 | §6 |
| V1-OPT-01 | pendiente | selector offline sin inspección visual humana | §7 |
| V1-OPT-02 | pendiente | presupuesto dither en bytes | §7 |
| V1-RUNTIME-01 | código listo | RAM/p95/drops físicos | §8 |
| V1-REL-01 | pendiente | regenerar/promover 960 solo si VAL-001 lo permite | gates físicos |
| V2-00 | implementado | cerrar evidencia del planificador exacto | §9 |
| V2-01 | implementado | revisión congelada; falta aceptación física | §9 |
| V2-02 | verificado localmente | repetir métricas en TV | §9 |
| V2-03 | verificado localmente | repetir ReaderV2/seek en TV | §10 |
| V2-04 | implementado | medir dirty híbrido Canvas/WebGL | §10 |
| V2-REMAP-01 | experimento; no default | medir CPU física antes de considerar perfil | §9 |
| TV-02 | pendiente | go/no-go v2 físico | §11 |
| INT-001 | pendiente | diseño formal de slots sin cambiar envelope v2 actual | §12 |
| INT-002 | pendiente | slot runtime | §12 |
| MEM-001 | pendiente | memoria por componente | §13 |
| CACHE-001 | pendiente | caché/versionado HTTP | §13 |
| FMT-LIMIT-001 | parcial | validar artefactos reales <4 GiB | §13 |
| RANGE-001 | diferido | prototipo solo con evidencia MEM-001 | §13 |
| DOC-001 | en curso | mantener índice/estatus sin contradicciones | enlaces vigentes |

## 16. Próxima sesión recomendada

1. Desplegar ambos bundles y ejecutar VAL-001/TV-02 en Canvas2D y WebGL1 reales.
2. Medir decode/seek/scratch, RAM, CPU y dirty híbrido v1 frente a v2 en esos equipos.
3. Mantener el remap exacto fuera del default: su -0,9569% estimado requiere demostrar
   que 94 predictores no empeoran CPU/drops.
4. Decidir go/no-go: promover v2, ofrecerlo como perfil especializado o conservar v1.
5. Recién después retomar near-lossless o intervención matricial como revisiones separadas.

Range continúa detrás de evidencia física: la primera revisión descarga y cachea un único
recurso completo.

## 17. No hacer todavía

- IA, detección/rotación de objetos o overlays DOM;
- dependencia obligatoria de Worker, WASM, WebGL2, IndexedDB o Service Worker;
- packing de 5/6/7 bits sin benchmark neto en TV;
- segmentación o streaming sin medir primero XHR/RAM;
- textura WebGL exclusiva que cambie `soft` frente a Canvas2D;
- reemplazar v1 antes de cumplir TV-02.
