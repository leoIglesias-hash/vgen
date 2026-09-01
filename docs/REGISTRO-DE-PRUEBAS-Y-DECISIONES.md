# Registro de pruebas y decisiones

Este documento conserva las apreciaciones, mediciones y decisiones de cada version
probada. Una conclusion no se considera universal: vale para la instancia y la
configuracion que figuran en su entrada.

## Regla para nuevas entradas

Registrar siempre:

1. fuente y hash;
2. version del formato y configuracion completa;
3. archivo resultante y hash;
4. observacion que motivo la prueba;
5. mediciones comparables;
6. explicacion de la causa probable;
7. decision y limites de validez;
8. resultado en dispositivos reales cuando este disponible.

Se debe repetir una conclusion si cambia alguno de estos factores: fuente, modo PIXEL o
ASCII, columnas/filas, FPS, cantidad de colores, algoritmo o duracion de paleta,
dithering, threshold con perdida, reconstruccion, formato/codec o reader/player.

## Fuente TKN usada en las instancias 001, 002 y 003

- Archivo: `TKN-2441-GANADOR- 15seg-.mp4`.
- Tamaño: 39.032.116 bytes.
- SHA-256: `EADB3346C8618E1954474696B8F96157B3E6409DBA57350440D7737B88A3AB55`.
- Salida: 640x360, 15 FPS, 231 frames, 15,4 segundos.
- Audio incluido en cada ASCLV: MP3 de 180.857 bytes.

## Instancia 001 - Seleccion de K-means y demo de 30 frames

Fecha: 2026-08-11.

### Configuracion evaluada

- ASCL v1, modo PIXEL.
- Perfil `graphic`: 640 columnas y hasta 256 colores.
- 15 FPS.
- Paleta temporal por bloques de 30 frames (2 segundos).
- Algoritmo `kmeans-rgb`.
- Reconstruccion `soft`.
- Dithering apagado y threshold 0.
- Implementacion del encoder: commit `62c56a7` (backend sin cambios durante la
  comparacion posterior de bloques).

### Motivo

La cuantizacion anterior producia escalas visibles en gradientes. Se compararon
MEDIANCUT, FASTOCTREE y K-means RGB, aceptando mas trabajo en la PC si el archivo y el
player del televisor mejoraban.

### Resultado que llevo a la decision

En el benchmark de nueve cuadros documentado en `BENCHMARK-TKN-COLORES.md`, K-means
frente a MEDIANCUT, ambos con 256 colores y bloques de 30 frames, obtuvo:

- +4,28 dB de PSNR de grilla;
- 14,8% menos bytes en el ASCLV;
- frente al candidato original de 128 colores, +6,75 dB por 917 KB adicionales.

El costo adicional quedo solo en el procesamiento offline. El formato, reader, RAM por
matriz y renderer no cambiaron.

### Version conservada

- Archivo: `outputs/TKN-2441-GANADOR-graphic-kmeans.asclv`.
- Tamaño: 12.089.965 bytes.
- SHA-256: `81702D32CABDFBB9F15D6AAA2908B3FE5B13751CFB52257DCF01DFE9CF2F87F5`.

### Decision y alcance

K-means RGB queda seleccionado para esta clase de animacion grafica con 256 colores.
La conclusion se obtuvo con este TKN, PIXEL 640x360, 15 FPS y sin dithering. No demuestra
por si sola que K-means sea siempre mejor en video fotografico, otra grilla, otra cantidad
de colores o modos ASCII.

## Instancia 002 - Duracion de paleta: 30, 15, 10 y 5 frames

Fecha: 2026-08-12.

### Observacion que motivo la prueba

Los ultimos frames del demo de la instancia 001 mostraban menos escalas de color que el
resto. Se planteo renovar la paleta cada 5 frames porque el tiempo de encode no es una
restriccion y la prioridad es la calidad final.

### Explicacion comprobada

El video tiene 231 frames. Con bloques de 30 se forman siete bloques completos y un
ultimo bloque de solo 21 frames. El encoder usa hasta 12 frames repartidos para construir
cada paleta:

- bloque normal: 12 de 30 frames representados (40%);
- bloque final: 12 de 21 frames representados (57%).

El final estaba mejor adaptado por cubrir menos tiempo y estar mas densamente muestreado;
ademas, su contenido es cromaticamente mas sencillo. No recibio un tratamiento manual.
Al pasar a bloques de 5, la diferencia de PSNR entre el tramo anterior y el final bajo de
aproximadamente 0,95 dB a 0,04 dB, confirmando la causa.

### Comparacion controlada

Todas las variantes conservaron exactamente: fuente, ASCL v1, PIXEL 640x360, 15 FPS,
231 frames, 256 colores, K-means RGB, reconstruccion soft, dithering apagado, threshold 0
y el mismo audio.

Se compararon los 231 cuadros. La referencia fue cada RGB 640x360 anterior a la
cuantizacion y la salida fue la matriz ASCL decodificada con su paleta activa. Estas
metricas aislan la cuantizacion; no miden la perdida de reducir la fuente a 640x360 ni
el escalado soft del navegador. Los tamaños incluyen el mismo audio y el header ASCLV.

| Bloque | Renovacion | ASCLV | Cambio | PSNR | PSNR baja frec. | DeltaE76 | Contorno proxy | Full frames |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 2,000 s | 12.089.965 B | base | 35,952 dB | 41,382 dB | 2,788 | 8,88% | 60 |
| 15 | 1,000 s | 13.106.144 B | +8,40% | 36,421 dB | 41,962 dB | 2,607 | 7,91% | 58 |
| 10 | 0,667 s | 13.288.322 B | +9,91% | 36,541 dB | 42,130 dB | 2,557 | 7,68% | 67 |
| 5 | 0,333 s | 14.075.645 B | +16,42% | 36,731 dB | 42,410 dB | 2,499 | 7,30% | 86 |

PSNR mas alto es mejor; DeltaE y contorno artificial mas bajos son mejores. El contorno
es un proxy experimental sobre gradientes suaves, no una metrica perceptual estandar ni
un umbral universal de aceptacion.

El PSNR de esta tabla usa los 231 cuadros y MSE RGB agregado. No se compara directamente
con el PSNR historico de la instancia 001, calculado sobre nueve cuadros.

Con 5 frames, respecto de 30:

- el error perceptual de color bajo aproximadamente 10,4%;
- los contornos artificiales asociados al banding bajaron aproximadamente 17,8%;
- el archivo crecio 1.985.680 bytes;
- la RAM de la matriz, el byte por celda y el algoritmo del renderer no cambiaron;
- los frames completos ZLIB aumentaron de 60 a 86, reduciendo continuidad DELTA y
  agregando algunas descompresiones/subidas completas en el player.

### Version seleccionada para probar en Smart TV

- Archivo: `outputs/TKN-2441-GANADOR-graphic-kmeans-block5.asclv`.
- Tamaño: 14.075.645 bytes.
- SHA-256: `C74CE669AEE4F10788BE8EAD02971A487E95E65D7E1E326FC26BDD3E759BC798`.
- Flags ASCL: `0x1A`; CRC validado.

Comando reproducible:

```text
python backend/make_clip.py "TKN-2441-GANADOR- 15seg-.mp4" \
  --out outputs/TKN-2441-GANADOR-graphic-kmeans-block5.asclv \
  --profile graphic --fps 15 --palette block --palette-block-frames 5 \
  --palette-algorithm kmeans-rgb --reconstruction soft --dither off
```

### Decision y alcance

- Para equilibrio general, 10 frames entrega casi toda la mejora con +9,91% de peso.
- Para esta demostracion y una prioridad explicita de maxima calidad, se seleccionan
  5 frames: la reduccion de banding es medible y +1,99 MB fue considerado aceptable.
- Esto no convierte 5 frames en default universal. Debe repetirse el barrido si cambia
  cualquier condicion enumerada al comienzo del documento.
- Falta registrar la prueba fisica en cada familia de Smart TV. Si los 26 frames completos
  adicionales producen tirones en un decoder especialmente lento, 10 frames es el
  fallback ya medido; no se debe bajar calidad por suposicion antes de probarlo.

### Resultado en dispositivos reales

Pendiente.

## Instancia 003 - Oklab, bloques adaptativos, estabilidad, auto y resolucion

Fecha: 2026-08-12.

### Motivo y alcance

Se aplicaron las mejoras 1 a 5 manteniendo ASCL v1: K-means Oklab, renovacion de paleta
por cambio numerico de color, estabilidad temporal, dithering calibrado y perfiles
seleccionables 640x360, 768x432 y 960x540. No se uso IA ni deteccion de objetos. Todo el
trabajo nuevo ocurre en el encoder de PC; el player recibe la misma matriz de indices.

La fuente, FPS, 256 colores, threshold 0, reconstruccion `soft`, audio y 231 frames son
los mismos de la instancia 002. La metodologia y las tablas completas se conservan en
`docs/BENCHMARK-V1-ADAPTATIVO-OKLAB.md`.

### Por que el adaptativo no quedo en 5..30

El primer candidato produjo 11 bloques de hasta 30 frames y peso 12.554.539 B. Mejoro
el error perceptual puntual, pero compartia una paleta durante 1,5 a 2 segundos y perdia
calidad de baja frecuencia. Al limitar el maximo a 10, sin convertirlo en intervalo fijo,
el mismo detector produjo 27 bloques de 1..10 frames, promedio 8,56, y mantuvo un hard
cut exacto. Bajar el umbral 0,20 a 0,15 casi no cambio la segmentacion.

Esta es una conclusion de esta instancia: el maximo de 10 queda como default conservador
de calidad, pero el valor sigue editable. Los cortes siguen dependiendo del color real y
pueden ocurrir antes; no se renueva obligatoriamente cada 10 frames.

### Evidencia resumida

| Variante | ASCLV | DeltaE OK | Mesetas | PSNR fuente 1080p bilinear | Decode ref. | RAM Canvas min. |
|---|---:|---:|---:|---:|---:|---:|
| block5 RGB 640 | 14.075.645 B | 0,989 | 61,26% | 28,026 dB | 1,209 ms/f | 15,64 MiB |
| adaptativo Oklab 640 | 13.196.334 B | 0,812 | 59,71% | 27,765 dB | 1,208 ms/f | 14,78 MiB |
| adaptativo Oklab auto 768 final | 17.935.310 B | 0,824 | 59,50% | 28,585 dB | 1,684 ms/f | 20,27 MiB |
| adaptativo Oklab auto 960 exploratorio | 26.069.769 B | 0,816 | 58,48% | 30,146 dB | 2,562 ms/f | 29,81 MiB |

La auditoria Oklab de baja frecuencia del 640 adaptativo 5..10 bajo de 0,1432 a 0,0810
frente al block5 RGB, y el RMS de contorno suave bajo de 0,1278 a 0,1108. Esto motivo
conservar Oklab aunque el PSNR RGB de grilla no aumentara: miden objetivos diferentes.

El dither auto se mantuvo conservador. En HQ cambio 0,57% de las celdas y en ultra 0,69%,
con presupuesto maximo de 5%; sus indices quedan horneados y no agregan CPU/GPU al player.

### Decisiones

- Conservar 640 adaptativo Oklab sin dither como perfil eficiente.
- Seleccionar 768 adaptativo Oklab con dither auto como candidato HQ recomendado.
- Mantener 960 como perfil ultra opcional hasta medirlo en dispositivos fisicos.
- Mantener estabilidad maxima 0,25 en esta version para que la paleta conserve continuidad;
  contrastar 0,10 en clips fotograficos antes de universalizar el valor.
- No cambiar el formato: los tres archivos son ASCL v1, flags `0x1A`, CRC valido y audio
  incluido. Canvas2D y WebGL1 siguen consumiendo la misma matriz.

### Versiones conservadas

- Eficiente: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-efficient-640.asclv`,
  13.196.334 B, SHA-256
  `D53611B89991CF01FBFB7E08AAE31BCEDD0AE2DD6C06AB0D5D5E9033D0BC6875`.
- HQ recomendado: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv`,
  17.935.310 B, SHA-256
  `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`.
- Ultra: medicion exploratoria local; debe regenerarse con el guard final de textura
  antes de entregarlo o versionarlo.

### Resultado en dispositivos reales

Pendiente. No convertir los tiempos del decoder Python en una garantia de Smart TV;
medir cuadros perdidos, CPU y RAM en Canvas2D y WebGL1 por familia de equipo.

## Instancia 004 - Runtime v1 acotado, cambios exactos y renovación de caché

Fecha: 2026-08-14.

### Motivo y alcance

Se optimizó el frontend para el candidato HQ 768 sin volver a codificarlo y sin cambiar
ASCL v1. El objetivo fue reducir asignaciones, trabajo de conversión y retención de
recursos, manteniendo Canvas2D, WebGL1 y sintaxis ES5/ECMAScript 2015.

Esta instancia no mide todavía un Smart TV físico. Las cifras temporales provienen de
Node en la PC y describen únicamente el trabajo JavaScript aislado.

### Artefacto control

- Archivo: `outputs/TKN-2441-GANADOR-v1-adaptive-oklab-hq-768.asclv`.
- Tamaño: 17.935.310 B.
- SHA-256 antes y después:
  `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`.
- Matriz: 768x432, 231 frames, 15 FPS, 256 colores.
- Tags: 89 ZLIB, 1 DELTA y 141 DELTA_MASK.

El binario quedó idéntico. Las mejoras pertenecen solo al reader, inflate, renderers y
player TV.

### Reader e inflate

- offsets consultados directamente con `DataView`, sin `Array` por frame;
- keyframes en bitset: 29 B para 231 frames;
- estructura completa y CRC32 cuando está presente/no nulo validados al abrir;
- inflater zlib ES5 con CMF/FLG, Adler32, bounds, truncado, árboles y backreferences
  validados;
- inflate directo a un `Uint8Array` reutilizable, sin `dest=[]` ni copia final;
- scratch adaptativo: límite defensivo de 1.658.880 B para cualquier DELTA del HQ,
  pero uso real estable de 331.776 B con este archivo;
- bitset exacto de celdas modificadas: 41.472 B.

El reader anterior creaba durante cada inflate un Array JavaScript de una entrada por
byte y luego un segundo `Uint8Array`. Para un full HQ eran al menos 331.776 slots JS más
331.776 B tipados; el tamaño real de los slots depende del motor. La versión nueva retiene
un scratch tipado de 331.776 B y lo reutiliza. Esto reduce presión de GC aunque agrega el
bitset persistente de 41.472 B.

### Conversión y presentación

La primera implementación por una única banda vertical se midió antes de aceptarla. En
este clip los cambios están dispersos y solo evitaba 0,44% de filas. El reader pasó a
unir un bit por celda durante cada `seek`, incluidos frames omitidos.

Sobre los 231 frames:

- conversiones índice a RGBA evitadas: 46,14%;
- cinco pasadas alternadas en Node: 322,68 ms por clip con conversión completa frente a
  260,69 ms usando celdas exactas, una reducción de 19,21% en esa etapa;
- en decode más conversión, la mejora medida fue aproximadamente 4,7%; el costo de unir
  el bitset quedó dentro del ruido después de usar copias tipadas nativas;
- el upload/`putImageData` sigue usando una banda cuando los cambios están dispersos;
  esta medición no afirma una reducción equivalente de GPU ni del tiempo total del TV.

Los tiempos son una medición puntual y no portable de esta PC con Node v24.19.0: cinco
pasadas alternadas sobre el mismo clip ya cargado, sin red, audio, DOM ni GPU reales. No
constituyen un benchmark de Smart TV ni quedaron asociados a un artefacto de medición
versionado; los gates físicos de VAL-001 reemplazarán estas cifras para aceptar el cambio.

Canvas2D y WebGL1 llaman la misma API `fillRGBAChanged`. Primer frame, paleta, RAW, ZLIB,
metadata dirty inválida o un reader anterior fuerzan el camino completo. El sentinel
vacío canónico evita conversión, upload y draw en un frame sin cambios.

### Robustez de presentación

- WebGL solicita un contexto sin alpha, antialias, depth ni stencil y reintenta con la
  llamada legacy si el WebView no acepta atributos;
- valida `MAX_TEXTURE_SIZE` antes del RGBA;
- prueba una sola vez `texImage2D` y `texSubImage2D`; si un driver falla, usa upload full
  exacto o degrada a Canvas;
- una excepción o `webglcontextlost` conserva reader, frame, audio, reloj y RAF al caer
  a Canvas2D;
- `dispose()` libera explícitamente textura, shaders, programa, buffer, RGBA, ImageData y
  contexto cuando se actualiza el video;
- un bundle inválido libera también Blob URL y audio.

### Renovación de caché con URL base estable

`tv-player.html` conserva `./outputs/clip.asclv`. El menú técnico oculto se abre con la
tecla 9 moderna/numpad o con la pestaña translúcida `MENU` inferior izquierda. La acción:

1. detiene playback y aborta una XHR anterior;
2. libera audio, reader, Canvas y recursos WebGL;
3. rota un token de query persistido bajo `try/catch`;
4. envía `Cache-Control: no-cache` y `Pragma: no-cache` cuando el XHR los permite;
5. descarga el mismo recurso base otra vez.

Esto no borra la caché HTTP global: una página no tiene autoridad para hacerlo y las URLs
tokenizadas anteriores quedan a cargo de la política del navegador/servidor. En un browser
legacy, `keyCode=9` continúa siendo Tab para no romper navegación; el hotspot es el fallback.

### Validación

- 26 artefactos ASCL/ASCLV locales decodificados;
- HQ completo, 231 frames y seeks inversos;
- RGBA incremental idéntico al full en los 231 frames;
- 300 streams zlib stored/fixed/dynamic;
- 67 tests Python y 7 suites JavaScript verdes;
- corrupción de header, CRC, offsets, bloques, paletas, tags, DELTA, MASK y zlib rechazada;
- DELTA v1 desordenado/repetido conservado por compatibilidad (`última escritura gana`),
  con dirty set único y validación completa antes de mutar la matriz;
- tests runtime con DOM/XHR/GPU falsos verifican fallback y limpieza sin recargar página.

### Decisión y límites

- Adoptar los cambios para la prueba física HQ 768: no aumentan el ASCLV ni cambian su
  matriz, calidad, FPS o compatibilidad binaria.
- Desplegar `cache-refresh.js` junto con `tv-player.html` y los demás scripts.
- No atribuir el 19,21% al tiempo total del TV: solo mide la etapa de conversión en PC.
- Falta medir p50/p95, cuadros perdidos, RAM, CPU y temperatura en los equipos objetivo.
- El `outputs/clip.asclv` local puede no ser el HQ; en el servidor se debe publicar el
  artefacto HQ bajo ese nombre si se quiere que el player estable lo abra.

## Instancia 005 - Primera revisión ASCL v2 exacta y experimento de remap

Fecha: 2026-08-14.

Estado: **implementación y verificación local cerradas**. El artefacto HQ v2 final ya fue
generado, identificado por hash y comparado cuadro por cuadro. La promoción de v2 sobre
v1 en Smart TV sigue pendiente de la prueba física TV-02.

### Motivo y alcance

Se implementó una revisión del codec que representa con menos bytes la misma matriz de
índices ya aprobada en v1. No vuelve a cuantizar el video, no usa IA ni una persona para
elegir calidad y no aplica near-lossless. La selección compara longitudes binarias de
candidatos reversibles.

La revisión fija:

- envelope `ASCLVID2` de 16 B: magic, `ascl_len`, `audio_len`, ASCL y audio;
- header ASCL de 32 B, byte 26 `tile_size=16`, byte 27 `codec_flags=1`;
- CRC v2 sobre bytes `0..27` y `32..EOF`;
- tags 0..3 v1 como fallback, 4..7 regionales y 8/9 predictores;
- opcodes `SKIP_RUN`, `SOLID`, `SPARSE`, `MASK`, `PACK1`, `PACK2`, `PAL4`, `PAL8`;
- LEB128 uint32 canónico, máscaras/packing LSB-first y cobertura exacta de tiles;
- predictores LEFT, TOP, GRADIENT, PREVIOUS_SUB y PREVIOUS_XOR, todos reversibles;
- `--format v1|v2`, con **v1 como default**;
- ReaderV2 ES5 y factory compartidos por Canvas2D/WebGL1.

`PACK4` era un nombre preliminar de `PAL4`; no son opcodes distintos. Solo `SKIP_RUN`
tiene longitud de corrida. `SOLID` siempre cubre un tile y no existe `SOLID_RUN`.

### Invariante de compatibilidad y tamaño

El transcodificador conserva por frame el tag/payload v1 original. Regional o predictor
solo gana si su payload es estrictamente menor; un empate conserva el candidato anterior.
Como header, offsets, frame header, paleta y envelope mantienen su tamaño, el v2 no puede
crecer respecto del v1 de entrada. El audio de un bundle se copia byte a byte.

La matriz, paleta visible, FPS y dimensiones son las mismas. V2 inicial solo admite
`mode=PIXEL`; v1 continúa cubriendo los demás modos.

### Resultado final exacto sin remap de paleta

Se transcodificó el HQ 768 definitivo sin remap y sin volver a cuantizar:

| Evidencia | V1 | V2 |
|---|---:|---:|
| Bundle | 17.935.310 B | 17.935.305 B |
| ASCL interior | 17.754.437 B | 17.754.432 B |
| Audio | 180.857 B | 180.857 B, idéntico |
| Tags R/Z/D/M | 0 / 89 / 1 / 141 | 0 / 89 / 0 / 141 |
| Tags regionales Kraw/Kz/Draw/Dz | — | 0 / 0 / 1 / 0 |
| Tags predictores Kz/Dz | — | 0 / 0 |

- V1 SHA-256: `346B4BE704E15B1855DB15C989774116247600C5911A98E908BB7FAD2E15BB70`.
- V2 SHA-256: `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A`.
- `ReaderV1` y `ReaderV2` reconstruyeron RGBA idéntico en **231/231 frames**.
- El audio de 180.857 B fue idéntico byte por byte.
- CRC interior v1 y v2 válidos; envelope e inner version concordantes.

El ahorro real es **5 B**: un DELTA v1 fue reemplazado por un
`REGIONAL_DELTA_RAW` más corto. El resto mantuvo sus payloads v1. El dato no justifica
promover v2 por peso en este clip, pero demuestra que el invariante de no crecimiento y
la compatibilidad exacta funcionan sobre el artefacto de producto.

### Experimento offline de remap exacto

Se evaluó reordenar IDs dentro de cada época/GOP y permutar conjuntamente las entradas
RGB. Este remap no cambia el color mostrado: cada índice nuevo apunta al mismo RGB que el
índice anterior correspondiente.

Resultado de laboratorio:

| Métrica | Resultado |
|---|---:|
| GOP con candidato binariamente menor | 89 / 89 |
| Bundle base | 17.935.310 B |
| Bundle remapeado estimado | 17.763.683 B |
| Ahorro | 171.627 B (0,9569%) |
| RGB reconstruido byte-exacto | 231 / 231 frames |
| Tags predictores | 94 / 231 |
| Distribución | 28 LEFT, 16 TOP, 50 PREVIOUS_SUB |
| Tiempo offline del laboratorio | 414,4 s |

Sin remap no se elegía ningún predictor en este HQ. El remap hace que 94 frames usen
predictores; esto puede aumentar trabajo de inflate/reconstrucción en el dispositivo,
aunque el procesamiento offline prolongado sea aceptable.

### Reader, dirty y memoria

ReaderV2 valida header, CRC, offsets, bloques, paleta, bounds, stream completo, padding e
índices antes de consolidar un frame. El dirty set combina celdas exactas para cambios
dispersos y tiles para comandos densos; keyframe/paleta marca full. Canvas2D y WebGL1
consumen la misma matriz y API.

El gate de memoria se corrige: no se promete cero memoria proporcional. `cells`, RGBA,
bitsets y scratch dependen de la grilla. Se exige que el loop estable reutilice buffers
acotados y no reserve un nuevo frame completo en cada cuadro.

### Decisión de esta instancia

- Mantener `--format v1` como default.
- Conservar v2 exacto como salida opt-in; la verificación local queda cerrada.
- **No implementar ni activar el remap por defecto**: menos de 1% de ahorro estimado no
  compensa asumir una posible regresión de CPU en TVs viejos.
- Tratar el remap como perfil futuro solo si un benchmark físico demuestra CPU, RAM,
  p95 y cuadros perdidos equivalentes o mejores.
- Mantener descarga completa/cacheable; streaming y Range no forman parte de esta revisión.
- Ejecutar TV-02 en equipos reales antes de una decisión de producto. El HQ final ya fue
  generado sin sobrescribir v1 y la igualdad Python/JavaScript quedó comprobada.

## Instancia 006 - Cierre del artefacto, player TV y preparación reproducible

Fecha: 2026-08-22.

Estado: **cierre local preparado para publicación**, sin cambio del codec ni de la matriz
aprobada en la Instancia 005. Referencia: tag `asclv2-exact-hq-v0.2`.

### Motivo y alcance

Después de aceptar visualmente el HQ v2 se ordenó la entrega: conservar un único ASCLV
útil en `outputs/`, hacer accesible el menú técnico de caché, eliminar dependencias de
prueba sobre artefactos ignorados y dejar inequívoco qué documentación está vigente.

### Artefacto vigente

- Archivo local: `outputs/clip.asclv`.
- Origen lógico: `TKN-2441-GANADOR-v2-adaptive-oklab-hq-768.asclv`.
- ASCLVID2, 768x432, 231 frames, 15 FPS.
- Tamaño: 17.935.305 B; audio incluido: 180.857 B.
- SHA-256:
  `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A`.

Esto corrige la incertidumbre histórica de la Instancia 004: el `clip.asclv` local actual
sí es el HQ v2 exacto. El nombre estable solo pertenece a la ruta de despliegue.

### Limpieza y publicación

- `outputs/` quedó con un único archivo, `clip.asclv`; fixtures de tests viven en
  `tests/fixtures/` y los resultados regenerables están ignorados.
- Los binarios v1 anteriores permanecen recuperables en el historial/tag, aunque no en
  `HEAD`. Una publicación de toda la historia también los publica; no se reescribe sin
  decidir primero derechos y visibilidad del repositorio.
- El clip v2 no está en Git. Se distribuye como asset de release solo si se confirman sus
  derechos, con hash y tamaño documentados.

### Player TV y caché

- La pestaña inferior izquierda ahora muestra `MENU` con opacidad visible y conserva la
  tecla 9 como acceso alternativo.
- La renovación libera reader, audio, Canvas/GPU, rota un token y revalida la misma ruta.
- No se presenta como borrado global: ETag, Cache-Control y pruebas fría/caliente siguen
  siendo responsabilidad de CACHE-001 y del servidor PHP.
- Los mensajes provenientes de XHR/parser se insertan como texto, no como HTML.

### Robustez del tooling

- `make_clip.py` rechaza una salida que no termine en `.asclv` o que coincida con la
  fuente, evitando sobrescritura/borrado accidental.
- Sin `--keep`, los `.ascl/.mp3` intermedios viven en un directorio temporal único; con
  `--keep`, una colisión se rechaza en lugar de sobrescribirse.
- El bundle final se publica con escritura temporal y reemplazo atómico; un fallo conserva
  la versión anterior y en POSIX se preservan/aplican permisos legibles por el servidor.
- Los dos helpers antiguos que autocargaban checkpoints pickle predecibles se retiraron
  del árbol publicable y permanecen recuperables en el historial Git.
- Si no se extrae audio se emite una advertencia explícita.
- Una clonación limpia ya no necesita el clip de demostración para probar la página; el gate
  `--require-release-artifact` sí lo exige antes de crear un release.
- Se agregó un smoke test real sobre `inputs/synthetic.mp4`: encode v1, transcode v2,
  decode exacto y bundle.

### Validación

- 115 pruebas Python aprobadas.
- 11 suites JavaScript aprobadas, incluida una auditoría global de sintaxis/API legacy.
- `outputs/clip.asclv` validado como ASCLVID2 completo, con audio y hash esperado.
- El workflow de CI queda configurado para ejecutar la misma regresión en Python 3.8/3.11
  y Node 20 sin iniciar servidores ni descargar artefactos de producto. La primera corrida
  remota verde debe registrarse después del push.

### Decisión y límites

- Esta es la versión correcta para continuar y para preparar el repositorio remoto.
- V1 sigue siendo el default; v2 continúa opt-in hasta TV-02 porque en este clip ahorra
  solo 5 B y todavía no demuestra menor CPU/RAM física.
- No se implementa un selector automático de calidad por videos/segmentos. FPS, grilla y
  colores son explícitos; el automatismo solo toma decisiones numéricas verificables una
  vez fijada la matriz.
- Intervención matricial, near-lossless y Range permanecen en revisiones futuras separadas.
- El push público queda condicionado a decidir licencia/procedencia y derechos sobre los
  cuatro videos del historial y el clip de release.

## Instancia 007 - Referencia HQ reproducible en CI y arranque del modelo CI-only

Fecha: 2026-08-27. Contexto: nueva máquina de trabajo sin Python/Node (decisión del
operador); validación por GitHub Actions en cada push. El `clip.asclv` del release v0.2
(SHA `6FF3E71E…`) quedó en una máquina anterior y no es regenerable sin su V1 autorizado.

### Medición

Workflow `encode` run #1 (commit `7286399`), fuente `TKN-2443-GANADOR- 15seg-.mp4`
(rama `assets`), parámetros: `--format v2 --profile graphic-hq --fps 15
--palette adaptive --palette-algorithm kmeans-oklab --dither auto`.

Fila cruda de `tools/bench_ref.py --source`:

```text
| clip.asclv | 18646530 | 18829899 | 0.2433 | 231 | 94 | 9 | ZLIB:94;DELTA_MASK:136;RDELTA_RAW:1 | 34.29 | 0.00793 | f3051baafc17a0edf8e4e45e02d8c88287213ab73137f92088470ff4ce591527 |
```

768×432, 231 frames, 15 FPS, paleta 256, CRC OK (verificado por `ascl_decode` en el
mismo run).

### Conclusión y alcance

- Esta fila es la **nueva referencia HQ de medición** (P-02 cerrada, adaptada): se
  regenera de forma reproducible en CI, con SHA verificable, en lugar de depender de un
  binario congelado local.
- El HQ histórico del release v0.2 queda como evidencia no regenerable; sus números
  (`BENCHMARK-V2-HQ-768.md`) siguen siendo válidos para su clip (TKN-2441).
- Alcance: perfil graphic-hq 768 con estos parámetros exactos. Cambios de grilla, FPS,
  paleta o dither exigen una fila nueva.

## Instancia 008 - W-06: inflate.js con bit-buffer y tabla de 9 bits

Fecha: 2026-08-27, commits `ee1d104` (+ regresión verde en `c6e55a8`).

### Medición

Workflow `bench-inflate` (ubuntu-latest, Node 20), corpus determinista de
`tools/bench_inflate.js`, 300 repeticiones, HEAD `ee1d104` vs baseline `90e4b43`:

```text
                          baseline          W-06            mejora
rachas   253 KiB          357,5 ms          360,9 ms        ~igual
gradien  253 KiB        2.904,1 ms        1.025,9 ms        2,8x  (25,5 -> 72,3 MB/s)
ruido     64 KiB           30,3 ms           31,0 ms        ~igual
total                   3.291,8 ms        1.417,7 ms        2,3x
```

### Conclusión y alcance

- La ganancia se concentra donde el runbook la predijo: payloads dominados por
  decodificación Huffman (gradientes con dither, el perfil real del ASCL HQ).
  Rachas y ruido están dominados por la copia LZ77/stored y no cambian.
- Salida byte-idéntica garantizada por la regresión completa: fuzzing W-05
  (4000 mutaciones + dirigidos + bomba) y todas las suites de readers en verde.
- Alcance: medición en runner x64 de CI; la cifra absoluta en TV será otra,
  la relación debería sostenerse. Revalidar en F8 (validación física).

## Instancia 009 - E-06: glifos horneados e inspeccion visual

Fecha: 2026-08-27, commits `bc57e04` + `b0c2058` (normalizacion al pico).

- Tabla de referencia 8x12 (workflow `bake-glyphs`, DejaVuSansMono de
  ubuntu-latest): 11 glifos, 1.056 bytes, SHA-256
  `2ee438f4558832c31d8c8bb57a9939b73a65d6df11a9b18a1d906897f533042c`.
  Dos corridas byte-identicas verificadas con `cmp` dentro del mismo run.
- **Inspeccion visual (una vez, como exige el runbook): aprobada.** Los diez
  digitos son legibles a 8x12 celdas, el antialias 247..250 suaviza bordes sin
  ensuciar el trazo 251, el fondo 246 es uniforme y el glifo 10 es todo 255.
- Decision de diseno: la cobertura se normaliza al pico de cada glifo antes de
  cuantizar (division entera). Sin esto, trazos mas finos que una celda (el 5
  a 8x12) nunca alcanzan "texto pleno". La tabla depende de la fuente y el
  tamano: la tabla que se embeba en produccion debe regenerarse y registrarse
  con su SHA en el entorno que la emita.

## Instancia 010 - W-09/W-10/W-11: optimizacion del decode regional v2

Fecha: 2026-08-28, commits `d0b64eb`+`d216909` (W-09), `83924e1` (W-10),
`fbb38db` (W-11). Herramienta nueva: `tools/bench_reader_v2.js` + workflow
`bench-reader` (grilla sintetica 224x224, tiles 16, 400 repeticiones de las
dos pasadas reales de `_walkRegional`; us/frame por caso).

### Medicion (us/frame, runner ubuntu-latest)

```text
              pre-W-09      W-09          W-11          acumulado
key mix       615,2         437,3         223,5         -64%
sparse        396,9         439,4 (*)     121,4         -69%
mask          220,1         210,2         388,9 (*)     (*)
total (ms)    492,9         434,8         293,5         -40%
```

(*) El runner de CI muestra varianza alta entre corridas (el mismo commit
midio sparse 338,8 y 439,4 en dos runs). La cifra confiable es la tendencia
del total y del caso keyframe, no el punto individual por caso.

### Conclusion y alcance

- W-09 conserva la pasada de validacion byte a byte y recorta la de
  aplicacion; ninguna corrupcion nueva es aceptable por construccion (la
  pasada 1 es identica) y la suite de corrupcion existente siguio en verde.
- W-11 aporta la mayor parte del recorte (uvarint con tabla, packed sin
  divisiones, dirty sin div/mod en caminos calientes, predictores sin
  recomputar el residual).
- El objetivo del runbook para W-09 (~15-20%) se supero en el agregado
  W-09+W-11 (~40% del walk regional). Cifras absolutas de TV quedan para F8.

## Instancia 011 - W-12: salto por byte en DELTA_MASK

Fecha: 2026-08-28, commits `b8c812d` (readers) + `ab96b8c` (caso de bench).

Bench `bench-reader` (caso `lmask`: DELTA_MASK legacy sintetico de ~5% de
densidad, dos tercios de los bytes de mascara en cero), HEAD `ab96b8c` vs
baseline `fbb38db`:

```text
lmask   169,4 us/frame -> 80,6 us/frame   (-52%)
```

El runbook estimaba ~29%; el perfil sintetico con exactamente 2/3 de bytes en
cero rinde mas. La equivalencia de salida la garantiza la suite existente
(dirty exacto y celdas identicas en ambos readers).

## Instancia 012 - E-08 (Zopfli) y E-10 (keyframes por corte)

Fecha: 2026-08-28. Commits: E-08 `8d4489d`, E-10 `1523f4d`.

### E-08 - Referencia HQ con Zopfli (workflow encode, 15 iteraciones)

```text
                      zlib (referencia)      zopfli            delta
clip.ascl             18.646.530 B           17.298.901 B      -1.347.629 B
clip.asclv (bundle)   18.829.899 B           17.482.270 B      -7,16%
bytes/celda/frame     0,2433                 0,2257
PSNR RGB / Oklab      34,29 / 0,00793        34,29 / 0,00793   identicos
tags                  ZLIB:94 DELTA_MASK:136 RDELTA_RAW:1      misma estructura
SHA-256               f3051baa...1527        ebfe2eb4c8e0148b1ce6730b990abc4f
                                             6283ed40bf7977b7e7c3f548b3134b36
```

- La calidad de imagen no cambia: Zopfli recomprime los mismos indices ya
  decididos. La estructura de tags es identica a la referencia.
- Costo: el encode HQ pasa de ~10 a ~40 minutos de CI. El input `zopfli` del
  workflow permite apagarlo para iteraciones rapidas.

### E-10 - Medicion sintetica (test cableado)

Corte parcial (2 filas sobre ruido incompresible, 8 frames): sin el flag la
cadena DELTA maxima es 7 y hay 1 keyframe; con `--scene-keyframes` el corte
agrega exactamente 1 keyframe (cadena maxima 3) y el decoder Python reconstruye
celdas identicas en ambos casos. Default off = salida byte-identica (test).
En el perfil HQ actual (paleta adaptive) los cortes ya abren bloque/keyframe,
por eso el flag es opt-in pensado para --palette global/block con keyint largo.

## Instancia 013 - E-09: barrido de tile_size sobre ambas referencias

Fecha: 2026-08-28. Workflow `encode` con `tile=sweep`, `zopfli=off` (comparable
con las referencias zlib). Round-trip exacto verificado por el transcodificador
en cada candidato (verify_roundtrip).

### HQ (TKN-2443, graphic-hq 768, adaptive/kmeans-oklab, dither auto)

```text
tile      4          8          12         16         24         32
bytes     18.646.195 18.646.497 18.646.530 18.646.530 18.646.530 18.646.443
ganador   4 (-335 B vs 16; 0,002%)
```

Solo 5 de 231 frames eligen el codec regional: los payloads v1 (ZLIB llenos y
DELTA_MASK) dominan y el tile_size casi no incide HOY en este perfil. SHA del
artefacto barrido: `7fc4aac6...789b` (18.829.564 B bundle).

### Sintetica (synthetic.mp4, mismos parametros de workflow)

```text
tile      4        8        12       16       24       32
bytes     368.020  363.562  368.020  357.979  368.020  368.020
ganador   16 (-2,73% vs v1; 37/60 frames regionales)
```

### Conclusion

- El mecanismo queda operativo (byte 26 + sweep determinista); el ganador HQ es
  marginal y el sintetico confirma el default 16. **El barrido definitivo va en
  S-4**, cuando el trellis espacial (E-23) cambie la estadistica por tile.
- Ambas referencias medidas con zlib puro; con Zopfli las magnitudes relativas
  pueden moverse y se re-mediran al regenerar artefactos de produccion.

## Instancia 014 - F7: runtime del overlay (S-5)

Fecha: 2026-08-28. Cuatro patas del runbook (F7-1..F7-4) mas la integracion de
producto, cada una con CI `regression` en verde sobre su commit.

### Verificacion cruzada Python/JS (gate de cierre de S-5)

`test_overlay_ref.py` encodea un clip REAL con `reserved=10` (pal_size 256,
reservadas en 246..255, paleta global, keyint 4, corte duro en el frame 4),
compone frame a frame con `backend/overlay_ref.py` y deja los fixtures;
`test_overlay_cross.js` reproduce el mismo clip con `reader.js` +
`overlay.js` (beforeSeek/seek/afterSeek) aplicando la misma linea de tiempo
de cargas ("0512" en f0, "9934" en f3, cruzando el keyframe):

```text
frames comparados        8 (64x32, 2048 celdas c/u)
resultado                byte-identico Python/JS en los 8 frames
clear()                  byte-identico al video base decodificado
INV-3 / INV-4            verificados sobre el clip del encoder (cola 246..255
                         intacta en cada epoca; ninguna celda base >= 246)
```

### Gates de INT-002 cubiertos por la regresion

- restauracion exacta tras `clear()`, seek hacia atras y reinicio de loop
  (`test_overlay_runtime.js`, ambos readers, con cambio de valor en vivo);
- control negativo: saltear el paso 1 del orden §9.2 (restaurar antes de
  decodificar) hace divergir la matriz -> el orden es obligatorio y el test
  lo detectaria;
- union de rects sucios: slots pintados y recien desactivados quedan
  marcados; celdas lejanas no (v1 bits exactos; v2 disyuncion celda/tile);
- un `field_id` o digito invalido no escribe nada (todo-o-nada en
  `setValues`/`setField`, espejo exacto en la referencia Python);
- canal de datos: corpus completo de §13 (longitud, caracteres, serial
  repetido/retrocedido, campo fuera de rango, vacia, gigante) con backoff
  exponencial acotado a 5 min solo ante error de red
  (`test_overlay_datachannel.js`);
- sin allocaciones en el loop estable: `overlay.base`/`overlay.values` se
  reservan una vez en attach (identidad verificada tras la reproduccion).

Los gates fisicos de INT-002 (costo p95 <10% del presupuesto de frame y RAM
medida en TV) quedan para F8-2/F8-4 (MEM-001 mide con y sin overlay), como ya
preveia el plan; en CI la RAM auxiliar es 3.840 B + 40 B por construccion.

### Dither y panel (INT-001 §11/§13)

`protected_rects` (E-05) quedo plumbeado hasta `make_clip --reserved`:
`encode_video(protect_panel=True)` excluye los 40 rects del panel canonico
(`backend/overlay_panel.py`, misma geometria que el sidecar por construccion).
Test: con proteccion, las celdas dentro de los rects son identicas al encode
con dither off; sin proteccion el mismo fixture SI trama dentro del panel
(control de no-vacuidad), en `selective` via encoder y en `auto` directo.

### Decisiones

- `attach()` devuelve null (no lanza) ante sidecar ajeno o clip sin reserva:
  el video sigue sin overlay (INV-7). `live-player.html` reemplaza a la demo
  de laboratorio y degrada con mensaje claro.
- El serial del canal solo avanza cuando la carga se ACEPTA completa: un
  serial nuevo con un campo invalido no se consume y puede reintentarse.
- `pad=0` deja los ceros a la izquierda como glifo vacio (10); `pad=1` los
  pinta. Mismo comportamiento en JS y Python, cubierto por ambos tests.

### Referencia HQ con overlay (workflow encode, run 33138773906)

`overlay=on`, `zopfli=on`, `tile=16`, resto perfil HQ de produccion:

```text
clip.asclv (bundle)   17.197.813 B   231 frames, 94 keyframes, 9 epocas
                      tags ZLIB:94 DELTA_MASK:136 RDELTA_RAW:1
PSNR RGB / Oklab      34,14 / 0,00799   (sin reserva: 34,29 / 0,00793 - la
                      paleta base pasa de 256 a 246 colores; costo esperado
                      de la reserva, INT-001 §4.1)
SHA-256 clip          7da584f177025d69485fa5732fbec2404c9e451e2fb3b9d301e295217555a51d
clip.slots            1.950 B, panel de 20 campos / 40 slots (glifos E-06)
SHA-256 slots         ec77023cb60826f1bb9b42c00eadb5ea72c49fc5b707c734e5855969f70c7c56
```

Reproduccion verificada en navegador con `live-player.html` + serve-local:
attach activo sobre el clip real, los 20 numeros de `data.txt` pintados y
persistentes a traves de cortes de escena y cadenas DELTA; el canal rechazo en
vivo una recarga con el mismo serial ("serial repetido o retrocedido") y la
carga simulada repinto el panel. La referencia HQ **sin** overlay
(`ebfe2eb4…4b36`) sigue vigente para comparaciones de compresion del carril E.

## Instancia 015 - INT-003-A: reserva ampliada a 32 entradas (224..255)

Diseño cerrado con el operador (D1..D6) en `DISENO-PARCHES-GENERICOS.md`.
`RESERVED_RGB_32` conserva bit-idénticas las 10 entradas de F7 en 246..255
(los glifos horneados y el sidecar v1 del panel siguen válidos sobre un clip
de reserva 32); agrega 22 colores de arte genérico en 224..245. Encoder ya
genérico en `reserved`; `make_clip --reserved` acepta 0/10/32 y rechaza
cualquier otro valor antes de tocar el archivo. Commit `7156fd9`, CI verde.

### Costo de calidad de la reserva de 32 (workflow encode, sintético)

Perfil HQ por defecto del workflow (graphic-hq 768, 15 fps, adaptive
kmeans-oklab, dither auto, v2, zopfli on, tile 16), única diferencia
`--reserved 32` (que además activa `protect_panel`):

```text
| referencia | .ascl | .asclv | B/celda | PSNR | Oklab | SHA-256 |
| sintético reserved=0  | 325.229 | 325.245 | 0,0163 | 31,29 | 0,01239 | a97ef086…b8cb |
| sintético reserved=32 | 308.491 | 308.507 | 0,0155 | 30,82 | 0,01331 | 26ab1952…3244 |
```

Runs 33174111941 (base) y 33174113632 (reserved 32). El archivo con reserva
es ~5% MENOR: la base pasa de 256 a 224 colores y el panel queda excluido del
dither (menos celdas cambiadas). El costo es −0,47 dB PSNR / +0,00092 Oklab
sobre el sintético; para el clip HQ real se medirá al cierre de INT-003-F.

## Instancia 016 - INT-003-F: clip HQ con parches genéricos (overlay=patches)

Workflow `encode` run 33176566955 (`overlay=patches`, `zopfli=on`, `tile=16`,
resto perfil HQ de producción), sobre `main` `da28408`:

```text
clip.asclv (bundle)   16.465.367 B   231 frames, 94 keyframes, 9 epocas
                      tags ZLIB:94 DELTA_MASK:136 RDELTA_RAW:1
PSNR RGB / Oklab      34,05 / 0,00827   (panel reserved=10: 34,14 / 0,00799;
                      sin reserva: 34,29 / 0,00793 - la base baja a 224
                      colores y el panel queda fuera del dither)
SHA-256 clip          c315a13a8b635aba1cd9383a0030b9f9b991ce9fff5d96f0020e375cc9eb8e63
clip.slots (v2)       15.511 B: 25 parches (11 mono 8x12 + 11 serif 26x36 +
                      3 palabras 64x14), 47 slots, 24 campos
SHA-256 slots         678b392dfa55ef262f0d57fe9dc1792e20440026de1a10f05c4dadec8a762c56
data.txt              58 B: serial 1 + payload de 48 digitos (con presencia)
```

Nota: el bundle con parches es ~4,3% MENOR que la referencia con panel
(17.197.813 B) — mas entradas reservadas = base mas chica y mejor compresion,
al costo de −0,09 dB PSNR frente al panel.

Reproducción verificada en navegador (`live-player.html` + serve-local):
attach v2 activo (48 digitos, 47 slots); el canal aplicó el serial 1 de
`data.txt` y rechazó la recarga ("serial repetido o retrocedido"); el numero
grande en serif dorada aparece en una posición DISTINTA en cada tercio del
clip (izquierda → centro → derecha) con la palabra de elección verde y el
panel de 20 números simultáneos; la carga simulada generó un payload válido
por campo (dígitos de presencia incluidos) y repintó en pausa.

## Instancia 017 - INT-006-A: fondo sin reserva, 768 vs 960 (overlay=off)

Dos encodes del workflow `encode` sobre `main` `7cc1fdc` con `overlay=off`,
`zopfli=on`, `tile=16`, `palette=adaptive`, `algorithm=kmeans-oklab`,
`dither=auto`, `fps=15`, formato v2:

### graphic-hq 768 (run 33193293258) - fondo de producto

```text
| clip.asclv | 17298901 | 17482270 | 0.2257 | 231 | 94 | 9 | ZLIB:94;DELTA_MASK:136;RDELTA_RAW:1 | 34.29 | 0.00793 | ebfe2eb4c8e0148b1ce6730b990abc4f6283ed40bf7977b7e7c3f548b3134b36 |
```

**Reproduce byte a byte la referencia HQ de P-02/E-08** (`ebfe2eb4…4b36`,
17.482.270 B): determinismo confirmado tras todo el carril INT (el encoder
no cambió para clips sin reserva). PSNR 34,29 dB / Oklab 0,00793 — la base
recupera los 256 colores (+0,24 dB frente al clip de parches `c315a13a…`).

### graphic-ultra 960 (run 33193299286) - candidato «mayor calidad»

```text
| clip.asclv | 24819635 | 25003004 | 0.2073 | 231 | 119 | 9 | ZLIB:119;DELTA_MASK:108;RDELTA_RAW:1;RDELTA_ZLIB:3 | 34.40 | 0.00776 | 31348a83da40d0997379c03f2e7f863ae5b41a9dee17317f3922baed07585688 |
```

+0,11 dB PSNR y −2,1% de error Oklab frente al 768, a +43% de bytes
(25,0 MB vs 17,5 MB) y más celdas por frame en el decode del TV. Decisión:
el **768 queda como fondo de producto** (valores manuales del operador
prevalecen); el 960 queda medido y citable por SHA si el operador lo
prefiere al verlo.

### outputs/ y verificación en navegador

`outputs/clip.asclv` = el 768 (SHA local verificado); `clip.slots` y
`data.txt` **borrados** (eran del clip de parches). `logo.png` (logo
TeleKino del operador) queda para la imagen nativa. Player local:
standalone activo (3 campos de 2 dígitos por tercios en serif dorada,
«Simular carga» los cambia, zoom 2 nítido, «Limpiar panel» restaura el
fondo, logo nativo persistente en play/pausa/clear); consola limpia salvo
los 404 esperados de clip.slots/data.txt (falla suave INV-7).

## Instancia 018 - E-12: refit de paleta a la asignación real (bench 768)

Implementación en `09c4261` (CI `regression` 33202937713 en verde: 209
pruebas Python + 26 suites JS). Flag opt-in `--palette-refit 0..10`
(default 0 = bytes idénticos a los históricos): tras construir cada
paleta, se reasignan las muestras con la MISMA regla de cuantización del
encode (Oklab exacto/LUT para kmeans-oklab, Pillow para el resto), cada
entrada base se recalcula como la media (`np.bincount`) de sus píxeles
asignados y la iteración se acepta **solo si baja el error** en la
métrica del algoritmo (nunca degrada). Reservadas intactas (INV-4),
`pal_img` solo-base (INV-3), enhebrado en los tres caminos
(global / block / adaptive / per-frame, incluido median-cut).

Dos encodes del workflow `encode` sobre `main` `09c4261`, perfil
graphic-hq 768, `overlay=off`, zopfli, tile 16, adaptive/kmeans-oklab,
dither auto, 15 fps, v2 — idénticos a la referencia P-02 salvo el flag:

### `--palette-refit 3` (run 33203084602)

```text
| clip.asclv | 17242399 | 17425768 | 0.2250 | 231 | 92 | 9 | ZLIB:92;DELTA_MASK:138;RDELTA_RAW:1 | 35.39 | 0.00734 | 514be81e7f1af07d50f3d565d25deaa44b21f916e0ff360484da976be5a01aff |
```

### `--palette-refit 5` (run 33203086375) - nuevo fondo de producto

```text
| clip.asclv | 17196490 | 17379859 | 0.2244 | 231 | 92 | 9 | ZLIB:92;DELTA_MASK:138;RDELTA_RAW:1 | 35.46 | 0.00732 | adef9e533b01fdd489ec6dacf1265f07072ecba8d15e88e79b7bd2dd5a5c05bb |
```

Contra P-02 (34,29 dB / 0,00793 / 17.482.270 B): refit 3 = **+1,10 dB,
−7,4 % Oklab, −0,32 % bytes**; refit 5 = **+1,17 dB, −7,7 % Oklab,
−0,59 % bytes**. Mejora de calidad y de tamaño a la vez, con costo solo
offline. El 768 refit 5 supera incluso al 960 ultra sin refit (34,40 dB,
25,0 MB) con 31 % menos de bytes: la comparación 768 vs 960 de la
Instancia 017 queda desactualizada y debería repetirse con refit si el
operador retoma la idea del 960.

Decisión: **refit 5 pasa a ser el fondo de producto** («al cerrar E-12,
re-encodear el fondo», runbook §Próxima acción): `outputs/clip.asclv` =
`adef9e53…c05bb` (SHA local verificado). El flag sigue opt-in para que
las referencias históricas (P-02 `ebfe2eb4…4b36` incluida) se mantengan
reproducibles byte a byte; el workflow lo pasa por `extra`.

## Instancia 019 - E-13: cierre de Lloyd en dominio uint8 (bench 768)

Implementación en `a64c7ce` (CI `regression` en verde). El Lloyd principal
de `build_perceptual_palette` optimiza centros Oklab continuos; el gamut
map, el redondeo a uint8 y la reparación de duplicados los movían DESPUÉS
de la última asignación. `_closing_lloyd_uint8` itera ese tramo final
restringido a paletas sRGB representables (asignar → promediar en Oklab →
mapear/redondear/reparar) y acepta cada vuelta **solo si baja la inercia
ponderada** — nunca degrada, conserva el orden de entradas (la alineación
temporal previa sigue válida) y es determinista. Opt-in
`--palette-uint8-refine 0..10` (default 0 = bytes idénticos), solo
kmeans-oklab; `info["uint8_refine_accepted"]` lo reporta.

Encode 768 `overlay=off` con `--palette-refit 5 --palette-uint8-refine 3`
(run 33207479295):

```text
| clip.asclv | 17258895 | 17442264 | 0.2252 | 231 | 93 | 9 | ZLIB:93;DELTA_MASK:137;RDELTA_RAW:1 | 35.46 | 0.00728 | a95d0bbc6ef0a2ed42c40a2cd0fbeb517e31279900f4a77fcdf9ec08cfdeacbf |
```

Contra el refit 5 solo (`adef9e53…`, 35,46 / 0,00732 / 17.379.859 B):
PSNR igual, **Oklab −0,5 %** (0,00732 → 0,00728), bytes **+0,36 %**
(+62.405 B). La inercia de muestra baja siempre por construcción (gate de
aceptación, testeado en `test_palette_uint8_refine.py`); sobre el clip
real la ganancia perceptual es marginal y cuesta unos KB de paleta menos
comprimible.

Decisión: **el fondo de producto sigue siendo el refit 5 solo**
(`adef9e53…c05bb` en `outputs/`); E-13 queda medido y citable
(`a95d0bbc…acbf`) — si el operador prefiere optimizar el error perceptual
puro, se activa agregando `--palette-uint8-refine 3` al `extra` del
workflow. El barrido definitivo de S-4 (artefactos finales) reevaluará la
combinación con el trellis de F5.

## Instancia 020 - E-14: paleta sobre todos los píxeles, dos pasadas (RSS)

Implementación en `f324f1e` (CI en verde: 231 pruebas Python + 26 suites
JS). El modo global ya no materializa el video (`allf = list(...)`):
kmeans-oklab hace **pasada 1** con `StreamingColorAggregate` (todos los
píxeles del stream, colapsados por color exacto con la masa anti-banding
de `smooth_gradient_weights`, compactación acotada) y ajusta la paleta con
`build_perceptual_palette(sample_aggregate=…)` **sin el límite de 65.536
muestras**; **pasada 2** re-lee el stream y encodea. Los algoritmos
Pillow/RGB muestrean sus 12 frames históricos con pasada de conteo +
pasada de muestreo — selección exactamente igual, **bytes idénticos**
(verificado por test contra la paleta esperada). `refit_palette` ganó
`sample_weights` (con `None` el camino E-12 es byte-idéntico).

Tres corridas 960 `graphic-ultra`, `palette=global`, kmeans-oklab, dither
auto, v2, **sin zopfli** (la compresión no afecta PSNR/RSS), medidas con
`/usr/bin/time -v` (workflow `86eb5ae`; fuente 15 s — el clip de 90 s del
runbook no existe en `assets`, desvío anotado):

```text
baseline (código viejo, run 33211360889):
| clip.asclv | 20768254 | 20951623 | 0.1734 | 231 | 107 | 29 | ZLIB:107;DELTA_MASK:110;RDELTA_RAW:1;RDELTA_ZLIB:13 | 31.50 | 0.01140 | 17061d273f7b763b9bbaf472383560dacad6a7c790861387d4b1115a4338e093 |
  RSS máximo 885.996 kB · wall 7:01.91
dos pasadas (run 33211958336):
| clip.asclv | 22502003 | 22685372 | 0.1879 | 231 | 103 | 29 | ZLIB:103;DELTA_MASK:113;RDELTA_RAW:1;RDELTA_ZLIB:14 | 31.23 | 0.01089 | d9785bf219e809a56f1d505c5e44adc1d753d982c9566700f0629fdc4e6720e1 |
  RSS máximo 433.316 kB · wall 8:47.71
dos pasadas + --palette-refit 5 (run 33212853307): BYTE-IDÉNTICO al
anterior (mismo SHA d9785bf2…) — el Lloyd del builder ya convergió sobre
el mismo agregado y la aceptación Oklab del refit no encuentra mejora.
  RSS máximo 434.124 kB · wall 6:33.61
```

Resultado: **RSS máximo −51 %** (886 → 433 MB) ✓ y **error Oklab −4,5 %**
(0,01140 → 0,01089) ✓; **PSNR RGB −0,27 dB** (31,50 → 31,23) ✗ frente al
criterio «PSNR igual o mejor». Causa entendida: el camino viejo muestreaba
por cuantiles 65.536 píxeles de solo 12 frames; el agregado usa la masa
anti-banding del video ENTERO, y kmeans-oklab optimiza ese objetivo
perceptual ponderado (mejora), no el MSE RGB (cede 0,27 dB). Es el
trade-off diseñado del anti-banding aplicado por fin a datos completos.

Decisión: **E-14 cierra con el desvío registrado** — el objetivo del
proyecto es perceptual y el modo global no es el de producto (adaptive).
Si el operador quiere paridad PSNR en global, el knob natural es exponer
el `gradient_boost` del agregado (pendiente opcional, no bloquea F3).
Bytes +8,3 % en global sin zopfli: consecuencia de la paleta más fiel a
gradientes (más entropía de índices); no afecta al producto.

## Instancia 021 - E-15: estabilidad temporal para los cuatro algoritmos

Implementación en `91a0e68` (CI en verde: 239 pruebas Python + 26 suites
JS). `_stabilize_rgb_palette` alinea 1:1 la paleta nueva con la del bloque
anterior reutilizando el `_align_to_previous` genérico sobre los valores
RGB exactos (permutación sin pérdida: conserva el significado de los
índices y las cadenas DELTA) y fusiona hacia la previa según
`temporal_strength`. Aplicada en `make_global_palette` (kmeans-rgb,
median-cut, fast-octree — con `pal_img` reconstruida) y en el per-frame de
median-cut; `encode_video` calcula descriptor y estabilidad per-frame para
los 4 algoritmos (antes solo kmeans-oklab). kmeans-rgb —el default de
make_clip— deja de ir sin estabilización.

**Error temporal en fronteras de bloque** (cierre del runbook), medido por
`test_palette_temporal_all.py` sobre stream sintético de gradientes
(valores impresos en el log del CI de `91a0e68`):

```text
fast-octree : antes=58.417  despues=4.333   (−93 %)
kmeans-rgb  : antes=2.917   despues=2.021   (−31 %)
per-frame   : antes=0.993   despues=0.993   (los centros ordenados ya alineaban en el sintético)
```

Δbytes sobre el clip real (768 graphic-hq, adaptive, kmeans-rgb, dither
auto, v2, sin zopfli):

```text
antes  (run 33213974855): | clip.asclv | 18855007 | 19038376 | 0.2460 | 231 | 91 | 9 | ZLIB:91;DELTA_MASK:129;RDELTA_RAW:1;RDELTA_ZLIB:10 | 36.74 | 0.00967 | 7e35dc82f2eddd1f910502bd66651161893443e28000ad51ef11c226892748f0 |
despues (run 33214345845): | clip.asclv | 18616144 | 18799513 | 0.2429 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:131;RDELTA_RAW:1;RDELTA_ZLIB:4 | 35.70 | 0.01066 | 9c7db07e2487e4c50e29eecdfe44c8568bbccf9bdc83aed20365b20c7d4cefb1 |
```

**Bytes −1,25 %** y RDELTA_ZLIB 10 → 4 (índices estables entre bloques =
regionales v2 más baratos). Costo estático del blending: PSNR −1,04 dB y
Oklab +10 % — es la retención de hasta 25 % de paleta previa
(`adaptive_stability_max`, default 0,25), exactamente la semántica que
kmeans-oklab ya aplicaba por diseño; con `--adaptive-stability-max 0`
queda solo la alineación (permutación pura, sin costo de fidelidad). El
producto (kmeans-oklab) no cambia de bytes por esta tarea.

## Instancia 022 - E-16: dither exacto medido; queda opt-in (--dither-exact)

Código en `a87014a` (CI en verde: 244 pruebas Python + 26 suites JS):
`exact_pairs` calcula base/partner/level por píxel desde el índice REAL
del cuantizador, eliminando el gate 555 que apagaba el tramado en
silencio. Bench sobre la config de producto (768 graphic-hq, adaptive,
kmeans-oklab, dither auto, tile 16, `--palette-refit 5`, zopfli):

```text
producto  (run 33203086375): | clip.asclv | 17196490 | 17379859 | 0.2244 | 231 | 92 | 9 | ZLIB:92;DELTA_MASK:138;RDELTA_RAW:1 | 35.46 | 0.00732 | adef9e533b01fdd489ec6dacf1265f07072ecba8d15e88e79b7bd2dd5a5c05bb |
exacto    (run 33215511572): | clip.asclv | 18419043 | 18602412 | 0.2403 | 231 | 81 | 9 | ZLIB:81;DELTA_MASK:148;RDELTA_RAW:1;RDELTA_ZLIB:1 | 35.25 | 0.00762 | 0ed4cbbef7962058e75c81b5915f87bcdc08649fec987746b6dd46f08ef092f5 |
  wall 1:03:37 (antes 45:50, +39 %) · RSS máximo 691.644 kB
```

Resultado: **PSNR −0,21 dB, Oklab +4,1 %, bytes +6,0 %, tiempo +39 %** —
peor en las tres métricas registradas. Causa entendida: el gate 555
actuaba de facto como freno del tramado (menos píxeles tramaban); al
morir, traman muchos más píxeles y eso sube la entropía (DELTA_MASK 129 →
148, RDELTA_ZLIB 4 → 1) y baja el PSNR por píxel, sin que el proxy
perceptual del calibrado lo compense en estas métricas.

Decisión: **la exactitud E-16 queda opt-in** (`--dither-exact` en
make_clip/encoder, `exact_pairs=` en las APIs de dither), con default =
camino histórico por LUT byte-idéntico a pre-E-16. Así el producto
`adef9e53…` sigue siendo reproducible desde `main` (regla 5) y el fondo
instalado no cambia. El costo/beneficio real del dither exacto se
reevaluará con E-17 (presupuesto de dither en bytes), que es el freno
correcto para su mayor gasto de bytes. Test nuevo:
`test_default_path_keeps_historic_lut_gated_bytes` reconstruye el camino
histórico de forma independiente y exige bytes idénticos.

## Instancia 023 - E-17: el presupuesto de dither funciona; la decisión dither on/off queda del operador

Código en `6bc2676`/`b324446` (CI en verde): `--dither-byte-budget N`
opt-in mide los bytes reales del frame con la estructura exacta del
emisor (`encode_frame(..., fast_deflate=True)`, mismo prev/keyframe/
compress, zlib-9 puro para que la decisión no dependa de si Zopfli está
instalado) y, en modo `auto`, recorta por bisección determinista el
prefijo de tiles aceptados. Default `None` = salida histórica byte a
byte. Presupuesto en bytes y presupuesto del 5 % de celdas se aplican
JUNTOS.

Barrido completo sobre la config de producto (768 graphic-hq, adaptive,
kmeans-oklab, tile 16, `--palette-refit 5`, zopfli, `overlay=off`);
filas textuales de los artefactos:

```text
producto dither auto (run 33203086375): | clip.asclv | 17196490 | 17379859 | 0.2244 | 231 | 92 | 9 | ZLIB:92;DELTA_MASK:138;RDELTA_RAW:1 | 35.46 | 0.00732 | adef9e533b01fdd489ec6dacf1265f07072ecba8d15e88e79b7bd2dd5a5c05bb |
  392508 celdas tramadas · wall 45:50
budget 450          (run 33231255094): | clip.asclv | 17062681 | 17246050 | 0.2226 | 231 | 93 | 9 | ZLIB:93;DELTA_MASK:137;RDELTA_RAW:1 | 35.57 | 0.00725 | aabd518a5e195b477370c6e15c927c58ba69a58cbc40bc51deb9ebf0ae198bf6 |
  156947 celdas tramadas (40 %) · 99 frames limitados, 5115 tiles recortados · wall 48:41.15 · RSS 705.528 kB
budget 0            (run 33229100878): | clip.asclv | 16985223 | 17168592 | 0.2216 | 231 | 93 | 9 | ZLIB:93;DELTA_MASK:137;RDELTA_RAW:1 | 35.63 | 0.00721 | 909ba629c3044563d6eb1c012e57128e1d91c2292564de2fda88f66abfaaf68e |
  2 celdas tramadas · 204 frames limitados, 9232 tiles recortados · wall 49:04.75 · RSS 696.856 kB
dither off          (run 33231247505): | clip.asclv | 16985264 | 17168633 | 0.2216 | 231 | 93 | 9 | ZLIB:93;DELTA_MASK:137;RDELTA_RAW:1 | 35.63 | 0.00721 | 74be25ef6ebbcbc3ebf975bd10d348bb10badd8ec4e0800423f15f39c3a011f9 |
  0 celdas tramadas · wall 44:21.52 · RSS 700.320 kB
```

**El mecanismo de E-17 está validado.** El presupuesto es un knob
continuo y monótono, no un interruptor: 450 B/frame conserva 156.947 de
las 392.508 celdas tramadas (40 %) y cae proporcionalmente entre los dos
extremos en las tres métricas a la vez. Recorta por orden de aceptación,
o sea que lo que sobrevive es el tramo mejor rankeado por ganancia/costo.

**Hallazgo que corrige la lectura del primer bench:** `budget 0` y
`dither off` difieren en **41 bytes** y son idénticas en PSNR, Oklab,
B/celda/frame, keyframes y tags. Presupuesto 0 *es* dither apagado (las
2 celdas que se cuelan son esos 41 bytes), pero pagando **49:04 contra
44:21** de encode. Como ajuste de producto el 0 no tiene sentido: si se
quiere sin dither, la receta honesta es `--dither off`. Por eso el
+0,17 dB del primer bench no medía «E-17 mejora el dither» sino
«dither auto contra dither off».

**Costo real del dither completo:** 211.226 B sobre el clip sin dither
(1,23 % del archivo) y −0,17 dB de PSNR, para 392.508 celdas tramadas
(~0,54 B por celda tramada).

**Por qué NO se decide por número.** Las dos columnas de calidad del
bench —`psnr_rgb_db` y `err_oklab_medio`— son promedios de fidelidad
**por píxel**. El dither cambia exactitud por píxel a cambio de romper
las mesetas de color; por construcción esas dos métricas lo castigan y
**ninguna de las dos ve banding**, que es lo único que el dither compra.
El ranking monótono hacia «sin dither» es por lo tanto esperable y no
constituye evidencia de que la imagen se vea mejor. Con las métricas
registradas hoy el proyecto **no puede justificar el dither con una
fila de bench**: falta una columna que mida mesetas/banding.

**Decisiones:**

1. **E-17 queda opt-in** (`--dither-byte-budget`, default `None` =
   byte-idéntico). El producto sigue siendo `adef9e53…c05bb` con dither
   auto y sin presupuesto, reproducible desde `main` (regla 5).
2. **La elección dither on / 450 / off se eleva al operador** con los
   `preview.mp4` de las dos corridas nuevas, porque es una decisión
   visual y no la puede tomar el bench. Si elige «off», la receta es
   `--dither off` (no `budget 0`) y el fondo pasa a `74be25ef…a011f9`
   (17.168.633 B, 35,63 dB, −1,23 % de bytes y 1:29 menos de encode).
3. **Propuesta abierta:** agregar a `tools/bench_ref.py` una columna de
   proxy de banding, para que la regla «una mejora sin fila registrada
   no existe» pueda aplicarse también a lo que el dither mejora.

**E-18** (`b324446` + fix de fixture `a1fef56`, CI verde con 256
pruebas): el threshold corría después del dither y revertía celdas al
valor del frame anterior; sobre una celda tramada eso deshacía la
decisión del dither y rompía el patrón Bayer distinto en cada frame. El
revert ahora excluye las celdas que el dither movió, con contadores
`threshold_dither_protected_cells/_frames` reportados por encoder y
make_clip. No toca el producto: `--threshold` es 0 por default y el
perfil HQ nunca lo pasa. Test nuevo `tests/test_dither_threshold.py`
(3 pruebas), que se autocalibra barriendo umbrales en vez de fijar un
número mágico.

**Con E-17 y E-18 cerradas, F3 (E-12..E-18) queda completa.**

**Resolución del punto 2 (2026-08-29, decisión del operador):** comparó
los `preview.mp4` y eligió **off** — «SIN dither se ve igual que el con
dither para mí, así que nos quedamos con ese ahorrando porque la
diferencia es mínima». El fondo de producto pasa a `74be25ef…a011f9`
(17.168.633 B, 35,63 dB, Oklab 0,00721), instalado en `outputs/` con SHA
verificado; el default del input `dither` del workflow `encode` pasa a
`off` para que los defaults sigan siendo la receta de producto. Los
candidatos descartados se borran de `outputs/` (reproducibles desde el
workflow con dither=auto). La propuesta 3 (columna de proxy de banding)
sigue abierta.

## Instancia 024 - E-21: jerarquía de costo — mismo video, −54 % de encode, +0,012 % de bytes

**Fecha:** 2026-08-29 · **Commit:** `7e6fd8e` (CI verde run 33270790064,
282 pruebas Python — el conteo base previo era 271, no 266 como decía el
runbook — y 26 suites JS, con y sin Zopfli) · **Bench:** run 33270879728.

**Qué cambió.** Los tres puntos que decidían comprimiendo con
`best_deflate` por candidato (emisor v1 FULL/DELTA/DELTA_MASK,
predictores v2, e interna regional/predictor del transcodificador) ahora
eligen con **zlib-9 puro** (`trellis.finalist_deflate`, determinista con
o sin Zopfli — la elección ya no depende del entorno, regla 5) y pagan
`best_deflate` **una sola vez, sobre el ganador**
(`trellis.champion_deflate`). `trellis.proxy_cost` (entropía de orden 0)
queda listo como nivel de exploración para E-22/E-23. Sin Zopfli
instalado la salida es byte-idéntica a la histórica (probado por la pata
de CI sin zopfli, donde selección y campeón siempre fueron el mismo
compresor).

**Bench de producto** (768 graphic-hq, adaptive kmeans-oklab, tile 16,
`--palette-refit 5`, `--dither off`, zopfli, overlay=off):

```text
referencia (run 33231247505): | clip.asclv | 16985264 | 17168633 | 0.2216 | 231 | 93 | 9 | ZLIB:93;DELTA_MASK:137;RDELTA_RAW:1 | 35.63 | 0.00721 | 74be25ef6ebbcbc3ebf975bd10d348bb10badd8ec4e0800423f15f39c3a011f9 |
E-21       (run 33270879728): | clip.asclv | 16987304 | 17170673 | 0.2216 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:135;RDELTA_RAW:1 | 35.63 | 0.00721 | 41c9417008b57d53739db5f19cc36a19373f8dd8b84e1ba58862350cec1e79d5 |
```

- **PSNR y Oklab idénticos al centésimo/cienmilésimo**: E-21 no toca
  `cells`, solo la elección del contenedor; el video decodificado es el
  mismo.
- **Bytes +2.040 (+0,012 %)**: dos frames pasaron de DELTA_MASK a ZLIB
  (keyframes 93 → 95) porque en zlib-9 el candidato FULL les ganó,
  mientras que con la comparación Zopfli-por-candidato ganaba
  DELTA_MASK. Es el costo exacto de decidir sin Zopfli en el bucle.
- **Wall 44:21 → 20:18 (−54 %)**; RSS 693.644 → 678.832 kB.

**Decisión: adoptada.** Calidad idéntica, +2 KB sobre 17 MB, y el encode
a menos de la mitad; sobre todo, es el mecanismo que hace viables E-22 y
E-23 (explorar candidatos de trellis con Zopfli dentro del bucle era
inviable — el timeout de E-17 lo probó). El producto pasa a
`41c94170…79d5` (instalado en `outputs/` con SHA verificado). La
referencia `74be25ef…` queda como fila histórica: **ya no es
reproducible desde `main`** porque E-21 cambió el emisor — mismo motivo
por el que P-02 congeló su fila en su momento.

## Instancia 025 - E-22: trellis temporal — la curva presupuesto/bytes; presupuesto 2 sube PSNR y ahorra 16,6 %

**Fecha:** 2026-08-29 · **Commit:** `9ab95f6` (CI verde run 33272369191)
· **Benchs:** runs 33272440621 (presupuesto 4), 33272444235 (10),
33273449999 (2 + preview), 33273453829 (4 + preview).

**Qué es.** `--trellis-temporal N` (opt-in, default 0 = byte-idéntico,
verificado por test): para cada celda que difiere del frame anterior, el
índice PREVIO se considera segundo candidato y se emite si el error
EXTRA contra el pixel objetivo (misma métrica de E-20) no supera N — la
celda desaparece del DELTA. `extra` puede ser negativo: en los bordes de
Voronoi el índice previo está MÁS cerca del objetivo que el elegido, y
ahí la celda sale del DELTA **mejorando** la fidelidad. Corre en la
etapa trellis del orden canónico, después del threshold, y respeta la
protección del dither (E-18).

**Barrido sobre la receta de producto** (768 graphic-hq, adaptive
kmeans-oklab, tile 16, refit 5, dither off, zopfli; referencia = E-21):

```text
temporal 0 (run 33270879728): | clip.asclv | 16987304 | 17170673 | 0.2216 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:135;RDELTA_RAW:1 | 35.63 | 0.00721 | 41c9417008b57d53739db5f19cc36a19373f8dd8b84e1ba58862350cec1e79d5 |
temporal 2 (run 33273449999): | clip.asclv | 14132053 | 14315422 | 0.1844 | 231 | 39 | 9 | ZLIB:39;DELTA_MASK:190;RDELTA_RAW:2 | 35.75 | 0.00765 | 63fb7aaee60db9dc41b056cb0bf6986948230ffd66fb17bad46f50439176adde |
temporal 4 (run 33272440621): | clip.asclv | 12663096 | 12846465 | 0.1652 | 231 | 36 | 9 | ZLIB:36;DELTA_MASK:193;RDELTA_RAW:2 | 35.59 | 0.00809 | 221de28f1b6c5252be35368cdeeb736c15298c533956137438d59cdc11d80373 |
temporal 10 (run 33272444235): | clip.asclv | 10595152 | 10778521 | 0.1382 | 231 | 34 | 9 | ZLIB:34;DELTA:2;DELTA_MASK:193;RDELTA_RAW:2 | 34.81 | 0.00941 | 5db38f9d08af44582f9f12acb50b6bd891d3f5acb06771ffd9e0db92f26bf628 |
```

- **Presupuesto 2: −16,6 % de bytes y PSNR +0,12 dB** (9,2 M de celdas
  movidas, ~12 % por frame). La mejora de PSNR viene de las ganancias
  gratis (extra < 0); el Oklab medio sube +6,1 % porque las celdas
  congeladas retienen un color levemente viejo.
- Presupuesto 4: −25,2 %, PSNR −0,04 dB, Oklab +12 % (13,8 M celdas,
  ~21 % por frame). Presupuesto 10: −37,2 % pero −0,82 dB → descartado.
- Los keyframes elegidos caen 95 → 36-39: con los DELTA tan chicos, el
  emisor deja de preferir fulls; `cadena_delta_max` sigue en 9 (los
  bloques adaptativos acotan las cadenas).
- **Determinismo verificado** (regla 5): la re-corrida del presupuesto 4
  con preview reprodujo `221de28f…0373` byte a byte.
- Wall ~18 min (la jerarquía E-21 es la que hace barato este barrido:
  cuatro corridas costaron lo que antes una y media).

**Decisión: mecanismo cerrado; la adopción del presupuesto es del
operador, con los previews.** Igual que el banding con el dither, las
dos columnas de calidad son promedios por píxel y **no ven arrastre
temporal** (celdas que quedan pegadas al color del frame anterior); el
PSNR casi intacto sugiere que a presupuesto 2-4 el efecto es leve, pero
se confirma a ojo. `preview.mp4` de 2 y 4 enviados al operador;
`clip-temporal-2.asclv` y `clip-temporal-4.asclv` instalados en
`outputs/` con SHA verificado. Si adopta 2, el producto pasa a pesar el
**37 % del mp4 fuente**; si adopta 4, el **33 %**.

## Instancia 026 - E-23: trellis espacial — cruces de opcode medidos; −0,32 % en solitario

**Fecha:** 2026-08-29 · **Commit:** `626694a` (CI verde run 33274723247)
· **Benchs:** runs 33274781717 (presupuesto 8) y 33274785794 (16).

**Qué es.** `--trellis-spatial N` (opt-in, default 0 = byte-idéntico,
verificado por test): en tiles con exactamente 17, 5 o 3 valores
distintos, el valor más raro se fusiona con el valor del tile que
minimiza el peor error extra por celda (métrica E-20); el tile cruza a
un opcode más barato del regional v2 (PAL8→PAL4, PAL4→PACK2,
PACK2→PACK1). El cruce se fuerza en el ENCODER (etapa trellis, también
en keyframes); el transcodificador v2 sigue siendo lossless exacto.
Tiles con celdas tramadas se bloquean (E-18).

**Bench aislado sobre la receta de producto** (referencia = E-21):

```text
espacial 0 (run 33270879728): | clip.asclv | 16987304 | 17170673 | 0.2216 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:135;RDELTA_RAW:1 | 35.63 | 0.00721 | 41c9417008b57d53739db5f19cc36a19373f8dd8b84e1ba58862350cec1e79d5 |
espacial 8 (run 33274781717): | clip.asclv | 16931718 | 17115087 | 0.2209 | 231 | 96 | 9 | ZLIB:96;DELTA_MASK:134;RDELTA_RAW:1 | 35.62 | 0.00724 | 28edb2ad3b3c4669226171a68a8d6298b7a9d19bbbd52949ada1fc12613da6bb |
espacial 16 (run 33274785794): | clip.asclv | 16926685 | 17110054 | 0.2209 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:134;RDELTA_RAW:1;RDELTA_ZLIB:1 | 35.62 | 0.00724 | c84dfe9284a6e9991f5aee0bdf5fe736d2a518a86154146b0e195418b1cccbf2 |
```

- Presupuesto 8: 36.563 tiles fusionados (437.348 celdas en 231 frames)
  → **−55.586 B (−0,32 %) por −0,01 dB y +0,4 % Oklab**. Presupuesto 16
  apenas suma (−0,35 %): la curva satura — casi todos los tiles en
  cruce ya entran con 8.
- El efecto en solitario es chico porque las fusiones también ensucian
  el DELTA v1 (celdas que cambian respecto del frame anterior) y porque
  el candidato regional no gana en todos los frames. Su lugar natural
  es COMBINADO con el trellis temporal (E-22), que es exactamente lo
  que calibra E-24.

**Decisión: mecanismo cerrado, sin adopción en solitario** (−0,32 % no
justifica mover el producto por sí solo); queda como ingrediente de
`--near-lossless` (E-24). Nota para E-24: su criterio de cierre del
runbook pide comparar «error temporal y proxy de banding» contra el
baseline — ninguna de las dos columnas existe todavía en
`tools/bench_ref.py` (la de banding ya estaba propuesta desde la
Instancia 023), y la calibración también depende de la decisión visual
pendiente del operador sobre el presupuesto temporal.

**Resolución de la Instancia 025 (2026-08-29, decisión del operador):**
comparó los previews y eligió **presupuesto 2** — «realmente el primer
video se ve bien, no se ven arrastres casi, así que es una buena
aplicación porque no noto diferencia con el presupuesto anterior…
preferible por el ahorro conseguido». El fondo de producto pasa a
`63fb7aae…adde` (14.315.422 B, 35,75 dB, Oklab 0,00765 — **−16,6 % de
bytes y +0,12 dB de PSNR** sobre el producto E-21; **36,7 % del mp4
fuente**), instalado en `outputs/` con SHA verificado. El default del
input `extra` del workflow `encode` pasa a `--palette-refit 5
--trellis-temporal 2`: los defaults vuelven a ser la receta de producto
completa. El operador dejó abierta la puerta a «un presupuesto más
agresivo luego» — el 4 (−25,2 %, `221de28f…`) ya quedó medido con
preview y es exactamente el terreno que barre la calibración de E-24.

**Segunda resolución de la Instancia 025 (2026-08-29, mismo día):** el
operador vio también el preview del presupuesto 4 — «el más agresivo se
ve perfecto, yo no noto la diferencia» — y sostiene su criterio de que
sin diferencia visible gana el ahorro. **El producto pasa al presupuesto
4**: `221de28f…0373` (12.846.465 B, 35,59 dB, Oklab 0,00809 — −25,2 %
sobre el E-21 solo; **33,0 % del mp4 fuente**), instalado en `outputs/`
con SHA verificado; el default de `extra` del workflow pasa a
`--palette-refit 5 --trellis-temporal 4`. Pedido explícito del operador:
**probar presupuestos aún más agresivos «para comparar luego»** — el
barrido de calibración de E-24 debe incluir puntos entre 4 y 10 (p. ej.
5, 6 y 8; el 10 ya está descartado por −0,82 dB), medidos con las
columnas nuevas de error temporal y proxy de banding.

---

## Instancia 027 - E-24: columnas nuevas del bench + barrido near-lossless 4/5/6/8

**Fecha:** 2026-08-30 · **Commits:** `29ad7f8` (bench: `err_temporal` y
`proxy_banding`) y `271dd19` (perfil `--near-lossless`), CI verde
run 33320618751 · **Benchs:** runs 33321456189/463283/470296/477382/
484319/490398.

**Qué se mide ahora.** `tools/bench_ref.py` ganó las dos columnas que el
criterio de cierre de E-24 exigía (entre `err_oklab_medio` y `sha256`):

- `err_temporal`: magnitud Oklab media de (delta temporal decodificado −
  delta temporal de la fuente). El arrastre del trellis (celdas que se
  quedan en el valor viejo mientras la fuente se mueve) y el flicker
  aparecen acá; un corrimiento estático se cancela. Test de integración:
  una barra en movimiento congelada por el trellis dispara la columna
  mientras el encode exacto mide 0.
- `proxy_banding`: gradiente Oklab-L EXTRA del decodificado sobre zonas
  donde la fuente es suave (umbral 0,01 L por paso), medido tras
  promediar bloques 2×2: el tramado del dither se anula en el promedio y
  el contorno de un plateau sobrevive. A diferencia de
  `err_oklab_medio`, esta columna NO castiga al dither (test: rampa
  tramada Bayer mide menos de la mitad que la rampa cuantizada dura).

`--near-lossless N` (make_clip, resuelto en `trellis.py`): fija
`--trellis-temporal` y `--trellis-spatial` al MISMO presupuesto; 0 =
passthrough byte-idéntico; mezclarlo con los flags explícitos se
rechaza (regla 9).

**Barrido sobre la receta de producto** (768 graphic-hq, refit 5,
dither off; columnas nuevas 11 y 12):

```text
sin trellis  (run 33321456189): | clip.asclv | 16987304 | 17170673 | 0.2216 | 231 | 95 | 9 | ZLIB:95;DELTA_MASK:135;RDELTA_RAW:1 | 35.63 | 0.00721 | 0.00623 | 0.001034 | 41c9417008b57d53739db5f19cc36a19373f8dd8b84e1ba58862350cec1e79d5 |
temporal 4   (run 33321463283): | clip.asclv | 12663096 | 12846465 | 0.1652 | 231 | 36 | 9 | ZLIB:36;DELTA_MASK:193;RDELTA_RAW:2 | 35.59 | 0.00809 | 0.00652 | 0.001345 | 221de28f1b6c5252be35368cdeeb736c15298c533956137438d59cdc11d80373 |
near-loss 4  (run 33321470296): | clip.asclv | 12657520 | 12840889 | 0.1652 | 231 | 36 | 9 | ZLIB:36;DELTA_MASK:192;RDELTA_RAW:2;RDELTA_ZLIB:1 | 35.59 | 0.00810 | 0.00652 | 0.001340 | 5a45592b823d2c2b476b24eff897674849d0f34cc53a1b50cd38753b89f692d0 |
near-loss 5  (run 33321477382): | clip.asclv | 12156429 | 12339798 | 0.1586 | 231 | 36 | 9 | ZLIB:36;DELTA_MASK:193;RDELTA_RAW:2 | 35.48 | 0.00832 | 0.00664 | 0.001406 | 157bccf087903c64a9282832633f1682ccb65ab2d8a1d2866bda30fc20b04c44 |
near-loss 6  (run 33321484319): | clip.asclv | 11768438 | 11951807 | 0.1536 | 231 | 36 | 9 | ZLIB:36;DELTA_MASK:191;RDELTA_RAW:2;RDELTA_ZLIB:2 | 35.37 | 0.00853 | 0.00676 | 0.001465 | db32e8c435ecd53cabe4d04d7e22bdebe1023bb179478b912d2a913b81572157 |
near-loss 8  (run 33321490398): | clip.asclv | 11120768 | 11304137 | 0.1451 | 231 | 35 | 9 | ZLIB:35;DELTA:1;DELTA_MASK:192;RDELTA_RAW:3 | 35.10 | 0.00897 | 0.00705 | 0.001587 | b081f4bab92551569f0aba3d3644746acb643762a662624b0c41042245f6a05e |
```

**Lecturas.**

1. **Determinismo re-verificado (regla 5):** el baseline reprodujo
   `41c94170…79d5` y el producto `221de28f…0373` **byte a byte** con el
   emisor post-E-24 — el perfil con 0 no mueve nada.
2. **Las columnas ven lo que el PSNR no veía:** ambas suben monótonas
   con el presupuesto. Punto de referencia clave: el salto baseline →
   producto temporal 4 (+4,7 % de err_temporal, +30 % de
   proxy_banding) es exactamente el que el operador ya juzgó
   **invisible** en pantalla — ese incremento calibra qué significa
   «no se distingue» en estas unidades.
3. **El espacial no agrega nada a presupuesto 4:** near-lossless 4 vs
   temporal 4 = −5.576 B (−0,04 %) con métricas idénticas. Combinado
   con el temporal, casi todo lo que el espacial fusionaría ya salió
   del DELTA; el perfil solo rinde subiendo el presupuesto.
4. **La curva es suave, sin acantilado:** respecto del producto,
   near-lossless 5 = −3,9 % de bytes (+1,8 % err_temporal, +4,5 %
   banding); 6 = −7,0 % (+3,7 %, +8,9 %); 8 = −12,0 % (+8,1 %,
   +18 %, −0,49 dB). Los incrementos de 5 y 6 quedan muy por debajo
   del salto ya aprobado visualmente; el 8 se acerca a la mitad de ese
   salto y pierde medio dB.

**Estado: decisión visual del operador pendiente.** Previews en
`outputs/preview-e24-nl{5,6,8}.mp4` (el 4 no amerita video: es
métricamente el producto). Por números, 5 y 6 son candidatos firmes;
8 es el límite donde el bench empieza a distinguirse con claridad.

**Resolución de la Instancia 027 (2026-08-30, decisión del operador):**
comparó los tres previews — «los 3 se ven muy parecidos, el 3 se nota
que tiene una mínima pérdida de calidad pero es aceptable, así que
podríamos tomarlo» — y adoptó **near-lossless 8**, el más agresivo del
barrido. Es la primera vez que declara ver una diferencia y la acepta a
conciencia por el ahorro (antes su criterio era «sin diferencia
visible»). El fondo de producto pasa a `b081f4ba…f6a05e`
(11.304.137 B, 35,10 dB, Oklab 0,00897, err_temporal 0,00705,
proxy_banding 0,001587 — **−12,0 % sobre el temporal 4; el clip queda
en 29,0 % del mp4 fuente**), instalado en `outputs/` con SHA
verificado; los previews del barrido se borran de `outputs/`
(reproducibles desde los runs). El default de `extra` del workflow
`encode` pasa a `--palette-refit 5 --near-lossless 8` (defaults =
receta completa). **Con esta adopción E-24 queda cerrada y F5
(E-19..E-24) COMPLETA**: el carril trellis termina con el producto en
29,0 % de la fuente — un 34 % menos bytes que el baseline sin trellis
(17.170.673 → 11.304.137 B) por −0,53 dB (35,63 → 35,10), y aun así
+0,81 dB por encima del P-02 con el que arrancó el optimizador.

## Instancia 028 - S-7: barrido de resolución, primer escalón (1280) — ABIERTA

**Fecha:** 2026-08-30 · **Contexto:** F5 completa; arranca S-7 con la
receta de producto (graphic-hq, adaptive kmeans-oklab, dither off,
zopfli, tile 16, `--palette-refit 5 --near-lossless 8`) más `--cols
1280` en `extra` (el `--cols` manual pisa la resolución del perfil sin
tocar nada más, regla 9 ya cableada en `resolve_quality_options`).
Preparación: `timeout-minutes` de `encode.yml` 120 → **350** (tope del
runner 360; un 1920 estimaba ~5 h) — commit `2260d21`, CI verde.
A pedido del operador («pasa a 12 frames en vez de 15… tarda
significativamente menos mientras podemos ver los resultados visuales
igual») el escalón se midió también a **12 fps**, en paralelo.

Fuente mp4: 38.966.462 B. Filas de `bench_ref` (verbatim):

| archivo | bytes_ascl | bytes_asclv | B/celda/frame | frames | keyframes | cad | tags | psnr | oklab | err_temporal | proxy_banding | sha256 | run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 768@15 producto | 11.140.754 | 11.304.137 | 0.1451 | 231 | 36 | 9 | — | 35.10 | 0.00897 | 0.00705 | 0.001587 | `b081f4ba…f6a05e` | 33321490398 |
| 1280@15 | 24.347.091 | 24.530.460 | 0.1144 | 231 | 36 | 9 | ZLIB:36;DELTA:2;DELTA_MASK:191;RDELTA_RAW:1;RDELTA_ZLIB:1 | 35.02 | 0.00901 | 0.00713 | 0.001522 | `2a9201bf77a3ec0a6772e2131e5b9bc1db3e1f0dbdf3d01fae34038cb873b778` | 33325334610 |
| 1280@12 | 21.012.663 | 21.196.032 | 0.1232 | 185 | 32 | 9 | ZLIB:32;DELTA_MASK:153 | 34.95 | 0.00908 | 0.00766 | 0.001534 | `27ae0019ff0aab7f19ea4c3a56aef3f907fa1c6ad244716654236ad802fbe828` | 33326623591 |

**Lecturas:**

1. **La tasa por celda CAE 21 % al subir la resolución** (0,1451 →
   0,1144 B/celda/frame): con celdas más chicas los bordes son más
   suaves y los deltas comprimen mejor. Por eso la estimación previa
   (~31 MB = 79 % de la fuente) era pesimista: el 1280@15 real pesa
   **24.530.460 B = 63,0 %** de la fuente, con calidad por píxel casi
   idéntica al 768 (35,02 vs 35,10 dB; banding incluso mejor) sobre
   2,8× más celdas.
2. **12 fps compra −13,6 % de bytes y −25 % de wall** (41:23 → ~31 min)
   contra el mismo 1280@15. El costo no está en la imagen (PSNR y
   banding casi iguales) sino en el movimiento: menos frames = saltos
   más grandes por delta, y `err_temporal` lo ve (0,00713 → 0,00766).
   La tasa por celda sube (0,1144 → 0,1232) por el mismo motivo — el
   ahorro real es 13,6 %, no el 20 % lineal de frames.
3. Con la tasa real del 1280, el **1920 re-estima ~52 MB (1,3× la
   fuente) a 15 fps / ~45 MB a 12** — mejor que el ~69,5 MB previo pero
   aún sobre el mp4, salvo que la tasa vuelva a caer otro escalón.
4. Encode 1280: wall 41:23 y RSS 1,56 GB (@15) / ~31 min y 1,55 GB
   (@12) — entra holgado en el timeout nuevo y en el runner.

**Veredicto parcial del operador (2026-08-30, tras los previews):
«1280 quedó perfecto»**, y del 12 fps «casi ni se nota la diferencia de
frames» — pidió el **1920 a 10 fps solo para probar**. Despachado el
mismo día (receta de producto + `--cols 1920`, fps 10) → run
33333170964, success:

| archivo | bytes_ascl | bytes_asclv | B/celda/frame | frames | keyframes | cad | tags | psnr | oklab | err_temporal | proxy_banding | sha256 | run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1920@10 | 32.654.896 | 32.838.265 | 0.1023 | 154 | 28 | 9 | ZLIB:26;DELTA_MASK:126;RKEY_ZLIB:2 | 34.81 | 0.00929 | 0.00803 | 0.001553 | `87160987a4a9143ab41a68149c3556a76a0937c8c8d6ae4dfe83817a954e8d4e` | 33333170964 |

Lecturas del 1920@10: (a) **la tasa por celda cayó otro escalón**
(0,1144 → 0,1023 B/celda/frame) *a pesar* de los 10 fps que la empujan
hacia arriba — el efecto resolución sigue mandando; por eso pesó
**32.838.265 B = 84,3 %** de la fuente y no los ~40-45 MB estimados.
(b) El costo de los 10 fps está donde se esperaba: `err_temporal`
0,00803 (vs 0,00766 @12 y 0,00713 @15), PSNR −0,14 dB vs el 1280@12.
(c) Wall 1:02:07 y RSS 3,35 GB — holgado en el timeout 350 y en el
runner de 7 GB. Preview enviado al operador (artifact 9739091295;
clip en 9739090827, 14 días).

**Estado: ABIERTA — falta el veredicto visual del 1920@10 y las
definiciones finales de S-7** (qué resolución/fps queda como producto,
si alguna). El 1280 ya tiene aprobación visual del operador; nada
instalado en `outputs/` ni cambiado en los defaults del workflow.
En paralelo, a pedido del operador, el player real con los clips
768/1280-15/1280-12 quedó empaquetado en `outputs/deploy-player/`
(gitignored) para hostearlo en Cloudflare (dominio iargen.com) desde
una sesión nueva con su conector — los preview.mp4 validan calidad
(decodificación exacta) pero no el pipeline de reproducción JS.

## Instancia 028 — CIERRE (2026-08-31): S-7 definida por el operador

**Veredicto del 1920@10:** «lo revisé, se ve espectacular, está aprobado».
Con esto los tres escalones del barrido tienen aprobación visual
(1280@15 «quedó perfecto» · 1280@12 «casi ni se nota» · 1920@10
«espectacular»).

**Definición de producto (decisión del operador, regla 9):** el producto
de ASCILINE pasa de 768 a **1280 @15 fps** — `2a9201bf…b778`,
24.530.460 B = 63,0 % de la fuente, 35,02 dB (fila verbatim arriba).
Motivo de no elegir el 1920: «a 10 fps el 1920 se pone un poco trabado»
— el límite es la FLUIDEZ a 10 fps, no la imagen (que aprobó como
espectacular). Receta: los defaults del workflow `encode` + `--cols
1280` en `extra`. Las demás resoluciones (768, 1280@12, 1920@10) quedan
como **variantes disponibles en el player** (ya hosteadas en
iargen.com/player/).

**Directiva del operador para el frontend:** «después haremos una prueba
con 1920, así que el front debe poder procesar cualquier cosa que le
tiremos» — el player no asume la resolución del producto: cualquier
cols/rows/fps dentro de los límites operativos del reader (hoy 1920×1080
= 2,07 M de celdas entra holgado en el tope de 64 MiB y ya reproduce en
navegador) debe seguir siendo un input válido. El 1920 (a más fps que
10) entra en la matriz de F8-2 como prueba futura.

**Ejecución diferida a S-4 a propósito:** el re-encode del producto
1280@15 se hace UNA sola vez, con el formato v3 y el tile ganador del
barrido definitivo de F6-2 (en medición al momento del cierre), para no
gastar un runner en un artefacto v2 que quedaría viejo en horas. Hasta
ese encode, el artefacto instalado en `outputs/` sigue siendo el 768
`b081f4ba…` (v2). **S-7 CERRADA.**

## Instancia 029 — F6-2: barrido 2D de tile, ganador global y adopción de v3 (2026-08-31)

**Contexto.** El "barrido de tile" resultó tener dos ejes independientes:
la geometría del trellis ESPACIAL E-23 (lossy, vive en el encoder y está
acoplada a `--tile-size`) y el `tile_size` del codec regional v2
(lossless, vive en el transcoder y es lo único que `--tile-sweep`
barre). El run acoplado-32 de la sesión anterior no reprodujo el SHA del
sweep y eso destapó la matriz completa; se despacharon los dos runs que
cierran las diagonales. Todos sobre el 768 receta de producto, formato
v3, con `bench_ref` ya arreglado para v3 (`294c324`).

**Filas (verbatim de bench_ref, workflow `encode`):**

Run A 33350852865 — espacial 16 + sweep regional (ganó regional 32):

| clip.asclv | 11078613 | 11261986 | 0.1446 | 231 | 35 | 9 | ZLIB:8;DELTA_MASK:173;RKEY_ZLIB:27;RDELTA_RAW:3;RDELTA_ZLIB:20 | 35.10 | 0.00897 | 0.00705 | 0.001587 | 6f28a4597bdef682e80951f7454a15d14976e3cc6336092642adc4b07ed83784 |

Run B 33350856477 — espacial 32 (`--tile-size 32` en extra) + sweep regional:

| clip.asclv | 11092989 | 11276362 | 0.1447 | 231 | 35 | 9 | ZLIB:10;DELTA_MASK:172;RKEY_ZLIB:25;RDELTA_RAW:3;RDELTA_ZLIB:21 | 35.10 | 0.00896 | 0.00704 | 0.001593 | 8b5d0f1eddcab317d0223affa05a4912eb49c8c24c8731ece76c03e89132e738 |

**Lecturas.**

- **Regla 5, dos veces:** el run A reprodujo byte a byte el
  `6f28a459…8784` del sweep original (33347720448) y el run B reprodujo
  el `8b5d0f1e…` del acoplado-32 (33349725014). El pipeline v3 completo
  (SPARSE diferencial + envelope + sweep) es determinista entre runners.
- **Ganador global: espacial 16 + regional 32.** Bundle 11.261.986 B =
  **−0,37 %** vs el producto 768 v2 (11.304.137 B) con calidad idéntica
  (35,10 dB y las tres métricas de error iguales al producto). La
  diagonal espacial-32 es peor (+14.376 B): con tiles espaciales de 32
  el trellis fusiona 1.750 regiones contra 15.109 a 16 — el eje espacial
  ya estaba en su óptimo.
- El SPARSE diferencial de F6-1 aporta ~95 B a tile regional 16 en este
  artefacto; el ahorro real de v3 en bytes viene de habilitar el tile
  regional 32. El valor estructural (meta embebida, gate por versión)
  viene gratis.

**Decisión (cierra F6-2 y decide la adopción):** el producto adopta
**v3 con espacial 16 + regional 32**. La configuración mixta se pinnea
usando `tile=sweep` en el workflow — la elección del sweep es
determinista (regla 5 verificada) y evita agregar un flag nuevo que
decouple los ejes; si algún día el sweep eligiera otro tile por un
cambio de estadística, eso es exactamente lo que el barrido debe hacer.

**Acto de cierre de S-4 despachado en el momento:** run 33352859235 =
encode único del producto **1280@15 (S-7) en v3**, inputs `format=v3` +
`tile=sweep` + extra `--palette-refit 5 --near-lossless 8 --cols 1280`.
Con su fila: instalación en `outputs/` (clip versionado + puntero
CACHE-001) y publicación al player. Instancia ABIERTA hasta esa fila.

### Instancia 029 — CIERRE (2026-08-31): el producto 1280@15 v3 en producción

**Fila del encode de cierre (run 33352859235, verbatim de bench_ref):**

| clip.asclv | 24275511 | 24458884 | 0.1140 | 231 | 36 | 9 | ZLIB:9;DELTA:1;DELTA_MASK:153;RKEY_ZLIB:27;RDELTA_RAW:1;RDELTA_ZLIB:40 | 35.02 | 0.00901 | 0.00713 | 0.001522 | dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a |

Wall 59:54, RSS máx 1,6 GB. Del log: «barrido tile_size: 4:24347063 …
32:24275511 → ganador 32; trellis espacial: presupuesto 8, tile 16,
58.456 tiles fusionados (577.581 celdas) en 227 frames».

**Lecturas.**

- El sweep a 1280 eligió el MISMO punto que a 768 (regional 32 +
  espacial 16): la receta pinneada con `tile=sweep` es estable entre
  resoluciones.
- **v3 vs v2 en el producto real:** 24.458.884 B contra los 24.530.460 B
  del `2a9201bf…` (v2 tile 16) = **−71.576 B (−0,29 %)** con la MISMA
  calidad visual-métrica (35,02 dB; las diferencias en err_temporal y
  proxy_banding vienen del trellis con tiles regionales 32, mismas
  magnitudes). El producto queda en **62,8 % del mp4 fuente**.
- Instalación y publicación en el mismo acto: `outputs/` local (SHA
  verificado, copia versionada byte-idéntica + puntero) y player de
  producción — la raíz de iargen.com/player/ sirve ahora el producto por
  la vía CACHE-001 (puntero → `clip.dcd6afb66907.asclv` immutable;
  fallback `clip.asclv` actualizado a los mismos bytes). Token rotado y
  quemado, nada persistido.
- **Verificación de reproducción real (primer v3 en producción):** badge
  `ASCL v3 1280x720 @15fps`, frames avanzando, logo INT-007 girando; los
  404 de `data.txt` son el poll del datachannel (tolerado, INV-7).

**Decisión: S-4 CERRADA y v3 ADOPTADO como formato de producto.** El
criterio de la fase se cumplió: UNA sola versión nueva de decoder
desplegada con todos los cambios adentro (SPARSE diferencial, envelope
con meta embebida, tile regional 32, CACHE-001). Los subplayers
conservan los clips v2 como variantes comparables. Sigue F8 (TV físico);
queda en el operador probar celular/Smart TV.

**Veredicto visual del operador (2026-08-31, post-publicación):** comparó
la raíz (producto 1280@15 **v3** `dcd6afb6…`) contra `/player/1280-15/`
(el mismo contenido en **v2** `2a9201bf…`): «perfecto, se ve igual —
pasá la mejora». La adopción de v3 —hecha por métricas al cierre de
S-4— queda además CONFIRMADA A OJO: el cambio de formato es invisible,
como debía (v3 no toca la imagen decidida por el encoder, solo la
representación en bytes). Instancia 029 cerrada del todo.

## Instancia 030 - Auditoria de mejoras y plan nuevo (F9, F10, F11, DIAG-001)

**Pedido del operador (2026-08-31):** «se llego a un punto de dificil
avance en cuanto a mejoras... revisa las mejoras que ya se aplicaron
para no repetir y dame una bateria de nuevas optimizaciones... nos
interesa sobre todo como trabajar con resoluciones grandes como 1920
estresando menos el front pero manteniendo o mejorando la calidad de
reproduccion». Sumo un sintoma concreto: «los escalados de sombras... el
huevo de telekino en algun punto se ve con escalones en vez de pasar la
escala mejor».

### Auditoria previa (para no re-proponer lo descartado)

Se releyeron el encoder completo (15 modulos), el frontend completo (16
archivos + suites JS) y todo el historial de decisiones (Instancias
001-029 + `ejecutados/`). Las propuestas se filtraron contra la lista de
lo ya probado: quedan **fuera** por evidencia previa el dither global
(rechazado por el operador el 2026-08-29: 211.226 B y -0,17 dB sin
banding visible), el refine uint8 (E-13, +0,36 % bytes), el dither
exacto (E-16, +6,0 % bytes), los barridos de tile (F6-2: espacial 16 +
regional 32 es estable entre 768 y 1280), el remap de IDs (-0,96 %,
rechazado sin CPU fisica medida), el 960 (superado por el 768 con refit
5) y la compensacion de movimiento (vetada por invariante).

### Diagnostico del escalonado del huevo (tres causas, no una)

1. **Escalado de pantalla.** El backing store queda en tamaño de grilla
   y `fitCanvas()` estira por CSS con factor **fraccionario** (1280 en un
   panel de 1920 = x1,5). El producto sale con `--reconstruction nearest`
   (default de `make_clip.py`, el workflow no lo cambia), asi que el
   compositor duplica una de cada dos columnas. Sobre siluetas curvas y
   degradés eso agrega escalones que NO estan en el archivo.
2. **Banding de paleta.** 256 colores para todo el frame, y el
   `--near-lossless 8` adoptado en la Instancia 027 es un alias de
   `--trellis-temporal 8 --trellis-spatial 8`: el trellis espacial fusiona
   el valor MENOS FRECUENTE de cada tile que cruza los umbrales (3, 5,
   17), que en una rampa de sombra es exactamente el escalon intermedio.
   Medido en su momento: **+18 % de proxy_banding** (0,001345 ->
   0,001587) por -12 % de bytes.
3. **Animacion.** Trellis temporal (congela celdas casi iguales) +
   remuestreo sample-and-hold puro, sin blending: un zoom lento se ve
   por saltos.

**Procedimiento de desambiguacion anotado (DIAG-001):** decodificar el
`.asclv` vigente a resolucion nativa y comparar contra el player a
pantalla completa. Limpio en el MP4 y escalonado en el player -> causa 1;
escalonado ya en el MP4 -> causa 2; solo al moverse -> causa 3.
**El operador decidio verlo AL FINAL** («el escalado del huevo sera lo
ultimo que veremos»), despues de F9-F11.

### Hallazgo central para el 1920

El trabajo por frame del TV es proporcional a las **celdas**, no a los
pixeles de pantalla, y hoy se paga entero en CPU: `fillRGBARows` hace
~7 accesos a arrays y 2 multiplicaciones por celda, y recien despues se
sube el RGBA.

| Grilla | Celdas | Accesos por frame completo | RGBA a subir |
|---|---|---|---|
| 768x432 | 331.776 | ~2,3 M | 1,3 MB |
| 1280x720 | 921.600 | ~6,5 M | 3,7 MB |
| 1920x1080 | 2.073.600 | **~14,5 M** | **8,3 MB** |

Un keyframe a 1920 hace ese trabajo completo, y en el 1920@10 medido en
S-7 hay 28 keyframes en 154 frames (uno cada ~5,5). Es la hipotesis
principal de por que el operador vio el 1920 «un poco trabado» pese a
aprobar su imagen («se ve espectacular»): el costo no estaba solo en los
10 fps.

### Decisiones del operador sobre la bateria propuesta

- **Textura de indices + paleta en el shader: «debemos probarlo cuanto
  antes».** -> F9/W-18, primera prioridad tecnica.
- **Reconstruccion:** «se reproducira en televisores con resolucion 1920
  asi que aunque sea 1280 debera estirarse a 1920... se puede revisar a
  ver si es cierto que termina costando menos, pero seria algo para que
  veamos **por cada video** que trabajemos, **nunca algo fijo**...
  siempre las resoluciones deben poder ser elegibles al igual que los
  frames». -> W-19 implementa el filtro; la eleccion 1280-reconstruido vs
  1920-nativo se decide por clip. **Principio anotado como extension de
  la regla 9.**
- **Perdida adaptativa por suavidad: «brillante, seria algo realmente
  bueno para el degradado del huevo».** -> F10.
- **LOD por tile: «realmente brillante, hay que aplicarlo tambien».** ->
  F11-1 (+ E-30 como paso previo sin cambio de formato).
- **Feature nueva pedida por el operador — transparencia:** «este formato
  es perfecto para fondos transparentes... si yo te paso por ejemplo solo
  el personaje del huevo de telekino y saco el resto del video, poder
  hacer un clip con el resto transparente». -> F11-2 (ALPHA-001).

### Plan resultante

**Orden: F9 -> F10 -> F11 -> F8 -> DIAG-001.** F9 primero porque no toca
bytes ni formato y se valida contra el clip ya publicado: su ciclo de
prueba dura minutos en vez de una hora de runner.

- **F9 (S-8) - frontend:** W-16 medicion (banco Node + diagnostic-player,
  que es F8-1 adelantada), W-17 LUT `Uint32`, W-18 textura de indices con
  lookup en el shader, W-19 reconstruccion de 4 taps (acoplada a W-18:
  interpolar indices produce colores arbitrarios, asi que `LINEAR` sobre
  la textura de indices queda prohibido), W-20 cadencia y pre-decode del
  keyframe, W-21 dirty en X (opcional).
- **F10 (S-9) - encoder, sin cambio de formato:** E-25 expone
  `--gradient-boost` (hoy fijo en 3.0) y reutiliza el mapa de suavidad;
  E-27 impide que el trellis espacial fusione dentro de una rampa; E-26
  modula el presupuesto por celda; E-28 dither dirigido solo a mesetas,
  aceptado por `proxy_banding` (la metrica que no existia cuando se
  rechazo el dither global); E-29 costo de decodificacion en la eleccion
  de tag (opcional).
- **F11 (S-10) - formato v4:** E-30 hornea el LOD en la matriz **antes**
  del trellis (el codec sigue siendo lossless: se preserva el contrato C2
  y el beneficio de bytes se puede medir SIN cambiar el formato), F11-1
  agrega el opcode `0x08 LOD2`, F11-2 la transparencia via `cell_fmt = 4`
  (paleta RGBA) con `version = 4` — los decoders anteriores la **rechazan**
  por ambos campos en vez de mostrar basura, porque el reader actual ya
  falla con `cell_fmt !== 3` —, F11-3 el espejo JS con cross-test y
  fuzzing, F11-4 el barrido y la adopcion.

Diseños completos en `DISENO-RENDER-INDEXADO.md`,
`DISENO-PERDIDA-ADAPTATIVA.md` y `DISENO-FORMATO-V4-LOD-Y-ALPHA.md`.

**Estado: plan documentado, ejecucion pendiente.** Ninguna medicion nueva
todavia: las cifras de esta entrada son del codigo leido y de las filas ya
registradas, no de runs nuevos. La primera tarea que produce numeros es
W-16.

---

## Instancia 031 - 2026-08-31 - Revision del plan, pregunta de los 512 colores y dos ideas nuevas anotadas para v4

El operador pidio (a) el parecer sobre los tres disenos de la Instancia 030 y
(b) una idea mas de gran rendimiento alineada con no ensuciar el front en
dispositivos viejos. De la conversacion salieron dos ideas anotadas, un
descarte razonado y tres ajustes de detalle que se cablearon en los disenos.

### Parecer sobre el plan (resumen; el detalle quedo en los disenos)

El plan se sostiene. Cuatro puntos a vigilar detectados en la revision, todos
cableados en los documentos en esta misma instancia:

1. **Interaccion F10-F11 que no estaba escrita:** los tiles de bajo detalle
   (candidatos a LOD en E-30) son exactamente donde vive el banding; promediar
   2x2 y recuantizar dentro de un degrade puede reintroducir los escalones que
   F10 saca. La seleccion de E-30 ahora exige el mapa de suavidad de E-25 para
   distinguir "plano" (LOD si) de "rampa suave" (LOD no).
2. **Linea base de E-26:** medir contra el producto vigente le atribuiria
   merito doble (E-27 va antes y ataca la misma causa). Ahora E-26 se mide
   contra el producto post-E-27.
3. **Alcance de W-20:** pre-decode **solo de keyframes** (no dependen del
   estado actual, seguros por construccion). Adelantar deltas exigiria una
   base definida sin comprometer el invariante 4 y se disenaria aparte.
4. **Expectativa de W-18:** los TVs mas viejos son los mas propensos a caer al
   fallback; el valor de F9 descansa en que W-17 y W-20 mejoran el piso
   Canvas2D en TODOS los dispositivos. "W-18 acelera donde puede; W-17
   acelera en todos."

### Pregunta del operador: paleta de 512 en vez de 256?

Respuesta: encarece archivo y reproduccion por una razon estructural, no de
ajuste. Todo el formato descansa en que el indice entra en 1 byte: 512 colores
exige 2 bytes por celda (plano crudo x2; comprimido, +30-70 % estimado) o
empaquetado a 9 bits (rompe el decode trivial byte-alineado); todos los
opcodes del regional v2 estan definidos sobre valores de 1 byte; la subida por
keyframe a 1920 pasaria de 2,07 MB (post-W-18) a 4,1 MB. Ademas los 256 son
POR FRAME/BLOQUE, no por video, y lo medido atribuye el escalonado del huevo
al trellis espacial (+18 % proxy_banding, fila del REGISTRO) y al estirado
fraccionario, no a saturacion de paleta. Verificacion barata pendiente: la
corrida de E-25 con --gradient-boost alto responde si la rampa satura las 256.
**El operador evaluo y no siguio por 512; propuso en cambio la idea (b).**

### Idea (a) - frames de solo-paleta (propuesta en esta instancia)

Fundidos/flashes son hoy el peor caso simultaneo de bytes y trabajo del front
(todas las celdas cambian, o el detector de cortes dispara keyframe tras
keyframe; los 28 keyframes en 154 frames del 1920 de S-7 son sospechosos).
Pero un fundido cambia la PALETA, no la estructura: el encoder puede detectar
frame N ~ transformada global en Oklab del N-1 (ajuste numerico, sin IA) y
emitir celdas todas SKIP + paleta transformada: ~800 B por frame y un rebuild
de LUT de 256 entradas en el TV, contra cientos de KB y subida completa.
Requiere levantar de forma acotada la regla "los tags delta no pueden emitir
paleta" -> cambio de formato, viaja en v4. Des-riesgo igual que E-30:
**E-31** (analisis offline de candidatos y techo de ahorro, sin formato,
Δbytes no) es el gate de **F11-5** (permiso de paleta en delta o tag
PALETTE_ONLY, condicionada a E-31 + aprobacion del operador). Detalle en
`DISENO-FORMATO-V4-LOD-Y-ALPHA.md` §11.

### Idea (b) - paletas por region (idea del operador, anotada sin tarea)

Mantener 256 pero multiplicar donde hace falta: N paletas de 256 con selector
de 1 byte por tile (version espacial del modo `block` temporal). El indice
sigue pesando 1 byte por celda; la asignacion es clustering numerico por
similitud de color (sin segmentacion, veto respetado); histeresis para que un
tile no alterne de paleta. Punto clave del operador, generalizado: los tiles
se PARTICIONAN entre grupos, nunca se superponen — cuando una region rica en
colores se separa con su propia paleta, el grupo base no codifica nada debajo
(queda un hueco) y sus 256 entradas quedan enteras para el resto. Sin capas ni
doble decode: una matriz, un canvas, invariante 2 intacto. Gate para
promoverla a tarea: que E-25 muestre saturacion real de las 256. Detalle en
`DISENO-FORMATO-V4-LOD-Y-ALPHA.md` §10.

### Estado

Documentacion sincronizada en esta instancia: disenos (F9 §4/§6, F10 §3/§4,
v4 §3/§9/§10/§11), runbook de implementacion (filas E-31/F11-5 + ajustes
E-26/E-30/W-20 + nota de idea anotada), runbook de estado (proxima accion,
tabla de tareas abiertas, bitacora) y CLAUDE.md. **Ninguna medicion nueva;
el plan de ejecucion no cambia: arranca W-16.**

---

## Instancia 032 - 2026-08-31 - W-16 CERRADA: banco de conversion indice->RGBA y player de diagnostico

Primera tarea de F9 (S-8) y precondicion dura del resto de la fase: ninguna
mejora del frontend se puede cerrar sin medicion registrada (reglas 5 y 6).
Commit `f1ccfa3`, regresion en verde (3 patas de la matriz).

### Que se construyo

- **`tools/bench_render.js`** - banco Node de la etapa que el front paga por
  frame DESPUES de decodificar: pasar de un indice por celda a RGBA. Corpus
  determinista de tres grillas (768x432, 1280x720, 1920x1080) por tres perfiles
  (keyframe completo, delta disperso ~5 % de celdas, delta de tiles densos)
  sobre un clip ASCL v2 sintetico con paleta de 256 y tiles de 16. Dos
  variantes por caso: el camino de bytes vigente del reader y el prototipo LUT
  `Uint32` de W-17.
- **`frontend/diagnostic-player.html`** - ES5, sin dependencias nuevas. Es la
  tarea **F8-1 adelantada**. Mide por frame inflate, walk, conversion RGBA,
  blit/upload y el resto del seek, con p50/p95, drops y frames tarde contra el
  presupuesto que sale de los fps del clip (no de una constante).
- **`tests/test_bench_render.js`** y **`tests/test_diagnostic_player_page.js`**
  cableados en `tests/run_all.py` en el mismo commit (regla 7), mas el workflow
  manual **`bench-render`** para la corrida larga y la comparacion HEAD vs
  baseline.

### Tres decisiones de diseno que conviene no re-discutir

1. **El CI publica la tabla, no la juzga.** El runner comparte CPU: una
   asercion de velocidad seria un test intermitente. Lo que si es criterio duro
   es la **paridad** byte a byte entre el camino vigente, el prototipo LUT y la
   reconstruccion completa; si alguna difiere, el banco lanza y el CI falla.
2. **La instrumentacion vive entera en la pagina de diagnostico**, envolviendo
   metodos de la instancia del reader. Ningun archivo de produccion se modifica
   para medir, asi que lo medido es exactamente lo que corre en el TV.
   Detalle que costo un bug y quedo fijado en test: `fillRGBA` delega en
   `fillRGBARows`, las dos envueltas, y sin guarda de reentrada la conversion
   se contaba dos veces (y el blit quedaba en cero).
3. **El clip del banco es v2 a proposito.** La etapa medida es identica en v2 y
   v3: el SPARSE diferencial de v3 cambia el walk, no la conversion.

### Medicion (CI, ubuntu-latest, Node 20, 4 repeticiones)

| grilla | perfil | celdas | bytes ms | lut32 ms | x |
|---|---|---|---|---|---|
| 768x432 | key | 331.776 | 1,515 | 0,829 | **1,83** |
| 768x432 | sparse | 16.848 | 0,313 | 0,237 | 1,32 |
| 768x432 | tiles | 165.888 | 1,465 | 0,447 | **3,28** |
| 1280x720 | key | 921.600 | 4,978 | 2,152 | **2,31** |
| 1280x720 | sparse | 46.800 | 0,901 | 0,411 | 2,19 |
| 1280x720 | tiles | 460.800 | 2,467 | 1,244 | 1,98 |
| 1920x1080 | key | 2.073.600 | 11,047 | 4,922 | **2,24** |
| 1920x1080 | sparse | 105.240 | 1,166 | 0,772 | 1,51 |
| 1920x1080 | tiles | 1.036.800 | 5,559 | 2,829 | 1,96 |

Paridad OK en los 9 casos.

### Lectura

- El diagnostico de F9 se confirma con numeros: **el keyframe a 1920 cuesta 11
  ms de pura conversion en un runner de CI**, sin contar inflate, walk ni
  subida. Un TV viejo esta un orden de magnitud por debajo de esa CPU, asi que
  esos 11 ms son el techo que se lleva puesto el presupuesto de frame.
- **W-17 queda justificada antes de escribirla**: entre 1,3x y 3,3x segun el
  perfil, ~2,2x en los dos casos que dominan el costo real (keyframe y tiles
  densos). El prototipo del banco ya esta verificado byte a byte, asi que W-17
  es llevarlo al reader con su fallback byte a byte, no inventarlo.
- El perfil disperso gana menos (1,3-1,5x) y la razon es estructural, no de la
  LUT: `fillRGBAChanged` recorre TODO `dirtyCellBits` (n/8 bytes) aunque cambie
  el 5 % de las celdas. Es el hueco que ataca **W-21** (dirty en X) y conviene
  recordarlo cuando se decida si sigue siendo opcional.
- Los MB/s del camino de bytes se mantienen ~700-830 MB/s en las tres grillas:
  la etapa escala lineal con las celdas, sin sorpresas de cache. La LUT sube a
  ~1.400-1.600 MB/s, tambien plano.

### Estado

W-16 cerrada. Sigue **W-17** (LUT `Uint32` en `reader.js` y `reader-v2.js`),
que se cierra con salida byte-identica sobre el corpus mas la fila de
`bench-render` comparando el reader nuevo contra `f1ccfa3` como baseline.

---

## Instancia 033 - 2026-08-31 - W-17 CERRADA: LUT de paleta en Uint32 (hasta 2,2x en la conversion)

Commit `8cecc7b`, regresion en verde. Segunda tarea de F9, medida con el banco
que dejo W-16.

### Que cambio

La conversion indice->RGBA pasa de **3 lecturas de paleta + 4 escrituras de
byte** por celda a **1 lectura de LUT + 1 escritura de palabra**, en
`frontend/reader-v2.js` (modo PIXEL) y `frontend/reader.js` (PIXEL y PAL). Los
modos RGB y ASCII de v1 no se tocan.

Tres propiedades del diseno, todas exigidas por el contrato legacy:

1. **La endianness se detecta, no se asume.** Una vez por modulo: se escribe un
   valor conocido en un `Uint32Array` y se lee por su vista de bytes.
2. **La LUT se construye por PALETA, no por frame.** Las paletas son subvistas
   inmutables del archivo y solo se reemplazan por asignacion, asi que la
   identidad del objeto alcanza como clave de cache. En un clip de paleta
   global se construye una sola vez en toda la reproduccion; con paleta por
   frame son 256 empaquetados contra ~1 M de celdas, despreciable.
3. **El fallback de bytes no es opcional.** Si el destino no admite una vista
   `Uint32` -Array plano, buffer desalineado, motor sin `Uint32Array`- se
   conserva el camino viejo intacto. El destino ES el selector, y por eso el
   test de paridad puede correr los dos caminos sobre el mismo reader y el
   mismo frame (`tests/test_reader_palette_lut.js`): keyframe, delta de celdas
   exactas, delta de tiles densos, y las variantes alineada y desalineada.

Detalle que quedo fijado: las entradas de la LUT por encima de la paleta se
llenan con negro opaco, que es exactamente lo que escribia el camino de bytes
leyendo fuera de rango. Un indice invalido no llega ahi (lo rechaza la pasada
de validacion), pero la salida no cambia de significado por las dudas.

### Medicion: HEAD vs baseline en la MISMA corrida

Workflow `bench-render`, 40 repeticiones, baseline `f1ccfa3` (el commit de
W-16, es decir el reader anterior). Comparar dentro de una sola corrida evita
el ruido de comparar runners distintos.

| grilla | perfil | baseline ms | W-17 ms | mejora |
|---|---|---|---|---|
| 768x432 | key | 1,631 | 0,740 | **2,20x** |
| 768x432 | sparse | 0,228 | 0,202 | 1,13x |
| 768x432 | tiles | 0,976 | 0,574 | 1,70x |
| 1280x720 | key | 5,138 | 3,254 | 1,58x |
| 1280x720 | sparse | 0,564 | 0,455 | 1,24x |
| 1280x720 | tiles | 2,772 | 2,028 | 1,37x |
| 1920x1080 | key | 11,429 | 5,728 | **2,00x** |
| 1920x1080 | sparse | 1,136 | 0,854 | 1,33x |
| 1920x1080 | tiles | 6,225 | 3,265 | **1,91x** |

Honestidad sobre el ruido: dentro del bloque HEAD las filas `reader` y `lut32`
son ya el mismo algoritmo, y aun asi difieren hasta un 1,5x entre si en algun
caso (1280 key: 3,254 contra 2,184). Eso da la escala del ruido del runner y
dice que las mejoras de ~1,2x no son concluyentes; las de ~2x si. La corrida de
la regresion del mismo commit, con menos repeticiones, midio 1920 key en 4,872
ms, coherente con el mismo orden.

### Lectura

- **El keyframe a 1920 baja de 11,4 a 5,7 ms**, y los tiles densos de 6,2 a
  3,3. Es la mitad del costo de la etapa mas cara del frame, sin tocar un solo
  byte del formato ni la imagen: la salida es identica byte a byte.
- **El perfil disperso gana poco (1,1-1,3x) y no es culpa de la LUT**:
  `fillRGBAChanged` recorre TODO `dirtyCellBits` (n/8 bytes) aunque cambie el
  5 % de las celdas, asi que el costo dominante es el barrido del bitset, no la
  escritura. Es el argumento para dejar de tratar a **W-21** como opcional.
- La fila `bytes` del banco se renombro a `reader`: desde W-17 ya no describe un
  camino fijo, y su convergencia con `lut32` es justamente la evidencia de que
  la LUT entro al reader. La comparacion contra el pasado se hace con
  `bench-render` y un baseline, no con una fila fija.

### Estado

W-17 cerrada. Siguen **W-18 y W-19 juntas** (textura de indices + paleta en el
shader, y reconstruccion de 4 taps): la textura de indices rompe el modo `soft`
actual si la reconstruccion no la acompana. El player desplegado en
`iargen.com/player/` todavia corre el frontend anterior; la publicacion del
frontend acelerado se hace al cerrar F9, no por tarea.

---

## Instancia 034 - 2026-08-31 - W-18 + W-19: textura de indices, paleta en el shader y reconstruccion de 4 taps

Commit `07a94e2`, regresion en verde. Van juntas porque la textura de indices
rompe el modo `soft` anterior si la reconstruccion no la acompana.

### W-18: la GPU deja de recibir RGBA

En modo PIXEL la textura que se sube son los INDICES tal cual (LUMINANCE, 1
byte por celda) y la paleta viaja como textura 256x1 RGBA; el lookup lo hace el
fragment shader.

| | antes | ahora |
|---|---|---|
| conversion en CPU | `fillRGBA*` sobre las celdas sucias | **ninguna** |
| subida por frame completo a 1920 | 8,3 MB | **2,07 MB** |
| buffer RGBA residente | 8,3 MB | **no se reserva** |

Los tres detalles que deciden si esto anda o falla en silencio quedaron
cubiertos y con test:

1. **`UNPACK_ALIGNMENT` en 1.** El default es 4: una textura de 1 byte por
   texel con ancho no multiplo de 4 se sube corrida fila a fila. 1280 y 1920 lo
   son, pero la directiva del operador es que el front acepte cualquier
   resolucion, asi que esto no es opcional.
2. **Correccion de medio texel** al indexar la paleta (`idx * 255/256 +
   0,5/256`). Sin ella el lookup cae en el borde entre dos entradas y los
   colores salen corridos una posicion. El test lo verifica para los 256
   indices, no para una muestra.
3. **`highp` con fallback a `mediump`**: 256 niveles necesitan pasos de 1/255 y
   mediump (~2^-10) entra sin margen.

**Fallbacks, ninguno opcional:** modo no PIXEL, shader que no compila,
LUMINANCE ausente, o sonda de 2x2 rechazada -> camino RGBA anterior entero. Y
si la primera subida indexada del video falla, se degrada a RGBA **en caliente**
y el cuadro se rehace completo: no hay hueco visible.

### W-19: como se estira 1280 a un panel de 1920

- **`nearest`**: 1 tap, identico a antes, bit a bit. Sigue siendo el default.
- **`soft`**: 4 taps NEAREST sobre los INDICES, 4 lookups de paleta y mezcla de
  los COLORES resultantes. Interpolar indices produce colores arbitrarios (el
  indice 100 entre el 99 y el 101 no tiene relacion de color con ellos), por eso
  la textura de indices **nunca** se filtra con LINEAR.

**Decision que el diseno no fijaba y hubo que tomar:** en `soft` el backing
store del canvas sigue al **tamano de presentacion**. Con el framebuffer del
tamano de la grilla cada fragmento cae justo en el centro de un texel y la
mezcla de 4 taps seria un no-op: el estirado real lo estaria haciendo el
compositor igual que antes. El player informa ese tamano con
`setPresentationSize()` y vuelve a presentar si cambio (redimensionar el
backing store lo deja en blanco). En `nearest` no cambia nada: cols x rows.
Canvas2D declara la misma interfaz y NO cambia su backing store; su `soft`
sigue siendo el remuestreo del compositor, que es la asimetria entre renderers
ya documentada.

Ademas `?scale=int` en el player y en el diagnostic: escala por un entero con
letterbox. No es candidato a producto -desperdicia panel- pero es la unica
forma de ver el aporte del filtro sin el remuestreo fraccionario encima.

### Evidencia

- **Paridad de pixeles GL vs Canvas2D, con contexto WebGL real**: el diagnostic
  la corre al abrir y publico **`paridad GL/2D: OK (delta max 0, camino
  indexado)`**. Delta maximo CERO sobre el frame sintetico, y el camino activo
  fue el indexado. Es el criterio de cierre de W-18, y no se puede correr en el
  CI porque ahi no hay GL.
- **La conversion en CPU efectivamente desaparecio**: en el mismo diagnostic,
  con el clip de produccion 1280@15 v3, la etapa `rgba` marca **0,00 ms** por
  frame (antes era la etapa mas cara despues del walk).
- `tests/test_render_indexed.js` (cableado en `run_all.py`) fija el contrato con
  el driver: formato y alineacion de la subida, que la CPU no convierta, que la
  banda parcial sea una VISTA de `cells`, que la paleta se re-suba solo cuando
  cambia, los cuatro fallbacks y la aritmetica del medio texel.

### Lo que NO cierra todavia

El criterio del operador para W-19 es visual y en el televisor: comparar sobre
el mismo video **1280 `nearest`**, **1280 `soft`** y **1920 nativo**. Eso queda
pendiente de su revision; el codigo esta listo y las tres presentaciones se
eligen por query string (`?rec=soft`, `?scale=int`).

Anotado del entorno: el panel de navegador de esta maquina no compone, asi que
`requestAnimationFrame` no dispara nunca aunque `document.hidden` sea false. La
paridad se pudo medir igual (no depende del loop), pero los percentiles por
frame necesitan una pantalla real. No es un problema del player: en un TV el
compositor corre.

---

## Instancia 035 - 2026-08-31 - W-20: cadencia anclada al display y pre-decode del keyframe

Commits `798203a` (implementacion) y `1cb0e38` (correccion de una asercion del
CI), regresion en verde. Ultima tarea de codigo de F9.

### (a) Judder

Decidir el cuadro con `floor(audio.currentTime * fps)` reparte los frames en
5/7/6/6 refrescos en vez de 6/6/6/6, porque en TVs viejos `currentTime` avanza a
saltos gruesos. Ahora la fase avanza con el reloj del **display** y se corrige
**lento** contra el maestro (2 % del desvio por cuadro); un desvio mayor a 2
cuadros -seek, loop, stall- resincroniza de una. El audio sigue siendo el reloj
maestro: lo que deja de decidir es el instante exacto de cada cuadro.

Detalle que costo un bug: el primer cuadro despues de un reset se engancha al
maestro sin corregir, y la bandera que lo marca es **explicita** porque
`performance.now()` puede valer 0 justo al abrir la pagina — con una condicion
sobre `lastTick` el enganche se repetia y la correccion nunca arrancaba.

### (b) Jank de keyframe

Tres de cada cuatro callbacks a 60 Hz para un video de 15 fps solo miran el
reloj y vuelven a agendar. Ese tiempo ahora adelanta el proximo **keyframe**,
que no depende del estado actual y por eso es seguro adelantar. Solo se adelanta
si entra con margen (`slack > costo medido + 4 ms`): un pre-decode que no llega
a tiempo provoca exactamente el tiron que esto viene a sacar. El costo se mide y
se recuerda (maximo con decaimiento), no se supone.

**Decision de implementacion:** el «buffer alterno de `cells`» del diseno es, en
los hechos, un **segundo reader sobre los mismos bytes**, y adoptarlo es
**intercambiar** los dos readers. Cada uno queda internamente consistente
-paleta, dirty y `decodedIndex` viajan juntos-, asi que no hay que abrirle un
modo fuera de linea a la maquinaria dirty ni tocar la transaccionalidad del
invariante 4. El adoptado trae `dirtyFull` de su propio keyframe, o sea que el
renderer sube el cuadro entero, que es lo correcto. Cuesta otro `cells` (2 MB a
1920) mas su scratch de inflate: **anotado para MEM-001**.

Las dos piezas se apagan desde el TV sin recompilar: `?pacing=off` y
`?predecode=off`.

### Evidencia en CI

`tests/test_tv_player_runtime.js` corre el controlador real en un DOM falso con
reloj y `requestAnimationFrame` manuales:

- con un reloj maestro a saltos gruesos (audio en escalones de 200 ms, display
  parejo de 50 ms, 10 fps) la presentacion **nunca salta dos cuadros ni
  retrocede** y sigue avanzando. Sin pacing la misma secuencia da
  0,0,0,0,2,2,2,2,4... — el test falla si se revierte;
- el keyframe siguiente se adelanta en el callback ocioso, **el cuadro
  presentado sale del reader adelantado** y no se decodifica dos veces;
- sin keyframe proximo no se adelanta nada «por las dudas».

### Lo que NO cierra todavia

El criterio de cierre de W-20 es del diagnostic **sobre pantalla real**: a 1920,
drops < 0,1 % y p95 de decode+render bajo el presupuesto de frame. En esta
maquina no se puede medir: el panel de navegador no compone y
`requestAnimationFrame` no dispara nunca (verificado: `document.hidden` es false
y aun asi 0 callbacks en 1,5 s). Queda para el TV, junto con la comparacion
visual de W-19.

### Fallo de CI del camino, y por que importa

El primer push rompio `test_tv_player_page.js`: una asercion exigia
`disposeRenderer(true); reader=null; lastShown=-1` como **bloque literal
contiguo**, y W-20 metio la liberacion del segundo reader en el medio. La
propiedad que ese test cuida seguia valiendo. Se reescribio para verificar
contenido y orden dentro del cuerpo de la funcion -y de paso cubre lo nuevo: el
reader de pre-decode y el `ArrayBuffer` del clip tampoco deben quedar
retenidos-. Un test que compara texto contiguo no verifica una propiedad: obliga
a reescribirlo cada vez que algo se inserta al lado.

## Instancia 036 - 2026-08-31 - Ruido reportado por el operador: dos defectos reales, y su veredicto visual de W-19

### Como aparecio

El operador probo el frontend acelerado y reporto, sin numeros: «hay mucho ruido
al activar algunos parametros, asi que parece que no esta saliendo como
queremos». No habia test rojo: el CI estaba en verde con W-16..W-20 adentro. El
reporte a ojo encontro lo que la bateria no miraba.

### Defecto 1 - la banda subida a la GPU salia del reader anterior

`_drawIndexed` cachea una **vista** (`subarray`) de la banda sucia de `cells`
para no crear un objeto por frame (invariante 7). La clave del cache eran solo
las filas `y0..y1`. W-20 introdujo el **intercambio de readers**: al adoptar el
keyframe pre-decodificado, `cells` pasa a ser otro `Uint8Array`, pero si la banda
sucia media igual, la vista vieja seguia viva y se subia a la textura el
contenido del **reader anterior**. Se ve como franjas con imagen de otro momento,
apareciendo cada tantos segundos - exactamente la cadencia de los keyframes.

Arreglo: la clave del cache incluye ahora el **origen** (`_subCellsSource !==
cells`), y se limpia en `init`, `_downgradeToRgba` y `dispose`. Regresion:
`tests/test_render_indexed.js` seccion 7 dibuja la misma banda con dos `cells`
distintos y exige que lo subido sea el segundo.

Lo que esto ensena: cachear por **rango** una vista sobre un buffer que puede ser
reemplazado es un alias silencioso. La identidad del buffer es parte de la clave,
no un detalle.

### Defecto 2 - `soft` calculando en `mediump`

La reconstruccion de 4 taps de W-19 necesita la parte fraccionaria de la
coordenada en texeles. A 1920 esa coordenada llega a ~1920,0: en `mediump` (10
bits de mantisa) la fraccion **ya no existe**, y `fract()` devuelve basura. El
codigo tenia caida a `mediump` como fallback de compilacion, asi que en un driver
sin `highp` el shader compilaba **y dibujaba ruido**.

Arreglo: `soft` solo se activa con `highp` real, consultado con
`getShaderPrecisionFormat(FRAGMENT_SHADER, HIGH_FLOAT).precision > 0`. Si no lo
hay, `softBlocked = true`, se dibuja `nearest` y el HUD del diagnostic lo dice
(«soft NO activo: driver sin highp»). `softActive` -no `reconstruction`- es lo
que gobierna `_targetSize`, para que el backing store no siga a un modo que no se
esta dibujando. Regresion: seccion 8, con `HIGH_FLOAT` agregado al mock de GL.

Lo que esto ensena: una caida de precision es un fallback valido para **compilar**
y una fuente de basura para **calcular**. No son la misma decision.

Commit `af6bfff`, CI verde.

### Veredicto visual del operador (W-19), sobre PC

Con el arreglo puesto, el operador miro tres cosas y respondio:

| Que miro | Respuesta |
| --- | --- |
| `tv-player.html` (nearest, como hoy) | «se ve igual» - sin ruido, fluido |
| `tv-player.html?rec=soft` (4 taps) | «se ve igual» - **no distingue soft de nearest** |
| `diagnostic-player.html`, linea de paridad | `paridad GL/2D: OK` en el navegador de la PC |

Tres conclusiones:

1. **El ruido era de los dos defectos, no del diseno.** Desaparecio con el
   arreglo, sin tocar el formato ni los bytes.
2. **W-19 se cierra con `nearest` como default.** Si el operador no distingue la
   mezcla de 4 taps, no se paga: `nearest` es 1 tap contra 4 y es bit-identico a
   lo que habia. `soft` queda disponible por video (`?rec=soft`), que es
   justamente como el operador quiso que se decidan resolucion y reconstruccion.
3. **La paridad GL/2D quedo verificada tambien fuera de esta maquina**, en un
   navegador que si compone.

La comparacion `1280 soft` vs `1920 nativo` **en el TV** no se cae: se **mueve a
F8**, que es la fase de validacion en TV fisico. Mantenerla como bloqueo de F9
seria pedirle a esta fase un gate que pertenece a la siguiente, y el codigo de F9
ya esta verificado por otras vias (bench HEAD-vs-baseline, paridad con GL real,
byte-identidad).

## Instancia 037 - 2026-08-31 - W-20 CERRADA: medicion del operador sobre pantalla real

### La medicion

El operador corrio `diagnostic-player.html` en el navegador de su PC (que sí
compone, a diferencia del panel de esta maquina) sobre el **clip de produccion**:
`ASCL v3 · 1280x720 @15 · webgl/nearest · pacing on`, 166 frames y **497
presentaciones** -el clip dura 15 s y se repitio, asi que la ventana de muestreo
es de ~33 s-, `pre-key 27/28`.

| etapa | ult | media | p50 | **p95** |
| --- | --- | --- | --- | --- |
| inflate | 7,70 | 4,32 | 4,50 | **8,70** |
| walk | 0,00 | 0,45 | 0,00 | **3,20** |
| **rgba** | 0,00 | 0,00 | 0,00 | **0,00** |
| blit | 0,00 | 0,16 | 0,10 | **0,50** |
| otros | 4,00 | 2,37 | 2,50 | **6,00** |
| decode | 11,70 | 7,14 | 7,30 | **14,80** |
| **FRAME** | 11,70 | 7,31 | 7,30 | **14,90** |
| pre-key | 7,00 | 10,20 | 10,80 | **14,10** |

| grilla@fps | rend | p50 | p95 | presupuesto | drops | tarde |
| --- | --- | --- | --- | --- | --- | --- |
| 1280x720@15 | gl | 7,30 | **14,90** (verde) | 66,7 | **0** | **0** |

`paridad GL/2D: OK (delta max 0, camino indexado)`.

### Veredicto

**W-20 cumple su criterio con holgura de 4,5x.** El presupuesto a 15 fps es 66,7
ms y el p95 de decode+render es 14,90: se usa el **22 %**. Drops **0** y frames
tarde **0** sobre 497 presentaciones (el criterio era < 0,1 %, o sea < 1 drop en
esta ventana).

Tres cosas que la tabla confirma y que valen mas que el numero global:

1. **`rgba` en 0,00 ms en produccion.** W-18 no era un efecto de banco: con el
   clip real, en la maquina real, la conversion indice->RGBA **desaparecio** del
   presupuesto. La GPU recibe indices y resuelve la paleta en el shader.
2. **El pre-decode no entra al presupuesto.** `pre-key` marca p95 **14,10 ms**,
   comparable a un frame entero, y aun asi hay **0 drops**: corre en el tiempo
   muerto, exactamente como se diseno. Publicarlo en una fila aparte fue lo que
   permitio verificarlo en vez de suponerlo. 27 de 28 keyframes se adelantaron.
3. **El cuello de botella se movio a `inflate`** (p95 8,70 de los 14,90 del
   frame, ~58 %). Despues de W-17 y W-18, lo que queda caro es **descomprimir**,
   no convertir ni dibujar. Es el dato que ordena cualquier optimizacion futura
   del frontend: `W-21` (dirty en X) toca `walk`, que ya esta en 3,20; el
   margen grande esta en el bloque comprimido (ver `bench-inflate`).

### Lo que esta medicion NO dice

Es una GPU de PC a 1280@15, no un TV. **No se midio a 1920** ni sobre hardware de
television, y un TV viejo es mucho mas lento que esta maquina: la holgura de 4,5x
es justamente el margen que F8 tiene que confirmar que alcanza. Eso **es** F8, no
un pendiente de F9. Con esto, F9 queda con todos sus criterios medibles cumplidos
y lo unico que resta para cerrar la fase es **publicar el frontend acelerado**.

## Instancia 038 - 2026-08-31 - Publicacion del frontend de F9, y la directiva de que una actualizacion no pierde nada

### La directiva del operador

Ante la propuesta de cambiar la pagina principal del player, el operador fijo un
principio: **«no deberiamos perder cosas con las actualizaciones, por que son
eso, actualizaciones; deben ser mejoras de lo que ya tenemos»**. Y una segunda
directiva operativa: **guardar en el repo lo que esta vivo en Cloudflare antes de
actualizarlo**, y hacer la publicacion con las herramientas ya cargadas en vez de
pedirle pasos manuales.

Las dos corrigieron el rumbo. Yo venia proponiendo (a) reemplazar el
`live-player.html` publicado por `tv-player.html` -que habria borrado overlay,
textos y datachannel- y (b) una ruta por CI con un secret pegado a mano.

### Lo que no estaba guardado (y ahora si)

Antes de tocar nada se hizo la copia. Aparecieron tres cosas que **solo existian
dentro de Cloudflare**:

1. **El `worker.js`** no estaba en ningun lado del repo. Si alguien lo pisaba, no
   habia copia. Ahora vive en `deploy/asciline-player/worker.js`, verbatim.
2. **El arbol servido** se armaba en `outputs/deploy-player/`, que esta en
   `.gitignore`. Los 15 archivos de texto de la raiz se bajaron del bucket y sus
   13 `md5` coinciden uno a uno con los `etag` de R2.
3. **El mapa real de keys**: 71 objetos, en `MANIFEST.tsv`.

Dos hechos que el manifiesto probo y que el proyecto tenia mal documentados:

- **`index.html` es `live-player.html`** (mismo `etag` `534abb7e...`), en las
  cuatro carpetas. Lo que sirve `iargen.com/player/` es el **live-player**, no el
  `tv-player.html` que el MAPA llama «produccion». `tv-player.html` **no estaba
  publicado en ninguna key**.
- **Las tres variantes tienen copias byte-identicas del codigo de la raiz.** Lo
  unico propio de cada una es su `outputs/clip.asclv`. Toda actualizacion de
  codigo va a las cuatro carpetas o quedan desparejas.

### La publicacion

Se subieron **24 keys** = (4 archivos que F9 cambio + 2 paginas nuevas) x 4
carpetas. Procedimiento, entero desde la sesion, sin CI y sin pasos manuales del
operador:

1. Acunar un `UPLOAD_TOKEN` efimero en el worker por la API de Cloudflare.
2. `PUT /__upload/<key>` con `x-upload-token` y `x-sha256` (doble verificacion:
   el que sube calcula el digest y R2 lo recalcula del cuerpo recibido).
3. Verificar bajando lo servido: **los 24 byte-identicos al repo**.
4. Quemar el token con un valor aleatorio generado dentro de la llamada y nunca
   devuelto. Comprobado: el token viejo da **403**, y sin token tambien.

**La actualizacion fue puramente aditiva.** Los 11 archivos restantes conservan
exactamente el `md5` que tenian antes, comprobado contra el manifiesto: overlay,
textos y datachannel siguen intactos. Nada se perdio.

Se **descarto** el workflow `publish-frontend` que se habia escrito para la ruta
por CI: exigia un secret de GitHub, o sea persistir un token, que es justo lo que
el modelo de trabajo prohibe. Se borro en el mismo commit.

### Lo que la publicacion SI y NO le da al player publico

`live-player.html` carga los mismos `reader*.js` y `render-*.js` que se
actualizaron, asi que la raiz **gana W-17 y W-18** -LUT de paleta e indices por
GPU, las dos ganancias grandes- sin ningun cambio de comportamiento.

**No gana W-20**, porque la cadencia y el pre-decode se escribieron en
`tv-player.html`, que es otra pagina. Aplicando la directiva del operador, la
salida correcta **no** es reemplazar una por otra -eso perderia overlay y
textos-: es **portar W-20 a `live-player.html`**, que suma sin restar. Queda como
la tarea que cierra F9.

## Instancia 039 - 2026-08-31 - Un solo motor de reproduccion (W-22..W-25) y el CI que Pro no destrabo

### El pedido del operador

Textual: «fusionar los backgrounds (del front) para que todos los reproductores tengan
todas las mejoras para que puedan correr los nuevos formatos con la mayor eficiencia».
Antes de eso pidio revisar el CI, porque se habia suscrito a Pro suponiendo que el
bloqueo era por minutos agotados. Y despues de la fusion queria comparar 1280 vs 1920.

### El estado que encontro esa peticion

W-20 (cadencia + pre-decode) estaba escrita **dos veces**, copiada, dentro de
`tv-player.html` y de `diagnostic-player.html`. No existia en `live-player.html` -que es
lo que sirve la raiz publicada, segun probo el manifiesto del bucket en la Instancia
038- ni en `player.html`. La consecuencia practica: las ganancias que el operador midio
en su pantalla no estaban llegando al producto, y el diagnostic medía **una copia
parecida** del codigo de produccion, no el codigo de produccion.

### Lo que se hizo

- **W-22** (`3c46d3d`): la maquinaria se extrajo a `frontend/playloop.js`, con
  `tests/test_playloop.js` cableado en `run_all.py` en el mismo commit (regla 7). El
  motor **no es dueno del reader que se muestra**: la pagina se lo pasa en cada llamada
  y el intercambio queda explicito, porque la pagina tambien tiene que reapuntar su
  renderer y su overlay. Esconderlo detras de un accessor habria escondido justamente lo
  que hay que hacer bien.
- **W-23** (`2753fd1`): `tv-player` y `diagnostic` pasan al motor. El diagnostic
  instrumenta los DOS readers via el hook `onSpare`, asi que el desglose por etapa sigue
  siendo valido despues de un intercambio **y** ahora mide literalmente lo que corre en
  produccion.
- **W-24** (`26b4170`): `live-player` y `player.html` estrenan cadencia y pre-decode.
- **W-25** (`1fe95a9`): el gate ES5 descartaba un `<script>` si la **coincidencia
  entera** contenia `src=`, no si lo contenia la etiqueta. Un `var src=DEFAULT_SRC;`
  bastaba: `player.html` y `diagnostic-player.html` llevaban tiempo sin analizarse.

### La decision de diseno que costo pensar: intercambio de readers CON overlay

El pre-decode adopta un reader que decodifico su keyframe por su cuenta, o sea que sus
celdas **nunca vieron un parche**. El overlay guarda la base de las celdas que pinta y
la devuelve en `beforeSeek`. Si se reapunta mal, hay dos formas de romperlo: restaurar
sobre el reader nuevo una base que pertenece al viejo (escribe celdas de otro cuadro), o
dejar `overlay.reader` apuntando al viejo y que `afterSeek` pinte en el reader que ya no
se muestra.

El orden correcto es uno solo: `beforeSeek` (reader que se va) -> intercambio +
`overlay.rebind(reader)` -> `afterSeek` (reader que llega). `rebind` apaga
`restoreValid` porque la base guardada ya no aplica. El reader desplazado queda limpio
-su base fue devuelta- y cuando vuelva a usarse su proximo trabajo es un **keyframe**,
que reescribe todas las celdas: no arrastra parches.

El gate nuevo en `test_overlay_runtime.js` no verifica el mecanismo sino la propiedad
que importa: **adoptar y no adoptar tienen que dar exactamente las mismas celdas**.

### Verificacion posible sin CI

El CI sigue bloqueado, asi que las cuatro tareas quedan `en curso`, no `cerrada`. Lo que
si se pudo verificar, y se hizo:

- Las **cuatro paginas** cargan el clip de produccion servido local (`serve-local.ps1`)
  **sin un solo error de consola**, con `playloop.js` en 200 en todas. El diagnostic
  reporta `paridad GL/2D: OK (delta max 0, camino indexado)`; el live-player levanta
  overlay, texto nativo e imagen con giro.
- Las 16 expresiones del gate ES5 (`test_frontend_compatibility.js`), corridas aparte
  sobre los seis archivos tocados -incluidas las dos paginas que el gate no miraba-:
  **sin hallazgos**.

Lo que esto NO cubre, y por eso las tareas no se cierran: los tests de pagina y de
runtime (que sí ejercitan el intercambio con readers falsos), el gate de overlay nuevo y
la regresion Python entera.

### El CI: Pro no lo destrabo, y el porque probable

Se relanzo el run bloqueado y se empujaron los cuatro commits. Los tres jobs siguen
muriendo **a los 2 segundos sin ejecutar un paso**, con la misma anotacion literal:
pagos fallidos o limite de gasto. Dato nuevo que lo explica: el repo es **privado** y su
dueno es **`tablerosapp-ctrl`** (cuenta de usuario), mientras que quien empuja es
**`leoIglesias-hash`**. GitHub factura los minutos de un repo privado **al dueno del
repo**. Si el Pro se contrato en otra cuenta, no aplica.

Salidas, las dos del operador: (a) Pro + metodo de pago valido + limite de gasto > 0 en
**`tablerosapp-ctrl`**, o (b) repo **publico**, donde los minutos son ilimitados. El
token de esta sesion (scopes `gist, repo, workflow`) no puede leer la facturacion de esa
cuenta, asi que el diagnostico es estructural: se confirma abriendo Billing & plans de
`tablerosapp-ctrl`.

## Instancia 040 (2026-08-31) - El repo de trabajo se muda a `leoIglesias-hash` y el CI arranca

### Que pidio el operador

> «claro yo me pase a pro con leoIglesias-hash, ya esta hice cagada.. ahora podrias
> descargar el proyecto y subirlo a mi github? para poder seguirlo desde ahi? luego
> podriamos sincronizarlo cuando tenemos puntos de guardado.. al terminar dejare todo en
> tablerosapp-ctrl y listo»

O sea: el Pro esta en la cuenta que empuja, no en la que es dueña del repo. En vez de
mover la suscripcion, se mueve el repo.

### Que se hizo

La credencial guardada en el Credential Manager de Windows resulto ser de
**`leoIglesias-hash`** con scopes `gist, repo, workflow` - alcanza para crear el repo y
para empujar `.github/workflows/`. Con eso:

1. **`leoIglesias-hash/ASCILINE-video` creado privado** por API (`POST /user/repos`,
   201), sin `auto_init` para que el push entre limpio.
2. **Espejo completo**, no solo `main`: `main`, `assets` (los insumos de encode, que son
   lo que el workflow `encode` consume), `feature/quality-optimization` y los **7 tags**.
   98 MB de historia.
3. **Remotos renombrados** para que el default sea el repo del operador:
   `origin` -> `leoIglesias-hash/ASCILINE-video`, `ctrl` -> `tablerosapp-ctrl/ASCILINE-video`.
   `main` quedo trackeando `origin/main`.
4. Se **cancelo a mano** el run que `feature/quality-optimization` disparo de arrastre
   (codigo viejo, minutos gastados al pedo).

### El resultado: CI verde, y el diagnostico confirmado sin leer facturacion

El push de `main` disparo `regression` sobre `866f2f1` -que ya trae **todo** el codigo de
F9, W-22..W-25 incluidas- y **los tres jobs pasaron**: `test (py3.8)`, `test (py3.11)` y
`test (py3.11 + zopfli)`, **verde en 52 s**. Contra los 2 segundos sin ejecutar un solo
paso que venian dando las ultimas cuatro instancias en el repo viejo.

Eso **prueba** lo que la Instancia 039 solo podia inferir: no habia nada roto en el
codigo ni en los workflows; los minutos de un repo privado se le cobran **al dueño del
repo**, y el dueño era una cuenta sin Pro. El experimento fue mejor que leer la pagina de
Billing: cambiar de dueño y ver correr los mismos workflows aisla la variable.

Tambien disparo `publish-player` (el filtro por `paths` matchea en un push inicial,
donde *todos* los archivos cuentan como cambiados). Termino en **success sin publicar
nada**: `tools/publish-player-request.json` esta en su estado de reposo con `run_id`
vacio. Es exactamente el comportamiento que ese estado de reposo existe para dar.

### Consecuencia inmediata

**W-22, W-23, W-24 y W-25 pasan de `en curso (CI bloqueado)` a `cerrada`.** F9 queda con
un unico pendiente que no es codigo: publicar el frontend a las cuatro carpetas del
bucket (25 keys) y escribir el resumen en `ejecutados/`.

### Por que mudar el repo y no hacerlo publico

La otra salida (repo publico = minutos ilimitados) tambien destrababa el CI, pero
expone el codigo. Mudarlo no expone nada -sigue privado-, no depende de arreglar pagos en
una cuenta ajena, deja el repo original intacto como destino final, y es reversible: el
dia que el operador quiera consolidar, `git push ctrl main` y listo.

### Publicacion de F9 (segundo acto): 28 keys, no 25

El operador aprobo publicar de forma explicita. Antes de subir nada se **audito lo
servido**: 18 archivos x 4 carpetas bajados de `iargen.com/player/` y comparados por
SHA-256 contra el repo. Resultado: 4 diferian (`live-player.html`/`index.html`,
`tv-player.html`, `diagnostic-player.html`, `overlay.js`), 2 daban 404 (`playloop.js`,
`player.html`, este ultimo nunca habia estado publicado) y los 12 restantes estaban
identicos. **7 keys por carpeta x 4 = 28**, contra las «25» que decian los runbooks.

Vale la pena que esa auditoria sea el primer paso de toda publicacion: cuesta 68 GETs,
y detecto que una cuenta escrita a mano ya estaba mal.

Subida con el procedimiento de `deploy/asciline-player/README.md` (token efimero por
API, `PUT /__upload/<key>` con `x-sha256` que R2 recalcula del cuerpo recibido). Las 28
verificadas byte a byte despues de subir; mismatches 0.

**Hallazgo operativo sobre el burn del token:** el `PUT` del secret devuelve 200
enseguida, pero **el worker tarda unos segundos en ver el valor nuevo**. El primer
intento con el token viejo dio `200` -o sea, seguia siendo valido- y recien el siguiente
dio `403`. Dar por quemado un token con una sola prueba es un falso negativo de
seguridad: hay que reintentar hasta ver el 403.

### DIAG-002 abierta: pantallazos blancos en TV box

El operador reporto, al final de esta instancia:

> «tenemos que ver un problema grave de reproduccion en los tv box.. lo acabo de probar
> en un webview y me da pantallazos blancos. eso es algo critico […] salen pantallazos
> blancos entre las imagenes de telekino, eso es muy grave y deberiamos estudiarlo»

Se abre **DIAG-002** y se pone **adelante de F10**: un flash blanco en un televisor rompe
el producto, pesa mas que cualquier ganancia de bytes o de milisegundos.

Encuadre que conviene no perder al retomar: lo que el operador probo es **lo que estaba
publicado antes de esta instancia**, es decir la raiz (`live-player.html`) **sin**
cadencia ni pre-decode -esas piezas vivian en otra pagina y recien ahora estan en la
raiz-. Que el motor unico mejore, empeore o no cambie el sintoma **hay que medirlo**; no
se puede suponer en ninguna de las dos direcciones. Tampoco esta establecido de donde
sale el blanco: canvas limpiado, fondo de la pagina asomando, o recreacion del contexto.

#### DIAG-002, primer corte: el blanco NO esta en los datos

Se agrego `tools/diag_white_frames.py` y el workflow manual `diag-white-frames`, que
**baja el clip exacto que sirve el player publicado** y lo decodifica con el decoder de
referencia. Run 33440003966 sobre `https://iargen.com/player/outputs/clip.asclv`
(1280x720, 231 cuadros, 15 fps, ASCL v3, PIXEL):

| Metrica | Valor |
|---|---|
| luma media | min 97,1 / mediana 110,1 / **max 160,5** |
| celdas casi blancas (luma >= 235), maximo | **20,7 %** del cuadro (cuadro 71, t=4,73 s) |
| saltos de luma media >= 40 entre cuadros consecutivos | **ninguno** |

**Veredicto: ningun cuadro se acerca a ser blanco.** El cuadro mas claro de todo el clip
tiene una quinta parte de celdas casi blancas y una luma media de 160 sobre 255. No hay
transiciones bruscas. El encoder y el formato quedan **descartados**: lo que el operador
ve no viene de los bytes.

#### Lo que aportaron las respuestas del operador, y como reencuadra el problema

Tres datos, y los tres apuntan en la misma direccion:

1. **Se pone blanca TODA la pantalla**, no solo el area del video.
2. **Pasa al azar**, sin relacion con los cortes ni con el reinicio del clip.
3. Es un **WebView embebido en una app**, no el navegador del dispositivo.

El dato (1) es el que decide. El `body` de la pagina es `#0d0d10` y el canvas tiene
`background:#000`: **cualquier falla del canvas se veria NEGRA**, no blanca, y no podria
llevarse puesto el fondo de la pagina. Si se blanquea todo -fondo incluido- entonces lo
que se ve **no es la pagina**: es el WebView mostrando su propio blanco porque en ese
instante no hay pagina que pintar.

Eso saca el problema del pipeline de video y lo lleva a **estabilidad del WebView**. La
hipotesis principal pasa a ser que **el proceso renderer se muere y se recrea** (en
Android WebView el sintoma canonico es exactamente ese: pantalla blanca completa,
aleatoria, sin relacion con el contenido). La causa mas probable de que se muera es
memoria: el clip entero vive como `ArrayBuffer` de **24,4 MB**, mas la copia que la
respuesta XHR mantiene mientras se carga, mas `cells`, mas texturas -y desde W-20 un
**segundo reader** con su propio `cells`, que ya estaba anotado en **MEM-001**-. En una
caja de TV con memoria por proceso acotada, eso es un candidato serio.

**La pregunta que lo confirma o lo descarta, y que hay que hacerle al operador:** despues
del pantallazo, **el video vuelve a empezar desde el principio?** Si vuelve al cuadro 0,
el renderer se murio y se recargo la pagina, y el problema es de memoria/estabilidad. Si
sigue donde estaba, no hubo recarga y hay que buscar en composicion o en la app que
hospeda el WebView.

Mitigacion inmediata, del lado de la app y sin tocar el player: pintar el WebView de
negro (`setBackgroundColor`). No arregla la causa, pero convierte un flash blanco en un
parpadeo negro contra una pagina oscura, que es mucho menos violento.

#### DIAG-002, segundo corte: el renderer NO se muere; se cae la presentacion

El operador refino el sintoma (2026-08-31, sus palabras): *"muestra el primer frame, el
segundo tercero cuarto (al azar) va en blanco, luego muestra otro frame al azar, y asi..
no funciona. Los frames que muestra o quedan en blanco son completos, es decir, la
pantalla pintada en su totalidad de blanco o del frame."*

Esa descripcion **contesta la pregunta decisiva del primer corte sin hacerla**: despues
de los blancos aparece **otro frame mas adelante**, no el cuadro 0. La reproduccion
avanza -> el JS esta vivo -> **la pagina nunca se recargo** -> el proceso renderer del
WebView NO se esta muriendo. La hipotesis de muerte-y-recreacion queda **descartada**
(y con ella la urgencia de MEM-001 como causa de ESTO; MEM-001 sigue anotada por
derecho propio).

Lo que queda es una falla de **presentacion**: el loop corre, el seek avanza, pero la
mayoria de los cuadros no llegan compuestos a la pantalla; en esos vsyncs el WebView no
tiene superficie valida y se ve el blanco de la ventana de la app que esta detras. Que
sea la MAYORIA de los cuadros (2-4 blancos por cada uno visible) tambien descarta un
hipo ocasional de GC: es sistematico.

**Sospechoso principal: WebGL en la GPU/driver de la caja.** `pickRenderer()` en
`live-player.html` elige WebGL siempre que `init()` devuelva true; el fallback a
Canvas2D solo se dispara si la creacion falla o si llega `webglcontextlost`. Una GPU
vieja que compila, dibuja "bien" por API y **no presenta** no dispara ninguno de los
dos. Canvas2D es el piso por regla 6, y en las cajas de TV puede ser tambien el unico
camino que compone.

**La prueba decisiva ya esta publicada** (tv-player soporta `?renderer=` desde F4/W-14):

| URL en el MISMO WebView | Renderer |
|---|---|
| `https://iargen.com/player/tv-player.html?renderer=canvas2d` | Canvas2D forzado |
| `https://iargen.com/player/tv-player.html` | auto (elige WebGL) |

- 2D limpio + auto blanco -> **causa = WebGL de la caja**; salida: default/deteccion por
  entorno (y decidir si la raiz necesita el parametro o directamente otro default).
- Los dos blancos -> la composicion falla independiente del renderer; el diagnostico se
  muda a la capa de la app (hardware acceleration del WebView, tipo de layer).
- Los dos limpios -> el sintoma es propio de `live-player.html` (la raiz) y hay que
  bisectar que tiene la raiz que tv-player no.

Mitigacion inmediata sin esperar el resultado, del lado de la app:
`setBackgroundColor(negro)` en el WebView -> el blanco pasa a negro.

**Mitigacion del fondo negro DESCARTADA por el operador** (2026-08-31): *"tiene mucho
blanco... asi que si se nota"* -- el clip de Telekino es claro, un parpadeo negro se ve
igual de mal que uno blanco. No re-proponerla: DIAG-002 se cierra solo con la causa
real arreglada.

#### DIAG-002, tercer corte: CAUSA CONFIRMADA - WebGL de la caja no presenta

El operador corrio la prueba decisiva en el WebView de la TV box, sirviendo
`frontend/` + `outputs/` desde su propio servidor (mismo clip `dcd6afb6...`,
verificado por SHA antes de subir):

| Renderer | Pantallazos blancos |
|---|---|
| auto (WebGL) | SI |
| `?renderer=canvas2d` | NO |

**Veredicto: el blanco lo pone el camino WebGL de esa GPU/driver.** El contexto se crea
e `init()` devuelve true, asi que `pickRenderer()`/`chooseRenderer()` lo eligen; dibuja
"bien" por API pero la mayoria de los cuadros no llegan compuestos, y no dispara
`webglcontextlost` ni ningun fallback. Canvas2D (el piso, regla 6) compone siempre.
Consecuencia de diseno: **"WebGL solo acelera" necesita un escape operable por URL en
TODAS las paginas** - hoy la raiz (`live-player.html`) no acepta `?renderer=` y elige
WebGL sin salida. Tarea de arreglo: W-26 (runbook).

#### DIAG-003 abierta: sin fluidez en la TV box, con CUALQUIER renderer

Mismo test, hallazgo nuevo (palabras del operador): *"en ninguno de los dos escenarios
hay fluidez... ambos muestran un video entrecortado, mostrando algunos frames y otros
salteandoselos; la unica diferencia es que canvas2d no da pantallazos blancos, pero se
traba de igual forma"*.

Que se saltee frames y muestre otros es exactamente lo que hace la cadencia de W-20
cuando el trabajo por cuadro excede el presupuesto (66,7 ms a 15 fps): descarta para no
atrasarse. En la PC del operador el frame costaba p95 14,90 ms con el cuello en
`inflate` (58 %); en la CPU de la caja todo es mas lento y la hipotesis natural es que
`inflate` + decode superan el presupuesto. **Pero se mide, no se supone**: el siguiente
paso es `diagnostic-player.html?renderer=canvas2d` en el MISMO WebView - ya esta en el
servidor del operador, carga `./outputs/` solo y publica en pantalla FRAME p50/p95,
presupuesto, drops, tarde y el costo por etapa (inflate/rgba/draw). Con esa foto se
decide el ataque (fps del clip, resolucion, optimizar inflate, W-21).

Esto es territorio F8 (p95 en TV real) llegando por la puerta del sintoma: DIAG-003
queda como el diagnostico puntual; F8 sigue siendo la fase que lo resuelve.

#### DIAG-003: alternativas discutidas con el operador (2026-09-01, sin decision aun)

El operador pregunto si se puede aprovechar el decodificador de video POR HARDWARE de
las TV box (VP8/H.264: silicio dedicado, lo unico que estas cajas hacen bien) con
nuestro formato. Analisis:

1. **Contrabandear indices en H.264** (indices como grises espaciados x8, redondeo al
   decodificar -> indice exacto pese al lossy): el truco existe pero exige LEER los
   pixeles por cuadro (`getImageData`, 921.600 celdas) y repintar -> mas CPU que el
   `inflate` que ya no entra; y el remapeo en GPU es el WebGL que esta caja no
   presenta. **Descartado para esta caja.**
2. **MSE** (alimentar `<video>` por JS): no cambia el idioma del decodificador, solo
   quien acerca los bytes. No resuelve; util a futuro para streaming.
3. **HIBRIDO (candidato):** el video base lo presenta `<video>` por hardware, pero
   renderizado POR NUESTRO ENCODER desde las celdas ya decididas (nuestra paleta/
   cortes/look; el H.264 agrega perdida chica de transporte, criterio ya adoptado
   "perdida minima aceptable si el ahorro lo vale"). La INTERVENCION (numeros, texto,
   logo, canal de datos) queda en el canvas encima, que pasa de repintar ~921.600
   celdas/cuadro a solo la zona intervenida. Esquiva los DOS problemas medidos
   (WebGL roto: no se usa; CPU corta: el peso va al silicio). **Costo: toca el
   invariante de un-solo-layer (pasarian a ser dos: video + canvas de intervencion).
   Es decision de PRODUCTO del operador, pendiente.**

La filosofia del proyecto se conserva en el hibrido: el encoder caro decide todo
offline y el TV solo ejecuta; lo que cambia es el transporte del video base.

**Pendiente del operador para decidir (mañana):**
- Numeros del HUD de `diagnostic-player.html?renderer=canvas2d` en el WebView de la
  caja (FRAME p50/p95, presupuesto, drops, tarde, costo por etapa inflate/rgba/draw)
  -> dice si el player actual tiene chance en estas cajas con optimizacion.
- Probar un mp4 en un `<video>` en ese WebView (p.ej. el `preview.mp4` del workflow
  encode) -> confirma que el carril hardware funciona dentro del WebView de la app
  (a veces las apps lo tienen desactivado).

Con esas dos respuestas se decide: optimizar el player actual (fps/resolucion/inflate/
W-21) o diseñar el hibrido formalmente.

## DIAG-003: la app escala el WebView a ~4K; el diagnostic ahora lo mide (2026-09-01)

Hallazgo del operador al montar el diagnostic en su app: **por efecto del escalado,
el WebView le reporta a la pagina un tamano mucho mayor del que se reproduce** (del
orden de 3840x2160). Dos consecuencias:

1. **Sospechoso adicional del entrecortado:** con un viewport 4K, `fitCanvas` estira
   el canvas por CSS a ese ancho y el compositor de la caja tiene que escalar cada
   frame 1280x720 -> ~3840x2160. Ese costo no aparece en ninguna etapa del HUD
   (inflate/rgba/blit): es del compositor. Habia que hacerlo visible.
2. **El HUD quedaba ilegible:** 12 px CSS sobre una pagina "de 4K" se ve microscopico
   (foto del operador).

Cambio en `frontend/diagnostic-player.html` (solo la pagina de diagnostico, ningun
archivo de produccion):

- Seccion nueva **"Pantalla / escala"** en el HUD: ventana CSS (y doc si difiere),
  fisico = ventana x devicePixelRatio (+ visualViewport.scale si existe), pantalla
  (screen.width/height), canvas buffer (backing real), canvas en CSS con el factor
  de estirado (`estira xN`). Se refresca con el HUD y en cada resize.
- **HUD escalable:** factor automatico = round(innerWidth/960) acotado a 1..6 (1x
  hasta ~1440, 2x a 1920, 4x a 3840); `?hud=N` lo fija; teclas **+/-** lo ajustan en
  caliente (0,25 por paso). ES5 estricto, sin dependencias.

Con esto, la proxima foto del HUD en la caja trae los dos datos que faltaban ver:
cuanto estira el compositor y los tiempos por etapa, legibles.

**Correccion del operador (mismo dia):** la primera version calculaba la escala del
HUD UNA vez al cargar; si el WebView toma su tamano despues (o no dispara resize),
el cartel queda chico igual. Lo pedido: "el video se ajusta al tamano, el cartel
debe hacer lo mismo". Ahora la escala es proporcional continua (ancho/1280, piso
0,75, tope 8) y se recalcula en cada refresco del HUD (400 ms), no solo al arranque:
a 3840 de ancho la fuente pasa a 36 px y el panel a 1290 px = la misma fraccion de
pantalla que 12 px/430 px en una ventana de 1280. Verificado en navegador emulando
399, 1280 y 3840 de ancho. `?hud=N` sigue fijando el factor y +/- multiplica encima.

## DIAG-003: PRIMERA MEDICION REAL EN LA TV BOX - el player JS no llega (2026-09-01)

Llego el dato (1) pendiente: foto del HUD de `diagnostic-player.html?renderer=canvas2d`
corriendo el clip PRODUCTO (1280x720@15 v3) en el WebView de la caja.

**Pantalla / escala (hallazgo confirmado y cuantificado):**
- ventana CSS **3840x2160**, dpr 1.00, vv 1.00 -> la app le da al WebView una
  superficie 4K...
- ...sobre un **panel fisico de 1280x720** (fila `pantalla`). La caja renderiza a 4K
  y reduce a 720p: 9x los pixeles necesarios, costo regalado al compositor.
- canvas buffer 1280x720, canvas en CSS 3840x2160 (estira x3.00).

**Etapas del frame en ms (presupuesto 66,7; 65 frames mostrados, drops 324, tarde 64):**

| etapa   | media | p50   | p95    |
|---------|-------|-------|--------|
| inflate | 134,6 | 110,5 | 331,4  |
| walk    | 85,2  | 36,2  | 485,5  |
| rgba    | 30,8  | 29,6  | 79,6   |
| blit    | 14,5  | 11,2  | 21,2   |
| otros   | 125,3 | 74,1  | 521,8  |
| decode  | 345,1 | 249,6 | 1130,1 |
| FRAME   | 390,4 | 290,2 | 1193,3 |

pre-key: 848,3 (una muestra). Paridad GL/2D: OK (delta max 0, camino indexado).

**Veredicto (cierra la pregunta 1 de la Instancia 041):** FRAME p50 = 290 ms contra
66,7 = **4,3x pasado de presupuesto; p95 18x**. Solo `inflate` (110 ms p50) ya se
come el presupuesto entero; `rgba` sola se lleva la mitad. Esta CPU es ~20x mas
lenta que la PC (p95 14,9 alli). **El player actual NO llega a 15 fps en estas cajas
por optimizacion de codigo**: haria falta acelerar ~5x el camino completo y las
etapas gordas ya estan optimizadas (W-17/W-18/W-20). El unico carril 100% JS seria
degradar el producto (~640x360 @ 8-10 fps entra JUSTO, en un panel que es
exactamente 1280x720).

**Queda UN dato pendiente y ahora decide todo: el mp4 en `<video>` en ese WebView.**
- Fluido -> el HIBRIDO (video hw renderizado por nuestro encoder + canvas solo de
  intervencion) pasa de candidato a unica via que conserva 1280@15 en estas cajas.
- No fluido -> el decode por hardware esta capado en la app; el problema se corre a
  la app, no al player.

Nota para la app (independiente de la decision): configurar el WebView al tamano del
panel (1280x720) en vez de 3840x2160 ahorra 9x de pixeles por composicion.

**Prueba propuesta por el operador (mismo dia): ¿cuanto cuesta la superficie 4K?**
Idea del operador: antes de encarar un APK que reporte 1280 reales, forzar el
diagnostic a reproducir al tamano para el que esta hecho (aunque se vea mas chico)
y medir si mejora. Implementado `?view=` en el diagnostic: `view=buffer` (o `1:1`)
pone el canvas EN CSS al tamano nativo del clip; `view=AxB` le pone un tope; la
tecla V lo alterna en caliente (con R despues para separar sesiones). La fila
`vista` del HUD dice el modo activo. Expectativa honesta, para leer el resultado:
inflate/walk/rgba trabajan sobre el buffer y NO dependen de la superficie; lo que
esta prueba mide es la CONTENCION del compositor 4K (blit, `otros`, drops). Si los
drops caen fuerte -> el APK a 1280 reales vale la pena; si no cambian -> el cuello
es la CPU y la superficie era secundaria.

## DIAG-003: vista 1:1 medida - la superficie 4K era secundaria; y llega la prueba mp4 (2026-09-01)

**Resultado de `?view=buffer` en la caja** (canvas 1280x720 en CSS, estira x1.00,
mismo clip producto): FRAME p50 290 -> 233 ms (mejora ~20 %), p95 1193 -> 935,
drops 731/169 frames (proporcionalmente igual). Veredicto: la superficie 4K roba
algo pero es SECUNDARIA; el cuello es CPU pura (inflate p50 98 + walk 62 + rgba 30
ya triplican el presupuesto de 66,7). **Ni un APK que reporte 1280 reales ni la
optimizacion salvan al player 100 % JS en estas cajas; la calidad no se baja mas
(decision del operador). Se pasa a evaluar el carril mp4** (dicho por el operador:
"Vamos a evaluar la opcion mp4 a ver que pasa").

**Herramienta nueva: `frontend/tv-video-test.html`** (ES5, sin dependencias) para
que la prueba de video por hardware de numeros y no impresiones:
- Reproduce un mp4 (`?src=`, default `./outputs/preview.mp4`) en `<video>` muted+loop.
- Publica: tamano de ventana/pantalla, video nativo vs en CSS, frames decodificados
  y CAIDOS (getVideoPlaybackQuality o webkitDecodedFrameCount), fps de decode
  efectivo, atascos (eventos waiting/stalled) y deriva reloj-video (si crece, el
  video atrasa contra el reloj de pared).
- Dos vistas pedidas por el operador: default ADAPTADA al viewport (object-fit
  contain) y `?view=1:1` clavada al tamano nativo sin adaptarse; tecla V alterna.
- HUD proporcional al viewport igual que el diagnostic (`?hud=N`, +/-).
- `tools/serve-local.ps1` ahora sirve `.mp4` (video/mp4).

**El video de la prueba es el REAL de Telekino** (pedido explicito del operador:
"el video debe ser el de telekino"): el fuente HQ local `inputs/TKN-2443-GANADOR-
15seg-.mp4` (1920x1080) copiado a `outputs/preview.mp4` (gitignored, viaja por
fuera de main como todos los videos). Verificado en PC: reproduce, 24 fps de
decode, 0 caidos. Queda disponible ademas el carril del workflow encode con
`preview=true` para generar, cuando se quiera, el mp4 CON EL LOOK DEL PRODUCTO
(decodificacion del .asclv 1280@15) - ese seria el insumo real del hibrido.

**Como leer el resultado en la caja:** fluido = fps de decode ~cadencia del clip,
caidos ~0, atascos ~0, deriva estable -> el hibrido es viable y pasa a diseno
formal (decision de producto: dos layers). Entrecortado o ERROR -> el WebView de
la app tiene el decode hw capado; la conversacion es con la app.

## DIAG-003: mp4 con el look del producto generado para la prueba del hibrido (2026-09-01)

Resultado de la prueba del operador con el FUENTE crudo (1920x1080 ~24fps) en la
caja: "aceptable, un poco lento; en 1:1 mucho menos" -> el carril hardware VIVE en
ese WebView (primera reproduccion aceptable en la caja hasta ahora) y la
superficie 4K vuelve a cobrar peaje incluso al video por hardware.

Siguiente escalon pedido por el operador ("probemos nuestro modelo procesado de
1280x720 @ 15 fps"): run `encode` 33532310754 (verde) con preview=true, extra
"--palette-refit 5 --near-lossless 8 --cols 1280", fps 15, format v3, SIN zopfli y
tile fijo 16 (esas perillas solo cambian bytes del .asclv, no pixeles: el mp4 tiene
los MISMOS pixeles que decidiria la receta de producto). El preview.mp4 resultante
se instalo local como `outputs/producto.mp4` (gitignored) y se verifico en PC:
1280x720 nativo, ~15 fps de decode, 0 caidos.

**Dato de peso: el mp4 del look producto pesa 4.130.240 B (4,1 MB)** contra
24.458.884 B del .asclv producto (17 %) y 38.966.462 B del fuente (10,6 %). Si el
hibrido se adopta, el transporte H.264 de nuestro look es ~6x mas chico que
nuestro formato (la intervencion seguiria viajando aparte, minima).

Pendiente: foto del HUD de la caja con `?src=./outputs/producto.mp4` (adaptado y
?view=1:1) para cerrar la evaluacion del carril mp4 con numeros.

## DIAG-003: EVALUACION DEL CARRIL MP4 COMPLETA - el producto reproduce fluido en la caja (2026-09-01)

Resultado de la prueba de `producto.mp4` (el .asclv PRODUCTO decodificado a H.264,
1280x720@15, mismos pixeles que la receta) en el WebView de la TV box, palabras del
operador: **"realmente esto mejoro muchisimo.. reproduce muy bien nuestro
producto"**. Es la PRIMERA reproduccion fluida del producto en la caja en todo el
diagnostico.

Con esto quedan cerradas las DOS preguntas de la evaluacion:
1. ¿El player 100% JS puede dar 15 fps en estas cajas? **NO** (FRAME p50 233-290 ms
   vs 66,7; medido, no supuesto; la superficie 4K es secundaria, el cuello es CPU).
2. ¿El decode de video por hardware vive dentro del WebView de la app? **SI**, y
   con NUESTRO contenido reproduce muy bien.

Cuadro final de la evidencia (todo 2026-09-01, en la misma caja, mismo WebView):

| prueba                          | resultado                                 |
|---------------------------------|-------------------------------------------|
| player JS, WebGL                | pantallazos blancos (GPU no presenta)     |
| player JS, canvas2d             | sin blancos, entrecortado (290 ms/frame)  |
| player JS, canvas2d vista 1:1   | mejora ~20%, sigue inviable (233 ms)      |
| mp4 fuente 1080p en <video>     | aceptable, algo lento (menos en 1:1)      |
| mp4 PRODUCTO 1280@15 en <video> | **reproduce muy bien**                    |

Tamanos: producto.mp4 4,1 MB / .asclv 24,5 MB / fuente 38,9 MB.

**Estado: la decision de direccion queda EN MANOS DEL OPERADOR** (sus palabras:
"puede ser que cambie la direccion del proyecto asi que documenta, guarda lo
necesario y luego tomaremos desiciones"). La opcion sobre la mesa es el HIBRIDO
(REGISTRO 2026-09-01, "alternativas discutidas"): base <video> hw con el mp4
renderizado por nuestro encoder + canvas de intervencion repintando solo la zona
intervenida. La filosofia se conserva (el encoder caro decide todo offline; el TV
solo ejecuta); cambia el transporte del video base y el invariante de un-solo-layer
pasa a dos capas. Nada se implementa hasta esa decision.

## DECISION DE DIRECCION TOMADA: paradigma mp4/hibrido - nace ASCILINE-hybrid (2026-09-01)

El operador tomo la decision que la entrada anterior dejaba pendiente. Sus
palabras: "el paradigma cambio.. necesitamos trabajar con mp4 pero logrando
mejoras de reproductividad y para eso tendremos que hacer nuevas investigaciones
y demas... no cambiaria las documentaciones pero si pasaria muchas a historicas
para que esten pero tambien poder enfocarnos en algo mejor".

**Lo decidido:**

1. **El proyecto continua en un repo nuevo: `leoIglesias-hash/ASCILINE-hybrid`**
   (privado, elegido por el operador entre cuatro nombres propuestos), clonado
   con la historia completa de `ASCILINE-video` (`main` + `assets`). El repo
   anterior queda congelado como antecesor. La rama vieja
   `feature/quality-optimization` no se migro (estancada, vive en los remotos
   del repo anterior).
2. **El transporte del video base pasa a mp4**: el `.asclv` sigue siendo el
   MASTER determinista que el encoder emite offline; lo que viaja al TV es su
   decode a H.264 (hoy `preview=true` del workflow `encode`), reproducido por
   `<video>` con decodificador de hardware. Evidencia que lo sostiene: cuadro
   final de DIAG-002/003 (entrada anterior) - JS 290 ms/frame vs "reproduce muy
   bien" del producto.mp4 de 4,1 MB.
3. **La intervencion va en un canvas encima del video** (dos capas): el
   invariante de un-solo-layer del paradigma anterior queda reemplazado por
   decision explicita del operador. La filosofia madre no cambia: el encoder
   caro decide todo offline, el TV solo ejecuta.
4. **Reorganizacion documental (H-0, pedida "ejecutarla ya")**: los disenos y
   planes del paradigma JS se movieron VERBATIM a `docs/historico/` (9 archivos,
   con README que explica que fue cada uno y en que estado se archivo);
   `RUNBOOK-IMPLEMENTACION.md` nuevo con la fase H; `RUNBOOK-ESTADO.md` con la
   proxima accion nueva; CLAUDE.md e indices reescritos. Nada se borro: el
   REGISTRO, `ejecutados/`, las referencias de clips y la bitacora siguen
   intactos y append-only.

**El plan nuevo (fase H):** H-1 diseno formal del hibrido (sincronia
intervencion-video, viaje del sidecar, distribucion CACHE-001 del mp4,
fallback) + H-2 investigacion de reproducibilidad mp4 (matriz de emision H.264
desde el master, medida en la caja con tv-video-test) en paralelo; H-3 player
hibrido minimo solo con H-1 aprobada; W-26 heredada. F10/F11/F8/DIAG-001
quedan SUSPENDIDAS, recuperables de `historico/` solo con decision del
operador. Nota dejada por escrito: si se retoma F10, sigue teniendo efecto -
el mp4 hereda los pixeles del master.

## Debate de dirección: el alcance pasa a un FORMATO PROPIO (2026-09-01)

Mismo día que la decisión anterior y que H-0, en un debate explícitamente sin
acción («trabajemos en un debate en el cual todavía no tendremos acción»), el
operador amplió el alcance del proyecto. No es un ajuste: cambia qué estamos
construyendo.

**Los problemas que planteó** (siete, textuales en lo esencial): (1) con mp4 se
pierde la intervención en vivo que el player JS hacía en un solo canvas;
(2) tampoco se puede hacer un personaje sin fondo interactuando con una capa
anterior; (3) el mp4 normalmente no queda en caché del navegador, y las wifi de
los locales fallan; (4) se abre una puerta de eficiencia inversa — antes
evitábamos pedirle trabajo al aparato, ahora hay que **exprimir** el hardware de
video, aprendiendo de sistemas que funcionan bien ahí (YouTube); (5) el paradigma
real es un WebView dentro de una app propia modificable, pero primero hay que
resolverlo en la **versión web**, apuntando a que aguante 2-3 videos sin
romperse; (6) están abiertos los paradigmas nuevos; (7) para datos vivos se puede
usar multicapa, pero al mínimo, porque los WebViews se degradan con la cantidad
de DOM.

**Y la corrección de encuadre que ordenó todo**, después de una primera ronda en
la que la discusión se había centrado en el chip de esta caja: *«te estás
centrando en el bloque de silicio del decoder de este tv box, pero en realidad
estamos basándonos en este para crear un nuevo formato compatible con todo…
seguramente lo que permite usar estos recursos mejor es la etiqueta video. por
eso te digo que nuestro propio formato de video sería ideal… algo que tenemos que
entender probando y ejecutando mejoras constantes»*. Y el cierre: *«sacar de
estos formatos cada cosa útil: **v9 la compresión, dash la compatibilidad,
asciline la base que permite todo. encoder caro no importa, decoder con poco
estrés**»*.

**Lo que quedó fijado:**

1. **Qué construimos:** un **formato de video propio, códec-agnóstico**, que se
   decide caro y offline, se reproduce **siempre por hardware** y se puede
   **intervenir en vivo sin re-codificar**. No es un player: es un paquete + un
   contrato de reproducción.
2. **`<video>` es la única puerta al hardware.** Desde una página no hay otra
   forma de tocar el decodificador; ni WebGL ni WASM ni un decoder propio (todo
   eso es CPU, y ese camino ya se midió y se descartó en DIAG-002/003). Por lo
   tanto **todo lo que emitamos termina en algo que `<video>` acepta nativo**, y
   a cambio funciona en todo lo que tenga un `<video>`.
3. **Códec-agnóstico desde el día uno.** Las piezas van etiquetadas y el aparato
   elige. H.264 Baseline es el **piso universal**, no el centro del diseño.
   Hipótesis fuerte, verificable en minutos: **si YouTube anda bien en la caja,
   esa caja tiene VP9 por hardware** (YouTube sirve VP9 en Android TV) — o sea
   que VP9 es su camino **más rodado**, no el exótico. Eso da vuelta la
   suposición con la que se venía trabajando.
4. **Composición de linajes.** De **VP9/AV1**: compresión y primitivas — golden
   frames / alt-ref (fondo estático + primer plano resuelto **dentro** del
   códec), tiles independientes (la vía limpia para intercambiar un rectángulo) y
   **alfa real en WebM** (video transparente compuesto por el navegador, sin
   canvas ni CPU: la respuesta más limpia al problema 2). De **DASH**: el
   **modelo de datos** — Periods (una intervención = un Period), AdaptationSets
   (video y audio independientes → **cambiar solo la música es cambiar de
   pista**), Representations (variantes por códec, por capacidad **o por
   contenido**), duraciones variables por segmento, direccionamiento por rango de
   bytes; adoptamos su modelo, **no su runtime**. De **HLS**: la validación de
   campo de que un video puede ser una lista de piezas, y el piso de
   compatibilidad. De **ASCILINE**: el máster determinista, la intervención
   matricial con índice transparente y la disciplina de medición — la ventaja
   competitiva real es que **controlamos los píxeles antes de que entren al
   códec**, y eso ningún encoder genérico lo tiene.
5. **Base 1280×720 con fps variable** (decisión del operador). No es estético:
   fijar la resolución es lo que vuelve **intercambiables** a las piezas
   (comparten cabecera de códec, se concatenan sin re-codificar) y evita que el
   decodificador se **reconfigure** a mitad de stream, causa clásica de tildado y
   crash en SoCs baratos. El fps, en cambio, es libre y **variable por segmento**:
   en un contenedor la duración de cada cuadro es un dato, no bitstream, así que
   se retimea sin re-codificar — y menos cuadros es menos trabajo de
   decodificación, de forma lineal. Probablemente el ahorro más grande y barato
   del sistema, y **lo puede derivar el encoder solo** (el máster ya sabe dónde
   hay movimiento).
6. **Escalera de intervención**, con su límite honesto por escrito: **N1**
   estructural (elegir piezas, orden, duración y audio — gratis, en el
   manifiesto); **N2** composición encima (sprites ASCILINE con alfa y texto en
   el canvas, cayendo en **huecos horneados por el encoder**; o video WebM con
   alfa donde exista); **N3** variantes pre-codificadas (fuerza bruta: N copias
   del mismo segmento con distinto contenido); **N4** intercambio sub-cuadro
   (tiles/slices) como **investigación de alto riesgo, no cimiento**. **N5 es
   imposible**: tocar un píxel arbitrario del video en vivo exige re-codificar, y
   re-codificar en el TV no va a pasar — todo diseño que lo necesite está mal
   planteado y se baja a N1-N3.
7. **Perfiles de dispositivo P0..P3** (piso H.264+blob → VP9 → MSE/IndexedDB/dos
   decodificadores → AV1/tiles/rVFC). **Qué perfil le toca a cada aparato sale de
   la medición, no del criterio de nadie.**
8. **Nada se normaliza sin medición.** Regla nueva del runbook (§0.8).

**Por qué el orden cambió a medir primero.** El proyecto ya se equivocó una vez
por suponer capacidades: F9 completa, medida y publicada (W-16..W-25), y en la
caja real 290 ms por cuadro contra 66,7 de presupuesto. El trabajo estaba bien
hecho; la suposición de base estaba mal. Además hay bifurcaciones que no se
resuelven escribiendo: **si un canvas encima del `<video>` le baja el fps al
video** (puede sacarlo de su plano de hardware), la intervención va **al lado** y
no encima — y eso cambia el layout de todo el producto.

**Advertencia técnica registrada para no malinterpretar mediciones futuras:**
muchos trucos clásicos para aliviar H.264 (entropía más simple, filtro de bloques
apagado) rinden **solo si el decodificador es por software**; en hardware esas
etapas son silicio y son casi gratis, y ahí lo que cuesta es ancho de banda de
memoria, cantidad de cuadros, tamaño del buffer de referencias y picos de
bitrate. Por eso «¿hardware o software?» se responde **antes** de barrer la
matriz de emisión: bifurca toda la lista de optimizaciones.

**Hallazgo lateral que vale una tarea futura:** todos los códecs submuestrean el
color (4:2:0), lo cual es veneno para arte plano con bordes duros y podría
explicar parte del escalonado que se venía persiguiendo (DIAG-001). Elegir la
paleta de modo que los colores se separen sobre todo en **luma** haría que el
submuestreo casi no dañe. Es una restricción nueva para el K-means y no la aplica
nadie más. Anotada en `DISENO-FORMATO-ASCLH.md` §11 y como eje de H-6.

**El caso «cambiar solo la música» resultó ser el más fácil del sistema**, no el
más difícil: es elegir otra Representation del AdaptationSet de audio, y en su
versión inmediata ni siquiera necesita el muxer (un `<audio>` separado usa un
decodificador distinto, no compite por la sesión de video, y cambiar de tema es
cambiar un `src`).

**Lo que NO es este proyecto**, escrito para que ninguna sesión futura lo intente:
no inventamos un códec; no escribimos un encoder desde cero (manejamos encoders
existentes **desde el máster** — nosotros decidimos keyframes, fps por segmento,
zonas estáticas, paleta y estructura); no cargamos un player DASH/HLS (tomamos su
modelo, no su runtime); no decodificamos video en JS; no hacemos crecer el player
JS anterior; no diseñamos sobre suposiciones de capacidades.

**Documentación creada** (sin código, a pedido del operador — «en vez de ya
empezar a lo loco… creá documentación que nos permita luego hacer compacts y
seguir sin perdernos la línea de trabajo»): `docs/VISION-Y-OBJETIVOS.md` (el
norte: filosofía, linajes, objetivos macro, escalera de intervención, perfiles,
invariantes, no-objetivos), `docs/DISENO-FORMATO-ASCLH.md` (el formato en obra,
con **tabla explícita de decidido vs. gateado por medición**) y
`docs/PLAN-DE-MEDICION.md` (sondas, banco, matriz de emisión y registro de
aparatos vacío). Runbooks actualizados: **H-1..H-3 quedan REEMPLAZADAS** (eran el
diseño del player híbrido, la investigación de emisión H.264 y el player mínimo;
su contenido está absorbido y ampliado) por **H-4** sonda de capacidades, **H-5**
banco de reproducción, **H-6** matriz de emisión multi-códec, **H-7** spec
normativa del formato y **H-8** muxer ES5 + player híbrido mínimo. Esos IDs no se
reusan. Próxima acción real: **H-4**.

## Corrección de método: se descarta la sonda sintética; se arranca EMITIENDO (2026-09-01)

**Sin código.** Misma fecha que el debate de alcance, unas horas después: el
operador leyó la documentación recién escrita y frenó la primera tarea.

> *«el camino de H-4 no es el correcto porque nos basaríamos solo en 1 tv box,
> mejor tomar las bondades de cada encoder para crear el nuestro y ya. Y empezar
> con el primer video aunque sea basado en suposiciones: al probarlo podremos ir
> viendo si vamos en la dirección correcta paso a paso.»*

### Por qué tiene razón

El plan anterior nacía de una lección buena (F9: se aceleró un player 100 % JS
durante toda una fase y en la caja dio 290 ms/cuadro contra 66,7 — la suposición
de base estaba mal) pero la aplicaba de una forma que llevaba al **error
simétrico**: medir **una** TV box con una sonda sintética y normalizar el formato
contra ella. Un formato que solo sirve donde se lo midió no es un formato; es un
ajuste a un aparato.

Y hay un segundo argumento, técnico: **reproducir material real responde más que
un cuestionario.** `canPlayType` devuelve `"probably"` / `"maybe"` / `""` —una
declaración, no un hecho—; un video que corre 15 segundos sin caer cuadros es el
hecho. La sonda contestaba «qué caminos existen»; reproducir contesta eso *y*
«cuánto cuesta», en el mismo gesto.

### Qué se hizo con la sonda

**No se pospuso: se disolvió dentro del primer video.** Todo lo que la sonda iba
a preguntar (códecs, alfa en WebM, `blob:`, MSE, IndexedDB, `rVFC`, panel real vs.
superficie, cuadros caídos) lo reporta ahora la página que reproduce el pack v0
(H-10) **como subproducto**, sobre material verdadero y en todos los aparatos del
operador, no en uno.

### Lo que se fijó

1. **Invariante nuevo** (`VISION-Y-OBJETIVOS.md` §8.11): **ningún aparato solo
   define el formato.** Un aparato puede **refutar** (si algo no anda ahí, no
   anda) pero no puede **consagrar**: para normalizar hace falta que gane en al
   menos **dos clases** de aparato (caja / celular / Smart TV / escritorio), o que
   lo fije el operador —cuyos valores manuales siempre prevalecen.
2. **Regla 8 del runbook reformulada:** «se supone explícito, se reproduce, y
   recién ahí se normaliza». Arrancar suponiendo **es** el método; lo prohibido es
   que una suposición entre a la spec sin haberse reproducido. Una suposición
   escrita como suposición no es deuda: es una hipótesis con refutación. Una
   suposición escrita como norma sí lo es.
3. **Documento nuevo `EMISION-V0.md`:** qué le tomamos a cada códec (las
   «bondades»: Baseline el piso con DPB mínimo; **Main como detector de hardware
   vs. software**; VP9 por compresión y por alfa real en WebM; AV1 como columna
   futura; DASH el modelo de datos; ASCILINE los píxeles antes del códec), las
   cuatro piezas del pack v0 con sus parámetros, y la tabla **S1..S6 de
   suposiciones con su refutación escrita al lado**.
4. **`PLAN-DE-MEDICION.md` reescrito:** «se mide reproduciendo, y nunca en un
   solo aparato». Su §2 ya no es un cuestionario sino la lista de lo que la
   reproducción de v0 revela; §4 (matriz) pasa a ser posterior a v0.
5. **H-4 y H-5 REEMPLAZADAS** (IDs no reusables, igual que H-1..H-3). Nuevo
   orden: **H-9** (pack v0) → **H-10** (reproducirlo en varios aparatos) →
   **H-11** (canvas encima o al lado) → **H-6** (matriz) → **H-12** (caché) →
   **H-7** (spec) → **H-8** (muxer + player).

### La apuesta que más información da

De las seis suposiciones, la que más ordena el trabajo posterior es **S2**, y por
eso el pack v0 lleva una pieza que no está para ganar: **H.264 Main**. Si Main
—que usa CABAC y transformada 8×8, caras en software y casi gratis en silicio—
pesa menos y reproduce igual o mejor que Baseline, entonces **el decodificador es
hardware** y el cuello no es el bitstream: es cantidad de cuadros y ancho de banda
de memoria. Eso invalida de un saque todo el carril «aliviar el bitstream» y
reorienta la matriz H-6 entera. Una sonda de capacidades no lo hubiera contestado.

### Hallazgo de diseño anotado al pasar

**El manifiesto de runtime no puede ser JSON.** El gate ES5 del proyecto prohíbe
`JSON` (los WebViews viejos del parque no lo garantizan), así que el manifiesto
—el de v0 y el del `.asclh` definitivo— va en **texto tabulado**, partido con
`split`. Queda como fila **decidida** en `DISENO-FORMATO-ASCLH.md` §10, no como
detalle de implementación.

Próxima acción real: **H-9**, el pack v0.

## H-9: emitido el pack v0 — el primer video del formato (2026-09-01)

Workflow `emitir-v0`, run **33559631360** (verde), desde el máster
`dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a` bajado de la
copia pineada por contenido que sirve el player en producción y **verificado por
SHA-256 antes de usarlo**. 1280×720, 15 fps, 231 cuadros (15,4 s). Runner:
2 min 22 s, RSS 487 MB.

| Pieza | Bytes | vs. Baseline | SHA-256 (12) |
|---|---:|---:|---|
| `v0-h264-baseline.mp4` | 9.551.693 | — | `97bb642a6dfc` |
| `v0-h264-main.mp4` | 8.686.512 | −9,1 % | `e1037ead463e` |
| `v0-vp9.webm` | 4.411.693 | −53,8 % | `5be4650747fd` |
| `v0-vp9-alpha.webm` | 4.664.676 | (con plano alfa) | `2b1fe6c3bfde` |

**Cómo se emitió, y por qué así.** `tools/emit_pieces.py` decodifica el máster
**una sola vez** y alimenta con el mismo cuadro a los cuatro encoders en
paralelo: así las piezas son comparables **por construcción** (misma entrada
exacta, no «aproximadamente la misma») y no se paga la decodificación cuatro
veces. Cada línea de ffmpeg es la apuesta escrita en `EMISION-V0.md` §2-§3:
Baseline con `bframes=0 ref=1 keyint=15 scenecut=0` (el DPB más chico posible),
Main con **la misma estructura** y solo CABAC + 8×8 de diferencia (si no es la
misma estructura, la comparación mide dos cosas), VP9 en calidad constante, y
VP9 con `yuva420p` + `auto-alt-ref 0` para el plano alfa. Un hilo por encoder y
muxado bit-exacto, por el invariante de determinismo.

**Lo que ya se puede leer de los bytes (fluidez todavía no: eso es H-10):**

1. **VP9 comprime a menos de la mitad** que H.264 con la misma estructura y el
   mismo material. Si el aparato lo tiene por hardware (S3), es banda regalada.
2. **El piso cuesta caro en bytes, y hay que decirlo completo.** El
   `producto.mp4` que en la caja *«reproduce muy bien»* pesa 4.130.240 B: **2,3×
   menos** que nuestro Baseline. La diferencia no es un misterio ni un fracaso —
   aquel salió con los **defaults de ffmpeg** (calidad más floja, GOP largo,
   cuadros B, varias referencias) y este lleva a propósito CRF 20, GOP cerrado de
   15, sin B y `refs=1`. **El DPB mínimo se paga en bitrate.** Cuál de los dos
   precios conviene no lo dice esta tabla: lo dice el aparato. Si S2 se refuta
   —el decodificador es hardware y la memoria no era el cuello—, esa estructura
   estricta deja de valer lo que cuesta y H-6 la afloja.
3. **Main gana 9,1 % sobre Baseline** con idéntica estructura. Ese 9,1 % es el
   precio que Baseline paga por no usar CABAC. Si además reproduce igual o mejor,
   Baseline deja de tener sentido salvo como piso de compatibilidad.

**Hallazgo operativo:** el máster tiene **231 cuadros**, no 225 — el dato sale de
la emisión, no de una estimación. Queda anotado porque cualquier cuenta de fps
variable (H-6) parte de ahí.

**Herramientas que quedaron:** `tools/emit_pieces.py` (con `--only` y `--frames`
para corridas de humo, y el stderr de cada encoder guardado en su propio log),
workflow `emitir-v0`, `tests/test_emit_pieces.py`, y `frontend/v0.html` con
`tests/test_v0_page.js`. `tools/serve-local.ps1` aprendió `.webm` y `.tsv`.

Próxima acción: **H-10** — abrir `v0.html` en la caja, el celular, el Smart TV y
el escritorio, y llenar el registro de aparatos.

## Publicado el pack v0 en `iargen.com/player/v0/` (2026-09-01, H-10)

El operador eligió publicar en vez de servirlo por LAN: es el camino por el que
la caja ya llega hoy y sirve para los cuatro aparatos sin depender del wifi de
casa. **Nada de lo ya publicado se tocó**: el prefijo `v0/` es nuevo.

**Hizo falta redesplegar el worker, y la razón importa.** El `asciline-player`
desplegado no tenía `content-type` para video —toda extensión desconocida salía
`application/octet-stream`— ni servía `Range`. Publicar así habría producido un
**falso negativo**: varios WebViews de TV miran el `content-type` antes de
decidir si pueden reproducir, y hay reproductores que directamente no arrancan un
video si el servidor no sirve rangos. O sea que el aparato podría haber
«refutado» S1/S3 por culpa del servidor, no del códec.

Dos agregados, y nada más (la rama sin `Range` quedó idéntica):

1. `mp4`, `webm` y `tsv` en la tabla de tipos.
2. `Range` → `206` con `content-range`, `416` fuera de rango, y
   `accept-ranges: bytes` también en las respuestas completas.

Procedimiento, en el orden que exige la directiva del operador («lo desplegado
tiene que estar guardado en el repo **antes** de actualizarlo»):

1. Se comprobó que el código desplegado coincidía con la copia del repo (misma
   línea `TYPES`), y se leyeron sus settings: `compatibility_date 2026-08-01`,
   bindings `BUCKET` (R2) + `UPLOAD_TOKEN` (secret).
2. Se actualizó `deploy/asciline-player/worker.js` y se commiteó (`bfa931c`).
3. Redeploy multipart con `main_module`, la binding R2 y **`keep_bindings:
   ["secret_text"]`** para no perder el secret.
4. Verificación post-deploy: la raíz sigue sirviendo el mismo `live-player.html`
   (200, 26.679 B), `playloop.js` con su `content-type` de siempre, un
   `Range: bytes=0-99` devuelve `206 · bytes 0-99/10999`, y las bindings quedaron
   en `BUCKET` + `UPLOAD_TOKEN` (**el secret sobrevivió**).
5. Token efímero acuñado, **6 keys subidas** con `x-sha256` (R2 recalcula el
   digest del cuerpo recibido), verificadas bajando cada una y comparando
   **SHA-256 contra el archivo local**: las 6 idénticas, con `video/mp4` y
   `video/webm` correctos. Token quemado; el viejo dio **403 en el primer
   intento** (a diferencia del 2026-08-31, donde tardó en propagarse).

| Key | Bytes | etag (md5) |
|---|---:|---|
| `v0/index.html` | 12.631 | `d43457add8f6855c0b86343f125675f9` |
| `v0/MANIFEST.tsv` | 923 | `301e55f5d0935b80b9519c0786dfbee3` |
| `v0/v0-h264-baseline.mp4` | 9.551.693 | `cd75c48b765f6392cfd5c837a3a28141` |
| `v0/v0-h264-main.mp4` | 8.686.512 | `52d782c1345f2466123a9ea539e37cf5` |
| `v0/v0-vp9.webm` | 4.411.693 | `0f0e6c818e88af172dcf10fb0b52d623` |
| `v0/v0-vp9-alpha.webm` | 4.664.676 | `8f8c27151e48334c3b40fc35f27faa7d` |

Ningún token se persistió, ni acá ni en el repo. Falta lo único que no podemos
hacer nosotros: **abrirlo en los aparatos**. Eso cierra H-10.

## El pack v0 suma HLS y DASH; y el determinismo del carril H.264 falla (2026-09-01)

Pregunta del operador: *«¿Y el HLS/DASH lo contemplaste?»*. La respuesta honesta
era **a medias**: DASH estaba adentro como **modelo de datos** (decidido, §2 del
diseño), pero el pack v0 eran **cuatro archivos progresivos** y lo único que la
página decía de HLS/DASH era `canPlayType` — una declaración, no un hecho, y
encima la menos confiable que hay (los WebViews de Android suelen devolver cadena
vacía para `application/vnd.apple.mpegurl` aunque la plataforma reproduzca).

**Se agregaron tres empaquetados, todos por REMUX (`-c copy`)** desde la pieza
Baseline: `hls-ts/`, `hls-fmp4/` (CMAF) y `dash/`. No recodifican nada; son los
mismos bytes de video envueltos distinto. Prueban dos cosas de una:

- **S7 — camino D:** si algún aparato reproduce HLS/DASH nativo. Donde exista,
  **el muxer ES5 de H-8 puede sobrar en ese perfil**: se emite la playlist y la
  plataforma hace la costura, sin MSE. Por eso no podía quedar para después del
  muxer. La apuesta es débil a propósito (el WebView de la caja es Android).
- **S8 — piezas intercambiables sin recodificar**, que es la afirmación central
  del formato.

El GOP de 15 cuadros a 15 fps es lo que permite cortar segmentos de 1 s
**exactamente en cuadro clave**: la estructura elegida en v0 habilita el
empaquetado.

### Resultado de la emisión (run 33566441576)

| Empaquetado | Bytes | Sobrecarga vs. la pieza progresiva |
|---|---:|---:|
| `hls-ts/` (MPEG-TS) | 9.795.953 | +2,6 % |
| `hls-fmp4/` (CMAF) | 9.555.175 | **+0,04 %** |
| `dash/` | 9.555.712 | **+0,04 %** |

**Hallazgo que vale por sí solo:** los 16 segmentos de `hls-fmp4/` y los 16 de
`dash/` son **byte-idénticos entre sí**, uno a uno (mismo md5, mismo tamaño). Un
solo juego de piezas, dos manifiestos distintos. Es la tesis del formato
comprobada sin escribir una línea de muxer.

### ⚠ El invariante 7 no se cumple en el carril H.264

La re-emisión funcionó, sin buscarlo, como prueba de determinismo:

- **VP9 y VP9+alfa: byte-idénticos** entre las dos corridas. ✔
- **Baseline y Main: NO.** 9.551.693 → 9.551.715 (+22 B) y 8.686.512 → 8.686.438
  (−74 B), con SHA-256 distintos. ✘

Verificado, no supuesto: **misma versión de ffmpeg** (6.1.1-3ubuntu5 en las dos
corridas), **línea de opciones de x264 idéntica** —`threads=1`,
`lookahead_threads=1`, `sliced_threads=0`—, y el primer byte distinto en el
**offset 605**, dentro de las tablas de muestras del `moov`: cambiaron los
tamaños de cuadro, o sea que difiere el **bitstream**, no solo el contenedor.

**Hipótesis (marcada como tal, sin comprobar):** `mbtree` de x264 usa punto
flotante y los runners no son todos el mismo CPU; distintas rutas SIMD pueden
redondear distinto y cambiar la asignación de bits. Es consistente con que VP9
—entero— sí sea determinista. Se abre **H-14** para separar «no determinista» de
«depende de la máquina»: emitir la misma pieza dos veces *dentro de la misma
corrida*, y registrar `lscpu`.

No invalida v0 (0,0002 % de diferencia, las dos son codificaciones válidas del
mismo máster), pero es deuda abierta contra un invariante y queda escrita.

### Publicación

**59 keys** bajo `v0/` (las 4 piezas, los 3 empaquetados con sus 49 segmentos,
`MANIFEST.tsv` e `index.html`), las 59 verificadas bajando y comparando SHA-256
contra el archivo local: **0 diferencias**. Token efímero quemado (403).

Hizo falta **un segundo redeploy del worker** el mismo día: `m3u8`, `mpd`, `ts` y
`m4s` salían como `application/octet-stream`. Con HLS eso es peor que con un mp4
—el tipo de la **playlist** es lo primero que mira el reproductor—, así que el
aparato podría haber refutado S7 por culpa del servidor. Copia guardada y
commiteada (`00deb9f`) antes de desplegar; verificado después: `m3u8` →
`application/vnd.apple.mpegurl`, `mpd` → `application/dash+xml`, `ts` →
`video/mp2t`, `m4s` → `video/iso.segment`, y la raíz del player intacta (200,
26.679 B). **Detalle a no re-descubrir:** la primera comprobación del `m4s` dio
`octet-stream` por caché de borde; con un parámetro anti-caché salió bien. Hay
que verificar con cache-buster después de cambiar tipos.
