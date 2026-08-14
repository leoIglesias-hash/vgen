# Hoja de ruta técnica — cierre de ASCL v1 y evolución a v2

Estado: plan activo desde 2026-08-14.

Base recuperable: commit `fbeca06`, tag `tkn-adaptive-oklab-hq-v1`.

Este documento es la cola técnica activa: define qué implementar, en qué orden y qué
evidencia se exige para aceptar cada paso. No reemplaza las especificaciones ni copia sus
tablas. Las fuentes de verdad son:

| Tema | Documento |
|---|---|
| principios y arquitectura | `PLAN-IMPLEMENTACION-OPTIMIZACION.md` |
| formato v1 | `ASCL-format-spec.md` |
| propuesta binaria v2 | `DISENO-ASCL-V2-TILES.md` |
| resultados actuales | `BENCHMARK-V1-ADAPTATIVO-OKLAB.md` |
| decisiones por instancia | `REGISTRO-DE-PRUEBAS-Y-DECISIONES.md` |
| hosting | `DESPLIEGUE.md` |

Si una nota histórica contradice esta hoja o el registro de decisiones, prevalecen estos
dos documentos más recientes. Al terminar una tarea se agrega la evidencia al registro;
no se borran las conclusiones anteriores.

## 1. Base cerrada e invariantes

- El artefacto distribuido es un único `.asclv` cacheable. `ASCLVID1` contiene el
  `.ascl` y el audio MP3.
- El video actual sigue siendo ASCL v1, `mode=PIXEL`, con índices de un byte y hasta 256
  colores.
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

### Ahora, con ASCL v1

No hace falta modificar `reader.js`, los renderers ni `tv-player.html`. Las mejoras están
horneadas como paletas e índices v1 y sus flags ya son compatibles. Para publicar un clip:

1. subir el `.asclv` elegido;
2. conservar el nombre esperado por `DEFAULT_SRC` o cambiar solo esa constante;
3. servirlo por HTTP con tipo binario y política de caché coherente;
4. no separar ni convertir el audio incluido.

El HQ 768 no necesita otro reproductor, aunque usa más celdas y debe pasar pruebas físicas
antes de convertirse en el único perfil publicado.

### Cambios futuros del frontend

- despacho `ReaderV1`/`ReaderV2` cuando exista un fixture v2 aprobado;
- dirty tiles comunes para Canvas2D y WebGL1;
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
- cero asignaciones o buffers transitorios proporcionales por frame; inventario
  persistente fijo/acotado y sin crecimiento entre loops;
- p95 sin regresión mayor a 5%;
- reducción >=20% del pico transitorio de inflate en el equipo más lento;
- cambios de paleta y keyframes fuerzan actualización completa;
- fallback WebGL→Canvas conserva frame y reloj de audio.

### Estado local 2026-08-14

Implementado sobre v1, pendiente de VAL-001 físico:

- offsets por `DataView`, keyframes en bitset y reader/CRC defensivo;
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

## 9. V2-00/01/02 — planificador regional, formato congelado y referencia Python

Objetivo: demostrar tiles usando la matriz final aprobada, sin volver a cuantizar,
suavizar ni aplicar dither. La representación base está en `DISENO-ASCL-V2-TILES.md` y
la selección exacta/near-lossless en `DISENO-PLANIFICADOR-REGIONAL-V2.md`.

### V2-00 — planificador regional experimental, sin formato público

Primero se implementa un planificador determinista en memoria. No emite todavía archivos
que se declaren v2 estables y puede probar tiles 8/16/32 para descartar opciones. Separa
dos decisiones que no deben mezclarse:

1. un planificador perceptual temporal produce la matriz que realmente se mostrará; en
   modo lossless es idéntica al objetivo y en modo con pérdida aplica límites explícitos;
2. un empaquetador regional lossless representa la transición elegida con el menor costo
   real de bytes, escrituras e inflate.

Los candidatos exactos mínimos son:

- `REPEAT`, `SKIP`, `SOLID`, `SPARSE`, `MASK`, `PACK1`, `PACK2`, `PAL4` y `PAL8`;
- DELTA_MASK v1 como baseline;
- candidato `MASK_ZLIB` (`mask_bits || changed_values`) para movimiento amplio;
- keyframe ZLIB completo después de disponer de inflate directo.

El encoder compara bytes reales. En un tile 16x16, `SPARSE` es apropiado para pocos
cambios, `MASK` para densidad intermedia, `PACK1/2/4` cuando hay 2/4/16 índices locales y
`PAL8` cuando casi todo el tile cambia. Tiles adyacentes con una misma decisión pueden
fusionarse offline en corridas o rectángulos; el decoder no recibe árboles ni ejecuta
búsqueda visual.

El modo temporal con pérdida queda apagado por defecto. No usa un porcentaje RGB global.
Compara cada celda objetivo contra el último color realmente emitido en Oklab y mantiene,
por tile, media, p95, máximo, edad y deuda temporal. Se fuerza una actualización por error
máximo, deuda, `max_hold_frames`, corte fuerte, bordes nuevos o riesgo de mesetas en un
degradado. El control propuesto como 2% se expone como perfil configurable, pero se traduce
a límites perceptuales separados y se calibra con VAL-002 antes de fijar un default.

Experimentos adicionales, sin reservar todavía opcodes:

- `HOLD_TICKS`: una sola muestra con duración entera para matrices idénticas consecutivas.
  Reduce tabla, decode y llamadas de render sin alterar la imagen ni el audio;
- `TILE_DICT`: diccionario acotado de patrones de tile que reaparecen en cuadros no
  consecutivos. El encoder usa hashes exactos, no detección de objetos;
- `PAL_PATCH`: conservar IDs estables y transmitir solo entradas de paleta modificadas.
  Incluye las corridas sucias para que Canvas regenere solo las regiones afectadas y solo
  avanza si el ahorro compensa ese trabajo;
- `REMAP_RECT`: aplicar pocas parejas `índice anterior -> índice nuevo` dentro de un
  rectángulo. Se descarta si escanear el área cuesta más que escribirla directamente;
- FPS por segmentos como modo con pérdida explícito: un máximo editable y duraciones en
  ticks permiten ahorrar cuadros en escenas lentas sin reducir el máximo de escenas que
  sí necesitan movimiento. Se evalúa después del camino lossless `HOLD_TICKS`.

Conceptos de WebP que se estudian sin incorporar un decoder WebP: selección local por
bloques, paletas de 1/2/4 bits, predictores espaciales simples y preprocesamiento
`near-lossless` exclusivamente offline. No se trasladan VP8/DCT, YUV420, motion vectors,
loop filter, un entropy coder nuevo ni ZLIB independiente por tile: aumentarían CPU, RAM
y superficie de errores en los navegadores que gobiernan la compatibilidad.

El planificador registra:

```text
stored_bytes
cell_writes
inflated_bytes
unpack_operations
dirty_tiles
keyframe_penalty
delta_ok_mean_p95_max
temporal_debt
max_hold_age
refresh_jump
```

Gate lossless: CRC de matriz idéntico por frame y reducción mediana de payload >=10% sin
casos >3% mayores, o reducción >=20% de escrituras para un perfil especializado. Gate
lossy: además, ninguna región excede media/p95/máximo, deuda, edad o salto configurados;
los cortes fuertes son inmediatos y el proxy de banding no retrocede. Si no se alcanza,
se revisan candidatos antes de congelar ningún byte del formato.

### V2-01 — decisiones binarias y fixtures dorados

Con la evidencia del planificador se cierran:

1. header, keymap, límites, tile sizes y opcodes;
2. si `MASK_ZLIB` es opcode normativo —por ejemplo `0x07`, único comando del delta— o
   solo comparador que hace que `--format auto` conserve v1;
3. envelope: el candidato preferido es `ASCLVID2` con directorio
   `VIDO/AUDI/SLOT/META`; `ASCLVID1` permanece intacto para bundles v1;
4. CRC de metadata (header/offsets/keymap) y CRC por frame o GOP, verificables antes de
   mutar `cells` tras una lectura Range;
5. GOPs autocontenidos, iniciados por keyframe y con directorio al comienzo. La descarga
   normal puede acumular todos los GOP sin perder datos; Range futuro puede pedirlos por
   separado usando la misma estructura;
6. offsets uint32 y límite v2 explícito menor a 4 GiB.

Recién entonces se generan fixtures binarios dorados y se actualiza
`DISENO-ASCL-V2-TILES.md` como especificación congelada.

### V2-02 — encoder y decoder Python de referencia

Se implementa la especificación cerrada, con encoder canónico, decoder independiente,
validación completa, keymap, seek y dirty union. Packing 5/6/7 bits queda fuera salvo
que el planificador haya demostrado ganancia neta suficiente para justificarlo.

### Corpus de codec

Usar las clases de VAL-002, cuadros repetidos, dimensiones no divisibles por 16/32 y
cambios de paleta. Codec v1 y v2 reciben las mismas matrices.

### Gate de referencia

- CRC de `cells` idéntico a v1 en cada frame;
- seek aleatorio y frames omitidos terminan en el mismo estado;
- metadata y frame/GOP corruptos se rechazan antes de modificar la matriz;
- el resultado conserva el beneficio aprobado en V2-00;
- solo después se autoriza escribir ReaderV2.

## 10. V2-03/04 — ReaderV2 y dirty tiles comunes

Factory obligatorio: `version=1 -> ReaderV1`, `version=2 -> ReaderV2`, otra -> error.
Interfaz común:

```text
header, cells, palette, seek(frameIndex)
dirtyFull, dirtyCount, dirtyTiles, tileSize
```

`ReaderV2` escribe sobre una única `Uint8Array(cols * rows)`. La primera implementación
mantiene la conversión RGBA y shaders actuales para no cambiar codec y reconstrucción a la
vez. Los dirty tiles se agrupan en corridas comunes:

- Canvas2D reutiliza bandas y `putImageData`;
- WebGL1 sube las mismas regiones RGBA con `texSubImage2D`;
- keyframe puede marcar `dirtyFull`;
- al saltar frames se acumula la unión completa.

Una textura WebGL de índices queda experimental: no entra al camino común mientras `soft`
no tenga semántica equivalente en Canvas2D.

### Gate JavaScript

- cero asignaciones o buffers transitorios proporcionales por frame; inventario
  persistente fijo/acotado y sin crecimiento entre loops;
- CRC idéntico a Python por frame/seek;
- igualdad funcional Canvas2D/WebGL1;
- regresión v1 completa;
- p95 v2 no supera v1 más de 5% en movimiento total;
- en movimiento localizado reduce >=20% celdas convertidas/subidas o usa `dirtyFull`.

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

`INT-001` usa la decisión de envelope tomada en V2-01. Si se adopta `ASCLVID2`, los datos
viven en `SLOT/META` y el video/audio en `VIDO/AUDI`. Sigue siendo un solo archivo cacheable
y el player dual continúa abriendo todos los bundles `ASCLVID1`.

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
No exige MediaSource, Streams ni Service Worker. La sección `AUDI` puede descargarse como
rango independiente y tener una copia acotada para crear su Blob; no se duplica el video
completo. Algunas cachés unen ranges en RAM: la reducción debe medirse, no suponerse.

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

| ID | Entregable | Dependencia | Gate |
|---|---|---|---|
| VAL-001 | matriz física 640/768 | v1 actual | §4 |
| VAL-002 | corpus y estabilidad 0/0,10/0,25 | fuentes con hash | §5 |
| V1-01 | reader v1 endurecido | fixtures actuales | §6 |
| V1-OPT-01 | selector offline | VAL-002 | §7 |
| V1-OPT-02 | presupuesto dither en bytes | benchmark encoder | §7 |
| V1-RUNTIME-01 | buffers y dirty regions v1 | V1-01; cierre físico: VAL-001 | §8 |
| V1-REL-01 | regenerar/promover 960 | VAL-001 | mismos gates físicos |
| V2-00 | planificador regional experimental | V1-RUNTIME-01 | §9 |
| V2-01 | spec/envelope/CRC/fixtures dorados | V2-00 + requisitos de slots | §9 |
| V2-02 | encoder/decoder Python | V2-01 | §9 |
| V2-03 | ReaderV2 ES5 | V2-02 | §10 |
| V2-04 | dirty tiles comunes | V2-03 | §10 |
| TV-02 | go/no-go v2 físico | V2-04 | §11 |
| INT-001 | diseño formal de slots/envelope | V2-01 | §12 |
| INT-002 | slot runtime | INT-001,V2-04 | §12 |
| MEM-001 | memoria por componente | VAL-001 | §13 |
| CACHE-001 | caché/versionado HTTP | VAL-001 | §13 |
| FMT-LIMIT-001 | validar <4 GiB | V2-01 | §13 |
| RANGE-001 | prototipo condicional | evidencia MEM-001 | §13 |
| DOC-001 | índice/estatus documental | inmediato | enlaces sin contradicción |

## 16. Próxima sesión recomendada

1. Desplegar el frontend v1 endurecido y ejecutar VAL-001 con 640/768; 960 sigue techo.
2. Construir VAL-002 y cerrar si estabilidad 0,25 es general o específica del TKN.
3. Cerrar V1-01/V1-RUNTIME-01 con p50/p95, RAM y cuadros perdidos físicos; el código y
   los fixtures defensivos ya están implementados localmente.
4. Implementar V2-00-A: planificador regional lossless contra matrices v1 aprobadas,
   sin emitir todavía un formato público.
5. Implementar V2-00-B: near-lossless temporal, `PAL_PATCH` y `REMAP_RECT` detrás de los
   límites y corpus de `DISENO-PLANIFICADOR-REGIONAL-V2.md`.
6. Congelar V2-01 solo después de los gates físicos y del planificador, y actualizar
   `DISENO-ASCL-V2-TILES.md`.
7. Construir V2-02 en Python antes de autorizar ReaderV2.

INT-001 puede diseñarse junto con el header v2, pero el runtime comienza cuando dirty tiles
sea estable. Range queda detrás de evidencia física: el único recurso cacheable sigue
siendo la prioridad.

## 17. No hacer todavía

- IA, detección/rotación de objetos o overlays DOM;
- dependencia obligatoria de Worker, WASM, WebGL2, IndexedDB o Service Worker;
- packing de 5/6/7 bits sin benchmark neto en TV;
- segmentación o streaming sin medir primero XHR/RAM;
- textura WebGL exclusiva que cambie `soft` frente a Canvas2D;
- reemplazar v1 antes de cumplir TV-02.
