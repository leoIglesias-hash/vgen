# ASCL v2 por tiles — primera revisión implementada

Fecha de revisión: 2026-08-14.

Estado: codec, transcodificador de referencia, ReaderV2 y despacho v1/v2 implementados.
Esta es una primera revisión utilizable y verificable; no es todavía una recomendación
de reemplazar v1 en todos los Smart TV. La promoción depende del benchmark HQ final y de
pruebas físicas.

La especificación normativa resumida también vive en `ASCL-format-spec.md`, §13. Este
documento explica las decisiones de implementación, los límites y lo que queda fuera.

## 1. Objetivo e invariantes

V2 mejora la representación binaria de una matriz ASCL ya aprobada. No vuelve a analizar
el video fuente, no usa IA, no estima calidad visual y no modifica colores para ganar
bytes. La primera revisión exige:

- `mode=PIXEL`, una entrada de paleta por celda;
- misma matriz de índices decodificada que v1 en cada frame;
- mismas emisiones de paleta RGB, FPS, dimensiones, keyframes y audio;
- Canvas2D y WebGL1 alimentados por el mismo ReaderV2;
- frontend con sintaxis ES5, apta para el piso ECMAScript 2015 requerido;
- un solo `.asclv`, descargado completo y cacheable;
- v1 como fallback binario por frame y como formato CLI predeterminado.

No existe un selector perceptual en este paso. El encoder elige entre formas lossless
materializadas comparando su longitud real.

## 2. Envelope ASCLVID2

El envelope no se rediseñó: conserva exactamente 16 bytes de cabecera y los dos cuerpos
contiguos.

```text
offset  size  campo
0       8     magic ASCII = "ASCLVID2"
8       4     ascl_len uint32 LE
12      4     audio_len uint32 LE
16      ...   ASCL v2 interior
...     ...   audio exacto (MP3 actual), opcional
```

El tamaño total debe ser `16 + ascl_len + audio_len`, sin truncado ni trailing bytes.
`ASCLVID2` debe contener inner `version=2`; `ASCLVID1`, inner `version=1`. El audio se
copia byte a byte al transcodificar.

No hay directorio `VIDO/AUDI`, GOP separado, chunks ni metadatos de streaming en esta
revisión. Eso evita ampliar el parser y mantiene la misma forma de caché que v1.

## 3. Header interior v2

Se conserva el header ASCL fijo de 32 bytes y la tabla de offsets `uint32 LE`.

```text
byte 0..3   "ASCL"
byte 4      version = 2
byte 5      mode = 3 (PIXEL)
byte 26     tile_size = 16
byte 27     codec_flags = 0x01 (regional habilitado)
byte 28..31 crc32 v2 uint32 LE
```

Los restantes campos mantienen el layout v1. Interpretado como el antiguo `reserved`
uint16 LE, bytes 26/27 forman `0x0110`.

### CRC v2

El CRC IEEE es obligatorio y cubre:

```text
header[0..27] ++ body[32..EOF]
```

Los cuatro bytes del propio CRC quedan excluidos. A diferencia de v1, la verificación
protege versión, modo, flags, FPS, dimensiones, paleta declarada, tabla y bloques.

## 4. Frame block y tags

El bloque conserva la estructura v1, por lo que no agrega overhead por frame:

```text
uint32 LE  block_len
uint8      tag
uint16 LE  pal_count
uint8      palette[pal_count * 3]
uint8      payload[block_len - 3 - pal_count*3]
```

Tags implementados:

| Tag | Nombre | Tipo |
|---:|---|---|
| 0 | `RAW` | key v1 conservado |
| 1 | `ZLIB` | key v1 conservado |
| 2 | `DELTA` | delta v1 conservado |
| 3 | `DELTA_MASK` | delta v1 conservado |
| 4 | `REGIONAL_KEY_RAW` | key regional crudo |
| 5 | `REGIONAL_KEY_ZLIB` | key regional zlib |
| 6 | `REGIONAL_DELTA_RAW` | delta regional crudo |
| 7 | `REGIONAL_DELTA_ZLIB` | delta regional zlib |
| 8 | `PREDICT_KEY_ZLIB` | key predictor reversible |
| 9 | `PREDICT_DELTA_ZLIB` | delta predictor reversible |

Los tags key son `{0,1,4,5,8}` y los delta `{2,3,6,7,9}`. Un delta no puede emitir
paleta. Un key de paleta temporal/per-frame debe ser autónomo. Mantener 0..3 dentro de v2
es una decisión central: si una idea v2 no gana, el frame usa sus bytes v1 originales.

## 5. Geometría de tiles

La primera revisión fija `tile_size=16`. La grilla se calcula sin padding materializado:

```text
tile_cols  = ceil(cols / 16)
tile_rows  = ceil(rows / 16)
tile_count = tile_cols * tile_rows
```

Los tiles del borde tienen ancho/alto menor derivado de la imagen. El cursor avanza
row-major y es implícito: excepto `SKIP_RUN`, cada opcode consume exactamente un tile.
El stream debe cubrir `tile_count` y terminar en ese punto exacto.

## 6. Stream regional implementado

Todos los `uvarint` son LEB128 uint32 canónicos, de uno a cinco bytes. Las máscaras y
códigos packed se escriben LSB-first y exigen padding cero. Los mapas locales son índices
de la paleta RGB activa, estrictamente crecientes y sin duplicados.

### 6.1 `0x00 SKIP_RUN`

```text
opcode:u8 ++ run:uvarint
```

Solo delta. Reutiliza `run>=1` tiles consecutivos de la matriz anterior. Es el único
comando con corrida. No existe opcode `REPEAT`: una matriz completa repetida se representa
con `SKIP_RUN(tile_count)`. Tampoco existe un `SKIP` unitario separado.

### 6.2 `0x01 SOLID`

```text
opcode:u8 ++ color_idx:u8
```

Llena un solo tile. El nombre normativo es `SOLID`, no `SOLID_RUN`; no lleva contador.

### 6.3 `0x02 SPARSE`

```text
opcode:u8 ++ k:uvarint ++ (offset:uvarint ++ value:u8)[k]
```

Solo delta. `k` está entre 1 y `npix`. Cada offset es absoluto dentro del tile row-major,
estrictamente creciente y menor que `npix`. Cada valor debe diferir de la matriz previa;
escrituras nulas se rechazan.

### 6.4 `0x03 MASK`

```text
opcode:u8 ++ mask[ceil(npix/8)] ++ values[popcount(mask)]
```

Solo delta. Bit `i` selecciona celda local `i`; los valores siguen el orden de los bits.
La máscara no puede estar vacía y tampoco admite escrituras idénticas al estado previo.

### 6.5 `0x04 PACK1`

```text
opcode:u8 ++ map[2] ++ codes[ceil(npix/8)]
```

Exactamente dos índices locales, un bit por celda.

### 6.6 `0x05 PACK2`

```text
opcode:u8 ++ count:u8 ++ map[count] ++ codes[ceil(npix/4)]
```

`count=3..4`, dos bits por celda.

### 6.7 `0x06 PAL4`

```text
opcode:u8 ++ count:u8 ++ map[count] ++ codes[ceil(npix/2)]
```

`count=5..16`, cuatro bits por celda. Documentos previos usaban `PACK4` y `PAL4` para
la misma idea. El opcode implementado y nombre normativo es **`PAL4`**; no son dos
candidatos distintos.

### 6.8 `0x07 PAL8`

```text
opcode:u8 ++ values[npix]
```

Un índice de la paleta global activa por celda, row-major. No incluye mapa local.

### 6.9 RAW frente a ZLIB

Primero se construye el stream completo. Los tags 4/6 guardan ese stream crudo; 5/7
guardan `zlib(stream)`. ZLIB se elige solo si es estrictamente menor. No existe zlib por
tile ni longitud RAW prefijada; el reader usa dimensiones y un bound defensivo.

## 7. Selección offline determinista

En cada tile cambiado se materializan todos los candidatos exactos aplicables. Gana el
menor por bytes; los empates siguen este orden:

```text
SOLID, SPARSE, MASK, PACK1, PACK2, PAL4, PAL8
```

En un key solo participan formas densas. En un delta, un tile idéntico se acumula en
`SKIP_RUN`; uno cambiado también puede usar `SPARSE`/`MASK`.

Por frame, el transcodificador compara:

1. tag/payload v1 original;
2. mejor stream regional RAW/ZLIB;
3. mejor predictor reversible.

Un candidato nuevo solo reemplaza al vigente con una longitud estrictamente menor. Los
demás bytes del bloque se conservan, de modo que el ASCL v2 nunca crece frente al ASCL v1
de entrada. Esta es una garantía estructural, no un promedio de corpus.

## 8. Predictores exactos

Los tags 8/9 guardan:

```text
predictor_id:u8 ++ zlib(residual de N bytes)
```

IDs key:

- `0 LEFT`: diferencia modular contra la izquierda, cero en borde;
- `1 TOP`: diferencia modular contra arriba, cero en borde;
- `2 GRADIENT`: predictor `left + top - top_left` módulo 256.

IDs delta:

- `3 PREVIOUS_SUB`: `actual - previous` módulo 256;
- `4 PREVIOUS_XOR`: `actual XOR previous`.

Se prueba cada predictor permitido, gana el menor payload y el ID menor desempata. Son
transformadas de bytes reversibles; no alteran paleta, índices ni RGB.

## 9. ReaderV2 y dirty híbrido

`reader-factory.js` despacha por el byte de versión:

```text
1 -> ReaderV1
2 -> ReaderV2
otro -> error
```

`ReaderV2` usa sintaxis ES5 y mantiene el contrato de los renderers. Su estado dirty es
la unión disjunta de:

- bits de celdas exactas para `SPARSE`, `MASK`, DELTA y DELTA_MASK;
- bits/lista de tiles para comandos densos regionales;
- `dirtyFull` para keyframes y cambios de paleta.

Si un tile denso solapa celdas exactas, el tile las reemplaza en la unión. `seek()` acumula
los cambios de todos los frames decodificados hasta el objetivo. Canvas2D y WebGL1 llaman
la misma `fillRGBAChanged`; no hay una semántica de imagen distinta por renderer.

## 10. Validación, scratch y seguridad

El reader verifica CRC, campos de header, offsets contiguos, longitudes exactas, paletas,
tags, bounds de inflate, LEB128 canónico, cobertura, padding e índices. El regional se
recorre una vez sin aplicar y otra vez para escribir; un payload inválido no deja un tile
parcialmente mutado. Los predictores también validan todos los valores antes de consolidar
el frame.

Inventario proporcional persistente/reutilizable:

- vista del archivo completo descargado;
- `cells` de `N` bytes;
- scratch tipado que crece bajo bound y luego se reutiliza;
- dirty bits por celda/tile y lista `uint16` de tiles;
- RGBA persistente del renderer.

Por ello el gate correcto no es “cero memoria proporcional”. Es **cero asignaciones nuevas
de un frame completo en el loop estable**, después de dimensionar el scratch necesario.
La revisión impone 64 MiB a cada bound operativo validado de matriz/inflate y hasta 65.535
tiles para IDs `uint16`; 64 MiB no es un límite de RAM total del player.

## 11. CLI e integración

`make_clip.py` expone:

```text
--format v1|v2
```

El default es `v1`. Con `v2`, el procesador crea primero la matriz v1 aprobada en un
temporal distinto, la transcodifica lossless y empaqueta `ASCLVID2`. Nunca sobrescribe la
fuente v1. También puede usarse `backend/ascl_v2.py input.asclv output.asclv` para convertir
un bundle v1 existente y copiar su audio exacto.

Los players cargan `inflate.js`, `reader.js`, `reader-v2.js` y `reader-factory.js`; aceptan
ambos magic de bundle. La descarga sigue siendo completa por XHR. No requiere Worker,
WASM, WebGL2, Service Worker, Streams ni MediaSource.

## 12. Pruebas de aceptación de esta revisión

Pruebas automáticas requeridas:

- roundtrip Python exacto de todos los opcodes y predictores;
- dimensiones no divisibles por 16;
- igualdad de matrices/paletas/keyframes v1-v2;
- garantía `bytes(v2) <= bytes(v1)` también en entrada incompresible;
- rechazo transaccional de truncado, trailing, overflow, padding, índices y zlib inválidos;
- igualdad Python/ReaderV2 y seek hacia adelante/atrás;
- factory y players duales sin regresión v1;
- envelope `ASCLVID1/2`, longitud exacta y versión interior concordante.

La aceptación de producto agrega Smart TV físico: p50/p95, cuadros perdidos, RAM, CPU,
Canvas2D y WebGL1. Un resultado de PC/Node no sustituye ese gate.

## 13. Pendientes, sin confundirlos con lo implementado

1. **Artefacto HQ final:** **COMPLETADO localmente**. El ASCLVID2 final pesa
   17.935.305 B, ahorra 5 B, conserva RGBA en 231/231 frames y audio byte-exacto; SHA-256
   `6FF3E71E3B090B4546C265AA60D22C65CF9382E0B207D6DCCB29AEFFF713573A`.
2. **Remap exacto de paleta:** el laboratorio permutó conjuntamente IDs y entradas RGB:
   conservó RGB byte-exacto en 231/231 frames y estimó 17.935.310 -> 17.763.683 B
   (-171.627 B; -0,9569%), pero introdujo 94 tags predictores y tardó 414,4 s offline.
   No está implementado ni es default; queda bajo evaluación física por posible costo CPU.
3. **Validación física TV:** decidir si v2 se promueve o queda como perfil especializado.
4. **Intervención matricial:** slots rectangulares dentro de la misma matriz/canvas.
5. **Near-lossless:** opcional y explícito, separado de este transcode exacto.
6. **Range/streaming/chunks:** solo con evidencia de RAM/arranque; hoy se conserva descarga
   completa y caché de un recurso.
7. **Otros tiles/opcodes:** 8/32, diccionario, hold o patch de paleta necesitan otra
   revisión y sus propios gates de compatibilidad/costo.

## 14. Criterio de promoción

V2 puede promoverse cuando:

- la igualdad exacta v1/v2 esté demostrada sobre el artefacto final (**cumplido local**);
- el tamaño no crezca y la ganancia justifique el decoder adicional;
- Canvas2D y WebGL1 mantengan calidad, reloj y estabilidad;
- RAM pico y cuadros perdidos no empeoren en los dispositivos objetivo;
- v1 siga siendo una salida seleccionable y reproducible.

Hasta entonces, `--format v1` continúa siendo el default conservador.
