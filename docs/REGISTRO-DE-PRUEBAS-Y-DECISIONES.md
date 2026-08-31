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
