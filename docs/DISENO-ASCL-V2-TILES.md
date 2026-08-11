# Diseño mínimo ASCL v2: codec por tiles adaptativos

Estado: propuesta técnica para prototipo. Esta versión no reemplaza ASCL v1: el
reader nuevo debe leer ambas versiones y el procesador conserva salida v1 durante la
transición.

## 1. Objetivos y alcance

1. Reducir bytes, RAM y CPU en reproducción, aceptando mayor costo offline.
2. Mantener una única matriz lógica indexada compartida por Canvas2D y WebGL1.
3. Usar únicamente operaciones simples, Typed Arrays y DataView compatibles con un
   runtime escrito en ES5.1.
4. Permitir seek por keyframes sin reconstruir el video desde el inicio.
5. Producir la misma matriz final independientemente del presentador.

Alcance mínimo:

- solo `mode=PIXEL` (`mode=3`);
- paleta activa de 1 a 256 colores RGB;
- tile fijo de 16x16 o 32x32 por clip;
- comandos `REPEAT`, `SKIP`, `SOLID`, `SPARSE`, `PAL4`, `PAL8` y `ZLIB`;
- offsets de 32 bits y archivos menores de 4 GiB;
- `.asclv` conserva el envelope `ASCLVID1`; la versión está en el `.ascl` interior.

Los modos ASCII continúan emitiéndose como v1. Mezclar tamaños de tile dentro de un
clip, motion vectors, detección de objetos y packing de 5/6/7 bits quedan fuera del
primer prototipo.

"Adaptativo" significa que el encoder elige el comando y la calidad de cada tile. La
geometría no cambia durante el playback.

## 2. Estado de reproducción

El decoder mantiene una sola matriz persistente:

```text
cells = Uint8Array(cols * rows)
```

Cada elemento es un índice en la paleta activa. Los comandos modifican `cells` in
place. Canvas2D y WebGL1 no interpretan el codec: ambos reciben esta matriz, la paleta
y la misma lista de tiles sucios.

Buffers auxiliares permitidos:

- vista de la paleta, hasta 768 bytes;
- lista y bitset de tiles sucios;
- una banda reutilizable de presentación;
- tablas pequeñas del inflater.

No se crea otro framebuffer lógico del tamaño del video.

## 3. Header v2

Los primeros 32 bytes conservan las posiciones principales de v1. El byte `version`
determina cómo se interpreta el resto.

| Offset | Tamaño | Campo | Valor v2 |
|---:|---:|---|---|
| 0 | 4 | `magic` | `ASCL` |
| 4 | 1 | `version` | `2` |
| 5 | 1 | `mode` | `3` (`PIXEL`) |
| 6 | 1 | `flags` | flags comunes más `TILED` |
| 7 | 1 | `fps_legacy` | entero aproximado, informativo |
| 8 | 2 | `cols` | columnas, uint16 LE |
| 10 | 2 | `rows` | filas, uint16 LE |
| 12 | 2 | `pal_size_max` | 1..256 |
| 14 | 4 | `n_frames` | uint32 LE |
| 18 | 1 | `ramp_len` | `0` |
| 19 | 1 | `cell_fmt` | `1` |
| 20 | 4 | `data_off` | inicio de tabla de offsets |
| 24 | 2 | `char_aspect_x1000` | `1000` |
| 26 | 2 | `reserved` | `0` |
| 28 | 4 | `crc32` | CRC desde byte 32 hasta EOF |
| 32 | 2 | `header_size` | `48` inicialmente |
| 34 | 2 | `fps_num` | numerador exacto |
| 36 | 2 | `fps_den` | denominador exacto, mayor que 0 |
| 38 | 1 | `tile_size` | `16` o `32` |
| 39 | 1 | `codec_flags` | reservado, `0` |
| 40 | 4 | `keymap_off` | offset absoluto al keymap |
| 44 | 4 | `frames_off` | offset absoluto al primer frame |

El reloj usa `fps_num / fps_den`; `fps_legacy` no interviene en el cálculo v2.

Bits de `flags`:

| Bit | Nombre | Uso v2 |
|---:|---|---|
| 0 | `LOSSY` | el encoder aceptó pérdida temporal/perceptual |
| 1 | `PAL_PER_SCENE` | pista informativa de estrategia de paleta |
| 2 | `PAL_GLOBAL` | misma paleta lógica durante todo el clip |
| 3 | `HAS_OFFSET_TABLE` | siempre `1` |
| 4 | `RECON_SOFT` | recomendación de reconstrucción |
| 5 | `TILED` | siempre `1` en esta v2 |
| 6 | `HAS_KEYMAP` | siempre `1` |
| 7 | reservado | `0` |

`PAL_GLOBAL` no impide reemitir la misma paleta en cada keyframe: describe su
identidad lógica, no cuántas veces aparecen sus bytes.

Layout posterior:

```text
HEADER             header_size bytes
OFFSET TABLE       n_frames * uint32 LE
KEYFRAME MAP       ceil(n_frames / 8) bytes, LSB-first
PADDING             ceros hasta múltiplo de 4
FRAME BLOCKS
```

Los offsets son absolutos desde el byte cero del `.ascl`, no desde el `.asclv`. El
reader consulta la tabla directamente con `DataView`; no crea un `Array` JS por frame.

El límite de 32 bits se conserva deliberadamente: un webview antiguo no puede cargar
de forma fiable un ArrayBuffer cercano a 4 GiB. Superarlo requerirá segmentación en una
versión posterior, no enteros de 64 bits en el runtime legacy.

## 4. Tiles

```text
tile_cols  = ceil(cols / tile_size)
tile_rows  = ceil(rows / tile_size)
tile_count = tile_cols * tile_rows
```

Se exige `tile_count <= 65535`. Los tiles se numeran row-major. Un tile de borde usa
solo su ancho y alto reales; no almacena celdas fuera de la imagen.

El encoder prueba 16 y 32 offline y selecciona uno para todo el clip:

- 16: mejor granularidad para cambios pequeños y menor costo de `SPARSE`;
- 32: menos comandos y menos llamadas de presentación en movimiento amplio.

## 5. Frame block

```text
uint32 LE  block_len       bytes posteriores a este campo
uint8      frame_flags     bit 0 = KEYFRAME
uint16 LE  pal_count
uint8      palette[pal_count * 3]
uint8      commands[...]   hasta el final de block_len
```

El bit `KEYFRAME` debe coincidir con el keymap.

Reglas de paleta y seek:

- frame 0 siempre es keyframe;
- cada keyframe incluye la paleta activa completa;
- cambiar la paleta obliga a emitir un keyframe;
- un delta tiene `pal_count=0`;
- una paleta global puede reemitirse en cada keyframe para mantener seek autónomo;
- `REPEAT` nunca es keyframe;
- `ZLIB` siempre es keyframe.

Una paleta por frame es válida, pero convierte cada frame en keyframe y normalmente
aumenta bytes y trabajo de presentación. El default recomendado es una paleta por
bloque o escena con duración mínima e histéresis.

## 6. Stream de comandos

El cursor de tile comienza en cero. No hay comando `END`: el límite del frame termina
el stream.

| Opcode | Nombre | Payload | Acción |
|---:|---|---|---|
| `0x00` | `REPEAT` | ninguno | Reusa matriz y paleta; debe ser el único comando. |
| `0x01` | `SKIP` | `uint16 run` | Avanza `run` tiles sin modificarlos. |
| `0x02` | `SOLID` | `uint16 run`, `uint8 color` | Rellena tiles consecutivos con un índice. |
| `0x03` | `SPARSE` | `uint16 count`, entradas | Cambia pocas celdas del tile actual. |
| `0x04` | `PAL4` | mapa local y nibbles | Sobrescribe un tile completo. |
| `0x05` | `PAL8` | índices de 8 bits | Sobrescribe un tile completo. |
| `0x06` | `ZLIB` | zlib hasta fin del bloque | Sobrescribe el frame completo. |

Todos los enteros multi-byte son little-endian. `run` debe ser mayor que cero y no
puede avanzar más allá de `tile_count`.

### 6.1 REPEAT y SKIP

`REPEAT` representa un frame completo sin cambios y deja el dirty set vacío. Un frame
delta puede omitir un `SKIP` final: los tiles desde el cursor hasta el final permanecen
sin cambios.

### 6.2 SOLID

`SOLID` escribe el mismo índice global en todas las celdas reales de uno o más tiles
consecutivos. El índice debe ser menor que `pal_count` de la paleta activa.

### 6.3 SPARSE

`SPARSE` solo es válido en frames delta. Cada entrada contiene posición local y color:

```text
tile 16: uint8  position, uint8 color
tile 32: uint16 position, uint8 color

position = local_y * tile_size + local_x
```

Las posiciones son estrictamente crecientes y deben pertenecer al área real del tile
de borde. Después de aplicar las entradas, el cursor avanza un tile.

### 6.4 PAL4

```text
uint8 map_count
uint8 map[map_count]
uint8 packed[ceil(pixel_count / 2)]
```

- `map_count=1..16`: cada nibble indexa `map`; `map` contiene índices globales.
- `map_count=0`: los nibbles son índices globales directos 0..15.
- el nibble bajo representa la primera celda;
- si `pixel_count` es impar, el nibble alto final es cero.

Las celdas se recorren row-major dentro del ancho y alto reales del tile. El cursor
avanza un tile.

### 6.5 PAL8

Contiene `pixel_count` índices globales, un byte por celda real, en row-major. El
cursor avanza un tile.

### 6.6 ZLIB

`ZLIB` debe ser el único comando de un keyframe. Los bytes restantes del frame son un
stream zlib cuyo resultado exacto es `cols * rows` índices row-major.

No se usa ZLIB por tile: inicializar cientos de inflaters por frame sería perjudicial
en Smart TVs. El inflater v2 debe escribir directamente en `cells` y validar la
longitud esperada, sin crear otro framebuffer.

### 6.7 Cobertura de frame

Un keyframe por tiles:

- solo usa `SOLID`, `PAL4` y `PAL8`;
- no usa `SKIP` ni `SPARSE`;
- termina con `cursor == tile_count`.

Un delta puede combinar todos los comandos salvo `ZLIB`, y los tiles no cubiertos se
conservan. Un stream vacío es inválido; el encoder canónico usa `REPEAT`.

## 7. Selección offline de comandos

Orden inicial por tile/frame:

1. frame idéntico: `REPEAT`;
2. tiles idénticos: `SKIP`;
3. tiles uniformes: `SOLID`;
4. pocos cambios: `SPARSE`;
5. hasta 16 colores locales: `PAL4`;
6. resto: `PAL8`;
7. comparar el stream completo contra un keyframe `ZLIB`.

El objetivo no puede ser solo el menor archivo. El encoder debe considerar trabajo de
reproducción:

```text
REPEAT / SKIP      casi cero
SPARSE             count escrituras
SOLID / PAL8       pixel_count escrituras
PAL4               pixel_count escrituras + desempaquetado
ZLIB               cols*rows escrituras + inflate
```

En el perfil legacy, `ZLIB` solo compite si reduce al menos 15-20% frente al stream por
tiles y cumple el presupuesto p95 medido. Un perfil opcional `smallest` puede ponderar
más los bytes.

La calidad adaptativa no necesita nuevos comandos. El encoder puede probar, por tile:

- resolución completa;
- reducción y reexpansión horneada;
- menor paleta local;
- dithering estable o sin dithering;
- retención temporal bajo un umbral perceptual.

Cada candidato termina en la misma matriz final. Se elige por distorsión, bytes reales
y costo estimado de decode. El dithering debe estar anclado a coordenadas absolutas y
solo conservarse si su mejora visual justifica los cambios temporales adicionales.

## 8. Dirty tiles comunes

El reader reserva una sola vez:

```text
dirty_ids   Uint16Array(tile_count)
dirty_bits  Uint8Array(ceil(tile_count / 8))
dirty_count
dirty_full
```

Semántica:

- `REPEAT` y `SKIP`: no ensucian;
- `SOLID`, `SPARSE`, `PAL4` y `PAL8`: ensucian los tiles afectados;
- keyframe y `ZLIB`: `dirty_full=true`;
- si el audio obliga a saltar varios frames, se guarda la unión de todos los tiles
  modificados, no solo los del último frame.

Al finalizar `seek`, el bitset se recorre para producir IDs ordenados y sin duplicados.
Los IDs se agrupan en corridas horizontales; Canvas2D y WebGL1 consumen exactamente las
mismas corridas.

Para v1, el adapter puede usar tiles lógicos de 16x16: RAW/ZLIB producen `dirty_full` y
DELTA/DELTA_MASK marcan los tiles tocados.

## 9. Presentación Canvas2D y WebGL1

Canvas2D:

- conserva solo el backing store nativo del canvas;
- usa un `ImageData` reutilizable de `cols * tile_size` píxeles;
- convierte índices a RGBA únicamente en corridas sucias;
- actualiza por corrida o banda mediante `putImageData`.

WebGL1:

- mantiene una textura de índices de un byte y una textura de paleta;
- actualiza las mismas corridas con `texSubImage2D`;
- usa una banda staging reutilizable cuando el subrectángulo no es contiguo;
- no interpreta comandos ni mantiene otro estado de video.

Ejemplo 1920x1080 con tiles de 16:

| Estado JS | Tamaño aproximado |
|---|---:|
| matriz de índices | 2,0 MiB |
| dirty IDs | 16 KiB |
| dirty bitset | 1 KiB |
| banda Canvas RGBA | 120 KiB |
| banda WebGL | 30 KiB |

El backing store Canvas y la textura WebGL son recursos de presentación inevitables,
no segundos framebuffers lógicos.

No debe aplicarse `LINEAR` directamente a una textura de índices: interpolaría números
de paleta en vez de colores. El camino normalizado inicial usa suavizado horneado
offline y presentación `NEAREST`. Un modo soft en runtime requeriría interpolar colores
después del lookup y demostrar equivalencia suficiente con Canvas.

## 10. Reader dual y límites ES5

Despacho obligatorio:

```text
magic inválido  -> error
version 1       -> ReaderV1
version 2       -> ReaderV2
otra versión    -> error explícito
```

Interfaz común:

```text
header
cells
palette
seek(frame_index)
dirty_full
dirty_count
dirty_tiles
tile_size
```

El runtime distribuido usa sintaxis ES5.1 y no depende de:

- `Promise`, `fetch`, módulos o `async/await`;
- Worker, WASM, WebGL2, OffscreenCanvas o Streams;
- `Map`, `Set`, `BigInt` o `TypedArray.slice`.

Sí requiere `ArrayBuffer`, Typed Arrays, `DataView`, XHR binario y Canvas2D. WebGL1 es
opcional. El reader usa `subarray` y vistas directas para no copiar el `.ascl` interior
del bundle.

Al buscar un frame objetivo:

1. localizar el keyframe anterior con el keymap;
2. si el estado actual válido está más cerca, avanzar desde él;
3. si hay un keyframe posterior al estado actual y anterior al objetivo, saltar directo
   a ese keyframe;
4. acumular dirty tiles de toda la cadena aplicada.

## 11. Riesgos

- Una paleta por frame elimina casi todas las ventajas temporales y fuerza redraw
  completo.
- Tiles de 16 reducen overdraw pero agregan comandos; tiles de 32 hacen lo contrario.
- Dithering temporalmente inestable puede destruir `SKIP` y `SPARSE`.
- ZLIB por tile aumenta mucho la CPU; queda prohibido en la v2 mínima.
- La escritura directa en `cells` puede dejar estado parcial ante un archivo corrupto;
  se mitiga con CRC, validación de límites y recuperación en el siguiente keyframe.
- El dirty set debe unir todos los frames omitidos por sincronización de audio.
- El player v1 existente no entiende v2. El frontend actualizado sí debe seguir leyendo
  todos los fixtures v1 y el procesador conserva `--format v1|v2` durante la transición.
- Los offsets y longitudes del envelope siguen limitados a 32 bits.

## 12. Pruebas de aceptación

Fixtures mínimos:

- dimensiones exactas y bordes: 16x16, 17x17, 31x33 y 1920x1080;
- un fixture por comando y combinaciones de comandos;
- `PAL4` directo, con mapa, cantidad impar y tile recortado;
- keyframes por tiles y por ZLIB;
- cambio de paleta en keyframe;
- secuencias largas de `REPEAT` y `SKIP`;
- seek hacia adelante, atrás y con frames descartados;
- payloads truncados, índices inválidos, cursor excedido y keymap inconsistente.

Validaciones:

- CRC de `cells` idéntico al decoder Python en cada frame;
- matriz idéntica antes de presentar por Canvas2D y WebGL1;
- unión correcta de dirty tiles al saltar frames;
- apertura de todos los fixtures v1 existentes;
- cero asignaciones por frame durante reproducción estable;
- RAM pico, bytes, decode p50/p95, render p50/p95 y frames descartados medidos por
  resolución y tipo de movimiento.

## 13. Orden de prototipo

1. Congelar layout, opcodes y fixtures binarios dorados.
2. Agregar gate de versiones y conservar regresión completa de ReaderV1.
3. Implementar v2 PIXEL, tile 16, keyframes `SOLID`/`PAL8`.
4. Agregar `REPEAT`, `SKIP`, `SPARSE`, keymap, seek y dirty union.
5. Presentar corridas comunes en Canvas2D y WebGL1.
6. Agregar `PAL4`.
7. Agregar tile 32 y elección offline 16 vs 32.
8. Agregar paletas por bloque/escena y adaptación de calidad offline.
9. Rehacer inflate con salida tipada directa a `cells`; recién entonces activar ZLIB.
10. Evaluar con benchmarks si packing de 5/6/7 bits merece ampliar el formato.

Cada etapa avanza solo si conserva compatibilidad v1, seek correcto, igualdad de la
matriz común y el presupuesto de memoria/CPU del perfil legacy.
