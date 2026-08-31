# Especificación del formato `.ascl` / `.asclv` — v1, v2 y revisión v3

> Contenedor binario compacto para reproducir ASCILINE como **VOD pre-encodeado**.
> El encoder (offline) hace todo el cómputo una vez; el reader (cliente, ES2015-safe)
> solo parsea bytes y dibuja. El servidor sirve un **archivo estático** → ≈0 cómputo en playtime.
>
> Estado: v1 permanece estable e implementado. La primera revisión v2 está
> implementada para `mode=PIXEL`: conserva los cuatro tags v1 como fallback y agrega
> representación regional por tiles y predictores reversibles. V2 no vuelve a cuantizar
> ni cambia la imagen RGB aprobada.

---

## 0. Decisiones que fija esta versión

| Decisión | Valor v1 | Dónde vive |
|---|---|---|
| **D1** Resolución | **variable** (`cols`/`rows` en header), objetivo 1080p | header |
| **D2** Render | el `.ascl` es agnóstico al renderer; sirve a Canvas2D `fillText`, glyph-atlas e instancing WebGL | reader elige en runtime |
| **D3** Paleta | 1..256 colores; global, bloque/adaptativa o per-frame. `encoder.py` directo conserva per-frame y `make_clip.py` usa global como defaults de interfaz | header `flags` + `pal_count` por frame |
| **D9** Procedencia | relación conceptual declarada con `YusufB5/ASCILINE`; implementación standalone de rampa, delta y selección por bytes | auditoría/licencia pendientes antes de publicación pública |
| FPS | **configurable**, default 15 (20/25/30 válidos) | header `fps` |
| Peso | **1 byte/celda** vía índice de paleta | plano de índices |
| Compresión | el encoder elige `zlib` (DEFLATE) o RAW por frame; transporte HTTP `identity` por defecto (ver §6) | tag por frame |

**Endianness:** todos los enteros multi-byte son **little-endian (LE)**. En el reader se
leen con `DataView.getUint16(off, true)` / `getUint32(off, true)`.

---

## 1. Layout general del contenedor

```
┌──────────────────────────────────────────────────────────────────┐
│  HEADER            32 bytes              (magic, modo, cols/rows…)  │
├──────────────────────────────────────────────────────────────────┤
│  CHAR RAMP         ramp_len bytes        (solo modos ASCII)         │
│                    p.ej. " .:-=+*#%@"    dark → light               │
├──────────────────────────────────────────────────────────────────┤
│  OFFSET TABLE      n_frames × 4 bytes    (offset absoluto a c/frame)│
├──────────────────────────────────────────────────────────────────┤
│  FRAME #0          block_len + tag + [paleta] + planos             │
│  FRAME #1          …                                                │
│  …                                                                  │
│  FRAME #(n-1)                                                       │
└──────────────────────────────────────────────────────────────────┘
       (el audio no forma parte del .ascl interior; el .asclv lo adjunta — ver §7)
```

Imagen fija = exactamente lo mismo con `n_frames = 1`: header + (ramp si ASCII) +
1 offset + 1 frame.

---

## 2. HEADER (32 bytes, fijo)

| Offset | Tamaño | Tipo | Campo | Descripción |
|---:|---:|---|---|---|
| 0  | 4 | char[4] | `magic`   | `"ASCL"` = `0x41 0x53 0x43 0x4C`. Si no coincide → no es `.ascl`. |
| 4  | 1 | uint8   | `version` | `1`, `2` o `3`. V2/V3 solo admiten `mode=PIXEL`; v3 = v2 + SPARSE diferencial (§14). |
| 5  | 1 | uint8   | `mode`    | `0`=ASCII_BW, `1`=ASCII_PAL, `2`=ASCII_RGB, `3`=PIXEL. Ver §3. |
| 6  | 1 | uint8   | `flags`   | bitfield. Ver §2.1. |
| 7  | 1 | uint8   | `fps`     | Cuadros/seg para playback (default 15). `frame = floor(audio.currentTime × fps)`. Para imagen es informativo. |
| 8  | 2 | uint16  | `cols`    | Columnas de la grilla (ancho en celdas). |
| 10 | 2 | uint16  | `rows`    | Filas de la grilla (alto en celdas). |
| 12 | 2 | uint16  | `pal_size`| Nº máximo de entradas de paleta (256 típico; `0` si el modo no usa paleta: BW/RGB). |
| 14 | 4 | uint32  | `n_frames`| Cantidad de frames. **Imagen = 1.** |
| 18 | 1 | uint8   | `ramp_len`| Longitud de la rampa de caracteres en bytes (`0` en PIXEL). |
| 19 | 1 | uint8   | `cell_fmt`| Informativo: nº de planos por celda. `1`=char, `2`=char+colorIdx, `3`=índice pixel/RGB. Ver §3. |
| 20 | 4 | uint32  | `data_off`| Offset absoluto donde empieza la **OFFSET TABLE** (= `32 + ramp_len`). El reader salta acá sin recalcular. |
| 24 | 2 | uint16  | `char_aspect_x1000` | Factor de aspecto usado al encodear × 1000 (p.ej. `500` = 0.5). Informativo para el reader; el mapeo ya está hecho. |
| 26 | 2 | uint16  | `reserved` / codec v2 | V1: `0`. V2: byte 26 `tile_size=16`; byte 27 `codec_flags=0x01` (regional habilitado), equivalente LE a `0x0110`. |
| 28 | 4 | uint32  | `crc32`   | V1: CRC32 IEEE de bytes `32..EOF`; `0` permite omitirlo. V2: obligatorio, sobre bytes `0..27` seguidos de `32..EOF`, excluyendo el propio campo. |

Total: **32 bytes**.

### 2.1 `flags` (bitfield)

| Bit | Nombre | Significado |
|---:|---|---|
| 0 | `LOSSY` | Hubo delta temporal con pérdida (tolerancia > 0). El plano de carácter siempre es exacto. |
| 1 | `PAL_PER_SCENE` | Paleta temporal: se reemite en cambios de escena o bloque y en todo keyframe (frames con `pal_count > 0`). |
| 2 | `PAL_GLOBAL` | Una sola paleta para todo el clip (solo el frame 0 trae `pal_count > 0`). |
| 3 | `HAS_OFFSET_TABLE` | Hay tabla de offsets (siempre `1` en v1 y en la revisión v2 actual). |
| 4 | `RECON_SOFT` | El encoder recomienda reconstrucción suavizada. Readers anteriores pueden ignorarlo y usar NEAREST. No modifica el payload. |
| 5–7 | — | reservados (`0`). |

Si bits 1 y 2 están en `0` → **paleta per-frame** (default de v1, decisión D3): cada frame
trae su propia paleta (`pal_count = pal_size`).

---

## 3. Modos (`mode`) y planos por celda

El "plano" es una matriz `rows × cols` recorrida **row-major** (fila por fila, de arriba
abajo; dentro de cada fila, izquierda a derecha). 1 byte por celda salvo RGB.

| `mode` | Nombre | `cell_fmt` | Planos (en orden) | Paleta | Bytes/celda crudos |
|---:|---|---:|---|---|---:|
| 0 | `ASCII_BW`  | 1 | `char_idx` (índice en la rampa) | no | 1 |
| 1 | `ASCII_PAL` | 2 | `char_idx` ++ `color_idx` (índice de paleta) | sí | 2 |
| 2 | `ASCII_RGB` | 3 | `char_idx` ++ `rgb` (3 bytes/celda) | no | 4 |
| 3 | `PIXEL`     | 3 | `color_idx` (índice de paleta) | sí | **1** |

- **`char_idx`**: byte en `[0, ramp_len)`. El glifo es `ramp[char_idx]`. La rampa va de
  **menos a más tinta** (índice 0 = celda más oscura → carácter más "vacío").
- **`color_idx`**: byte en `[0, pal_count)`. El color es `paleta[color_idx]` (RGB).
- **`rgb`**: 3 bytes `R,G,B` por celda (modo 16M, sin paleta).

> **PIXEL (modo 3)** es el camino de máxima eficiencia: **1 byte/celda** + paleta de 256.
> Ese byte describe la matriz ASCL. El renderer WebGL1 actual convierte los índices a un
> buffer RGBA persistente y sube esa textura con `texImage2D`/`texSubImage2D`; no sube una
> textura de índices ni cambia la representación lógica que comparte con Canvas2D.

---

## 4. CHAR RAMP

Solo presente si `ramp_len > 0` (modos ASCII). Son `ramp_len` bytes ASCII imprimibles,
ordenados por **densidad de tinta creciente**. Ejemplos:

- Rampa corta (look limpio): `" .:-=+*#%@"` (10 chars)
- Rampa larga (gradientes/foto): `" .'\`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"` (≈70 chars)
- Bordes (Sobel): `" |/-\\"` mapeando dirección de gradiente (Fase futura)

El reader lee la rampa textual desde el archivo; **no la asume hardcodeada**, así un mismo
reader sirve cualquier rampa que haya elegido el encoder.

---

## 5. OFFSET TABLE y FRAME BLOCK

### 5.1 OFFSET TABLE

`n_frames` enteros `uint32 LE`, cada uno = **offset absoluto** (desde el byte 0 del archivo)
al inicio del FRAME BLOCK correspondiente. Permite *seek* directo a cualquier frame /
keyframe sin recorrer todo. Para imagen: un solo offset.

### 5.2 FRAME BLOCK

```
┌───────────────────────────────────────────────────────────────┐
│ uint32 LE  block_len   │ bytes que siguen a este campo          │
│ uint8      tag         │ 0=RAW · 1=ZLIB · 2=DELTA · 3=DELTA_MASK│
│ uint16 LE  pal_count   │ entradas de paleta en ESTE frame (0=reusa) │
│ uint8[pal_count*3]     │ paleta RGB de este frame (si pal_count>0) │
│ uint8[...]             │ payload de planos (según tag, ver 5.3) │
└───────────────────────────────────────────────────────────────┘
```

- **Per-frame (default v1):** `pal_count = pal_size` en *todos* los frames.
- **Temporal (escena/bloque):** `pal_count > 0` al cambiar la paleta y en todo frame
  RAW/ZLIB que pueda iniciar un seek; `0` = reusar la última dentro de una cadena
  DELTA/DELTA_MASK.
- **Global:** `pal_count > 0` solo en el frame 0.
- En modos sin paleta (BW/RGB): `pal_count = 0` siempre.

### 5.3 `tag` — codificación del payload de planos

> **Optimización A+B (encoder principal):** además del DELTA por índices (tag 2),
> existe DELTA por **máscara de bits** (tag 3). Opcionalmente, un **umbral perceptual T**
> (distancia Euclídea RGB vía paleta) trata como "sin cambio" los pixeles cuyo color difiere
> ≤ T de lo ya mostrado (T=0 = lossless). Todo el umbral vive en el encoder: el decoder solo
> reconstruye lo emitido, por lo que no agrega una API ni algoritmo al player ES5.


Los planos se **concatenan** en el orden de §3 y forman el "payload crudo". Luego:

| `tag` | Nombre | Payload almacenado | Uso |
|---:|---|---|---|
| 0 | `RAW`   | planos crudos, tal cual | frames incompresibles o `--compress none` |
| 1 | `ZLIB`  | `zlib(planos crudos)` (DEFLATE) | caso general; el encoder elige RAW vs ZLIB y se queda con el más chico |
| 2 | `DELTA` | `zlib( índices_celdas_cambiadas[uint32 LE] ++ valores )` respecto al frame mostrado anterior | **video** (Fase 3); estático/poco movimiento. Plano de carácter siempre exacto |
| 3 | `DELTA_MASK` | `zlib( máscara_bits[1 bit/celda, LSB-first, ceil(N/8) bytes] ++ valores_celdas_cambiadas )` respecto al frame anterior | **video**; antes de compresión, el umbral aproximado de 87,5% solo corresponde a PIXEL/BW de 1 byte por celda. El encoder materializa y elige el menor entre RAW/ZLIB/DELTA/DELTA_MASK. |

En `DELTA` (tag 2), cada índice debe estar dentro de la matriz, pero v1 admite cualquier
orden para conservar compatibilidad con productores anteriores. Si un índice se repite,
la última tupla del payload gana. El encoder oficial emite índices únicos y ascendentes
porque esa representación canónica suele comprimir mejor. El reader valida todos los
índices y valores antes de aplicar la primera escritura. El total `k` no puede superar
`N` celdas, incluso cuando existan repeticiones toleradas.

El encoder, por frame, prueba los candidatos aplicables y **emite el más chico**; nunca
supera el tamaño RAW (DEFLATE puede inflar datos incompresibles, en ese caso cae a RAW).
Esta selección por bytes sigue la estrategia conceptual declarada en D9; la procedencia
de código se trata como un gate de publicación separado, no como parte del formato.

> **DELTA** queda **especificado pero no usado en Fase 1** (imagen): una imagen es siempre
> keyframe (RAW o ZLIB). Se activa en Fase 3 con video.

---

## 6. Compresión y webviews viejos (nota de diseño, liga con D5)

`zlib`/DEFLATE **no se decodifica nativo en JS** en webviews viejos. El proyecto distribuye
su propio `frontend/inflate.js` ES5, con límites y buffers reutilizables, para los tags
ZLIB/DELTA/DELTA_MASK.

El camino vigente es `tag = ZLIB` cuando gana por bytes e inflate en JS. Forzar RAW y
comprimir el recurso completo por HTTP queda como experimento de despliegue: el artefacto
normal es un `.asclv` que también contiene MP3, gzip suele ahorrar poco, suma una
descompresión completa y complica un posible Range. No es la recomendación general para
WebViews antiguos.

El encoder expone `--compress {auto,none,zlib}`:
- `auto` (default): por frame elige el más chico entre RAW y ZLIB.
- `none`: fuerza RAW para experimentos controlados de transporte.
- `zlib`: fuerza ZLIB.

`zstd` (mencionado en el plan) queda para Fase 6 como **mejora opcional**: mejor ratio/velocidad
offline, pero requiere decoder zstd en JS → se trata como lujo, nunca requisito.

---

## 7. Audio y envelope `.asclv`

El audio no forma parte del `.ascl` interior. El artefacto normal de distribución es un
único `.asclv` cacheable:

```text
magic      8 bytes = "ASCLVID1" o "ASCLVID2"
ascl_len   uint32 LE
audio_len  uint32 LE, 0 si no hay audio
ascl       ascl_len bytes
audio      audio_len bytes, MP3 en la versión actual
```

El envelope v1/v2 ocupa siempre **16 bytes** antes de los dos cuerpos. `ASCLVID1`
exige un interior ASCL v1 y `ASCLVID2` exige un interior ASCL v2. El lector rechaza
truncado, bytes posteriores a la longitud declarada y desacuerdo entre ambas versiones.

**`ASCLVID3` (F6-3)** agrega `meta_len` y el sidecar embebido — ver §14.2:

```text
magic      8 bytes = "ASCLVID3"
ascl_len   uint32 LE
audio_len  uint32 LE, 0 si no hay audio
meta_len   uint32 LE, 0 si no hay overlay
ascl       ascl_len bytes  (interior ASCL v3 obligatorio)
audio      audio_len bytes
meta       meta_len bytes  (sidecar ASCLSLOT, bytes exactos)
```

El reader crea vistas dentro del mismo `ArrayBuffer`, sin copiar el `.ascl` completo, y
expone el audio mediante `Blob`/object URL. Un `.ascl` suelto con MP3 externo se conserva
solo como entrada legacy del player tradicional.

El audio es el **reloj maestro**: el frame visible es
`Math.floor(audio.currentTime × fps)`; si el render se atrasa se descartan frames y el
audio nunca espera. MP3 es el codec base elegido por su compatibilidad amplia; la matriz
física debe confirmar el soporte de cada familia objetivo. Una imagen puede usar
`audio_len=0`.

---

## 8. Corrección de aspecto del carácter

El glifo monoespaciado es ~2× más alto que ancho, así que la grilla debe "achatarse" en
filas o la imagen sale estirada en vertical. El encoder calcula `rows` a partir de `cols`:

- **ASCII:** `rows = round(cols × (altoSrc / anchoSrc) × char_aspect)`, con `char_aspect ≈ 0.5`
  (el original usa 0.45; default v1 = 0.5, configurable). Guardado en `char_aspect_x1000`.
- **PIXEL:** `rows = round(cols × (altoSrc / anchoSrc))` (factor `1.0`, los bloques son cuadrados).

El reader **no recalcula nada**: usa `cols`/`rows` del header tal cual.

---

## 9. Ejemplo numérico (imagen, PIXEL 256, 200×112)

```
mode=3 (PIXEL), cols=200, rows=112, pal_size=256, n_frames=1, ramp_len=0
flags=0 (paleta per-frame), fps=15

HEADER          : 32 bytes
CHAR RAMP       : 0 bytes (pixel)
OFFSET TABLE    : 1 × 4 = 4 bytes
FRAME #0:
  block_len     : 4 bytes
  tag           : 1 byte
  pal_count=256 : 2 bytes
  paleta 256×3  : 768 bytes
  planos        : 200×112 = 22 400 bytes crudos
                  → con tag=ZLIB normalmente << 22 400
```

Crudo total (sin comprimir planos) ≈ 32 + 4 + 7 + 768 + 22 400 = **23 211 bytes** para una
"imagen" de 200×112 celdas a 1 byte/celda + paleta. Con `tag=ZLIB` el plano suele caer
fuerte. El **1 byte/celda** es la meta de peso (D-peso) y se cumple por construcción en PIXEL.

---

## 10. Pseudocódigo de parseo (reader, ES2015-safe)

```js
function parseHeader(buf) {                 // buf: ArrayBuffer
  var dv = new DataView(buf);
  if (dv.getUint8(0)!==0x41 || dv.getUint8(1)!==0x53 ||
      dv.getUint8(2)!==0x43 || dv.getUint8(3)!==0x4C) throw new Error('not ascl');
  return {
    version:  dv.getUint8(4),
    mode:     dv.getUint8(5),
    flags:    dv.getUint8(6),
    fps:      dv.getUint8(7),
    cols:     dv.getUint16(8,  true),
    rows:     dv.getUint16(10, true),
    palSize:  dv.getUint16(12, true),
    nFrames:  dv.getUint32(14, true),
    rampLen:  dv.getUint8(18),
    cellFmt:  dv.getUint8(19),
    dataOff:  dv.getUint32(20, true),
    crc32:    dv.getUint32(28, true)
  };
}
// ramp = bytes [32 .. 32+rampLen)
// offsets[i] = dv.getUint32(dataOff + i*4, true)
// frame i: en offsets[i] → block_len(u32), tag(u8), pal_count(u16), [paleta], [planos]
```

---

## 11. Constantes de referencia v1

```
MAGIC      = "ASCL"        VERSION = 1
MODE_ASCII_BW  = 0   MODE_ASCII_PAL = 1   MODE_ASCII_RGB = 2   MODE_PIXEL = 3
TAG_RAW = 0   TAG_ZLIB = 1   TAG_DELTA = 2   TAG_DELTA_MASK = 3
FLAG_LOSSY=1  FLAG_PAL_PER_SCENE=2  FLAG_PAL_GLOBAL=4  FLAG_HAS_OFFSET_TABLE=8
FLAG_RECON_SOFT=16
HEADER_SIZE = 32   DEFAULT_FPS = 15   DEFAULT_CHAR_ASPECT = 0.5
```

---

## 12. Addendum v1 — Video (Fase 3, implementado)

Lo que en §5.3 quedaba "reservado" ya está implementado y verificado pixel-perfect
(reader.js == decoder Python en 60/60 frames, ida y vuelta de seek).

### 12.1 Tag DELTA — layout exacto del payload

`payload = zlib( offsets ++ valores )`, donde tras descomprimir:

```
offsets : k × uint32 LE   índice lineal de cada celda cambiada (fila×cols + col)
valores : k × bpc bytes    la tupla completa de la celda, en orden de planos (§3)
```

`bpc` (bytes por celda) = PIXEL 1 · ASCII_BW 1 · ASCII_PAL 2 (char,colorIdx) ·
ASCII_RGB 4 (char,R,G,B). El decoder deduce `k = len(raw) / (4 + bpc)`. Reconstrucción:
copia el frame previo y sobreescribe las `k` celdas en orden de payload; un offset repetido
queda con su último valor. **DELTA siempre va comprimido (zlib).**

### 12.2 Keyframes y seek

Un frame es **keyframe** únicamente si su tag es RAW o ZLIB, decodificable sin estado
previo. DELTA y DELTA_MASK dependen de la matriz mostrada anterior.
El encoder fuerza uno cada `--keyint` frames (default `fps×2`). El reader, para ir al
frame T, arranca en el último keyframe ≤ T y decodifica hacia adelante la cadena
DELTA/DELTA_MASK.
Reproducción con audio: `frame = floor(audio.currentTime × fps)`; al saltar frames el
reader solo decodifica la cadena mínima, **el audio nunca espera** (frames descartados).

### 12.3 Paleta en video (D3)

- `per-frame` (default): cada frame trae su paleta → cada frame es full (RAW/ZLIB),
  DELTA de color no aplica (las paletas difieren). Máxima fidelidad, más peso.
- `block` (flag `PAL_PER_SCENE`): una paleta por bloque temporal; habilita DELTA dentro
  del bloque y limita el buffer del encoder. `--palette-block-frames 0` usa `fps×2`.
  El comienzo de bloque reinicia DELTA y todo keyframe RAW/ZLIB reemite la paleta activa,
  de modo que un seek nunca depende de haber decodificado el bloque anterior.
- `global` (flag `PAL_GLOBAL`): una paleta única, escrita en el frame 0; habilita DELTA
  de índices. En clips con poco movimiento baja el peso ~2× o más.

Medición (synthetic 480×270, 60 frames @15fps, pixel 200×112): per-frame ≈ 249 KB ·
global+DELTA ≈ 126 KB (57/60 frames en DELTA). ASCII_PAL global 160×45 ≈ 71 KB.

### 12.4 Archivos del cliente (Fase 2, ES2015-safe, sin dependencias)

| Archivo | Rol |
|---|---|
| `inflate.js` | inflate DEFLATE/zlib propio (para ZLIB/DELTA/DELTA_MASK en webviews viejos) |
| `reader.js` | parser .ascl + decode RAW/ZLIB/DELTA/DELTA_MASK + seek por keyframes + `fillRGBA` |
| `render-webgl.js` | WebGL 1.0: textura RGBA + quad (NEAREST). Fallback a Canvas2D si `getContext` es null |
| `render-canvas2d.js` | Canvas2D: mosaico (ImageData+nearest) y glifos ASCII (`fillText`) |
| `player.html` | player: file pickers, selector de renderer, audio como reloj maestro |

Glyph-atlas / instancing WebGL para ASCII (la 3ª ruta de D2) queda como mejora opcional
de Fase 6; hoy ASCII usa Canvas2D (glifos) y WebGL cubre pixel/color como mosaico.

---

## 13. Primera revisión ASCL v2 — implementada

### 13.1 Alcance e invariante de tamaño

V2 parte de un ASCL v1 `PIXEL` ya cuantizado y aceptado. La conversión conserva sin
cambios `cols`, `rows`, `fps`, flags de paleta, emisiones RGB, keyframes y audio. Por
frame se conserva el payload v1 original como candidato; un payload regional o predictor
solo lo reemplaza si reconstruye la misma matriz de índices y ocupa **estrictamente menos
bytes**. Un empate conserva la representación previa. Header, tabla, paleta por frame y
envelope tienen el mismo tamaño, por lo que:

```text
bytes(ASCL v2) <= bytes(ASCL v1 de entrada)
bytes(ASCLVID2) <= bytes(ASCLVID1 de entrada)  # audio copiado byte a byte
```

No hay evaluación visual, IA ni exploración de calidades en esta selección: se comparan
bytes de representaciones reversibles de una misma matriz.

### 13.2 Tags de frame

El frame block conserva exactamente el layout de §5.2.

| Tag | Nombre | Clase | Payload |
|---:|---|---|---|
| 0 | `RAW` | key | Semántica v1 sin cambios. |
| 1 | `ZLIB` | key | Semántica v1 sin cambios. |
| 2 | `DELTA` | delta | Semántica v1 sin cambios. |
| 3 | `DELTA_MASK` | delta | Semántica v1 sin cambios. |
| 4 | `REGIONAL_KEY_RAW` | key | Stream regional crudo. |
| 5 | `REGIONAL_KEY_ZLIB` | key | `zlib(stream regional)` completo. |
| 6 | `REGIONAL_DELTA_RAW` | delta | Stream regional crudo contra la matriz anterior. |
| 7 | `REGIONAL_DELTA_ZLIB` | delta | `zlib(stream regional)` completo. |
| 8 | `PREDICT_KEY_ZLIB` | key | `predictor_id u8 ++ zlib(residual[N])`. |
| 9 | `PREDICT_DELTA_ZLIB` | delta | `predictor_id u8 ++ zlib(residual[N])`. |

Los tags 0..3 son fallback normativo dentro de un archivo v2; no significan que el
archivo interior haya vuelto a v1. Los tags delta no pueden emitir paleta. Los tags key
de una paleta no global deben ser autónomos y reemitirla.

### 13.3 Grilla de tiles y stream regional

La revisión implementada fija tiles de `16×16`; los tiles del borde derivan su ancho y
alto de `cols`/`rows`. El cursor de tile es implícito, row-major, y el stream debe cubrir
exactamente toda la grilla sin bytes posteriores. `SKIP_RUN`, `SPARSE` y `MASK` solo son
válidos en deltas. Un key regional contiene un comando denso por tile.

Todos los enteros variables son **LEB128 uint32 canónico**. Máscaras y códigos packed son
**LSB-first**; sus bits de padding deben ser cero. Los mapas locales contienen índices de
la paleta RGB activa, estrictamente crecientes y sin repetidos.

| Opcode | Nombre y layout | Efecto |
|---:|---|---|
| `0x00` | `SKIP_RUN ++ run:uvarint` | Reutiliza `run>=1` tiles consecutivos. Es el único comando con corrida; un frame repetido es `SKIP_RUN(tile_count)`, no existe opcode `REPEAT`. |
| `0x01` | `SOLID ++ color_idx:u8` | Llena **un** tile. No es `SOLID_RUN` y no lleva longitud. |
| `0x02` | `SPARSE ++ k:uvarint ++ (offset:uvarint,value:u8)[k]` | Escribe cambios puntuales. Offsets locales absolutos, crecientes, dentro del tile; no admite escrituras idénticas. **En v3 los offsets viajan diferenciales (§14.1).** |
| `0x03` | `MASK ++ bits[ceil(npix/8)] ++ values[popcount]` | Un valor por bit activo, en orden row-major; la máscara no puede estar vacía. |
| `0x04` | `PACK1 ++ map[2] ++ codes[ceil(npix/8)]` | Dos índices locales, 1 bit/celda. |
| `0x05` | `PACK2 ++ count:u8 ++ map[count] ++ codes[ceil(npix/4)]` | `count=3..4`, 2 bits/celda. |
| `0x06` | `PAL4 ++ count:u8 ++ map[count] ++ codes[ceil(npix/2)]` | `count=5..16`, 4 bits/celda. **`PACK4` y `PAL4` nombran la misma idea; el nombre normativo implementado es `PAL4`.** |
| `0x07` | `PAL8 ++ values[npix]` | Un índice de paleta global por celda, row-major, sin mapa local. |

El encoder materializa los candidatos válidos por tile y elige la menor longitud real;
el desempate canónico es `SOLID`, `SPARSE`, `MASK`, `PACK1`, `PACK2`, `PAL4`, `PAL8`.
Después compara el stream completo crudo contra su zlib y usa zlib solo si es menor. No
hay zlib independiente por tile ni prefijo de longitud descomprimida en los tags 4..7.

### 13.4 Predictores reversibles

Toda aritmética es modular `uint8`; el residual descomprimido mide exactamente
`N=cols×rows` bytes. Para keyframes se comparan:

- `0 LEFT`: `residual = actual - izquierda`, usando `0` en el borde izquierdo;
- `1 TOP`: `residual = actual - superior`, usando `0` en el borde superior;
- `2 GRADIENT`: predictor `izquierda + superior - superior_izquierda`.

Para deltas se comparan:

- `3 PREVIOUS_SUB`: `residual = actual - anterior`;
- `4 PREVIOUS_XOR`: `residual = actual XOR anterior`.

Cada opción reconstruye exactamente el índice original. Gana el payload zlib menor y,
en empate, el ID más bajo. El predictor completo aún debe superar estrictamente al
candidato v1/regional que ya ganaba para reemplazarlo.

### 13.5 Reader y límites de la primera revisión

`reader-factory.js` despacha `version=1` a `ReaderV1` y `version=2` a `ReaderV2`; cualquier
otra versión falla. `ReaderV2` está escrito con sintaxis ES5, conserva una sola matriz
lógica `Uint8Array`, valida CRC/header/offsets/bloques/paletas, limita inflate y valida un
stream regional completo antes de la primera escritura.

El dirty set es híbrido y disjunto: `SPARSE`, `MASK` y deltas v1 marcan celdas exactas;
comandos regionales densos marcan tiles; keyframe o cambio de paleta fuerza full. Los
renderers Canvas2D y WebGL1 consumen la misma API y la unión se conserva durante seek.

La garantía de memoria no es “cero buffers proporcionales”: `cells`, RGBA, bitsets y el
scratch reutilizable dependen necesariamente de la grilla. El gate correcto es **no crear
un nuevo buffer de frame completo en cada cuadro**. El scratch crece bajo bounds hasta la
capacidad necesaria y luego se reutiliza; la revisión limita a 64 MiB cada bound operativo
de matriz/inflate que valida y la lista de tiles a 65.535 IDs `uint16`. No se interpreta
ese valor como límite de RAM total del player.

### 13.6 Envelope, descarga y caché

`ASCLVID2` usa el envelope fijo de 16 bytes de §7; no introduce directorio, GOPs externos
ni chunks. La implementación actual descarga el archivo completo por XHR, lo conserva como
un recurso único cacheable y reproduce después de obtenerlo completo. Streaming, HTTP Range
y carga parcial permanecen fuera de esta revisión.

### 13.7 Pendientes que no forman parte del contrato

- validación física del artefacto HQ en Smart TV; el benchmark exacto local está cerrado;
- remap exacto de IDs de paleta: está bajo evaluación offline y, si se adopta, debe
  permutar conjuntamente paleta e índices para que cada RGB mostrado permanezca idéntico;
  la Instancia 005 registra un ahorro estimado menor a 1% y por eso no es default;
- intervención matricial, near-lossless, FPS por segmentos, diccionarios y Range;
- otros tamaños de tile o nuevos opcodes, que requerirían otra revisión de codec
  (la revisión v3 de §14 cambia solo la codificación de offsets de `SPARSE` y el
  envelope; no agrega opcodes).

---

## 14. Revisión ASCL v3 / ASCLVID3 — implementada (F6-3, S-4)

V3 agrupa los cambios de formato de la revisión única S-4 para desplegar **una sola**
versión nueva de decoder. Un reader v2 ya desplegado rechaza tanto el magic
`ASCLVID3` como `version=3`, limpiamente. Todo lo no listado acá es idéntico a v2:
header de 32 bytes, CRC con el alcance v2, tags 0..9, tiles 4..32 (byte 26),
`codec_flags=0x01`, predictores y política de paletas.

### 14.1 SPARSE con offsets diferenciales (F6-1)

En un interior `version=3`, el comando regional `SPARSE` codifica cada offset como

```text
delta = offset - prior - 1        # prior arranca en -1
```

de modo que el primer delta coincide con el offset absoluto y los siguientes ahorran
bytes de uvarint en offsets altos. Como v2 ya exigía offsets estrictamente
crecientes, el delta nunca es negativo: la propiedad "creciente" pasa a ser
**estructural** y el decoder solo valida que el offset reconstruido quede dentro del
tile. Las demás reglas de SPARSE (sin escrituras idénticas, uvarint canónico, solo
en deltas) no cambian.

**El modo lo declara la versión del header, nunca el stream** (regla 8): un stream
leído con el modo equivocado puede decodificar en silencio a otra matriz, por eso no
existe flag de negociación. Referencias: `regional_codec_v2.py`
(`sparse_differential`), `reader-v2.js` (`_sparseDiff`), gateados por `version`.

### 14.2 Envelope `ASCLVID3` con `meta_len`

Layout en §7: header de **20 bytes** (`magic ++ ascl_len ++ audio_len ++ meta_len`)
y tres cargas. `meta` transporta el sidecar `ASCLSLOT` (v1 o v2 de slots) **byte a
byte**, con su propio CRC interno; `meta_len=0` significa video sin overlay. La
versión del envelope y la del ASCL interior deben coincidir (3↔3) y `meta` solo
existe en v3. El `clip.slots` externo queda como vía de transición para v1/v2: el
live-player usa la meta embebida cuando existe y solo si no, pide el sidecar por XHR.

### 14.3 Compatibilidad y verificación

- `reader-factory.js` despacha `version=3` al mismo `ReaderV2`; v1 sigue en `ReaderV1`.
- Transcodificación: `ascl_v2.py --v3 [--meta sidecar.slots]` o
  `make_clip --format v3`. El default de producto sigue emitiendo v2 hasta que el
  operador adopte v3 (S-4).
- Round-trip Python↔JavaScript byte-exacto verificado por `tests/test_v3_cross.js`
  sobre fixtures generados por `tests/test_ascl_v2.py` (patrón F7-4).
