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
