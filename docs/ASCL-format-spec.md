# Especificación del formato `.ascl` — v1

> Contenedor binario compacto para reproducir ASCILINE como **VOD pre-encodeado**.
> El encoder (offline) hace todo el cómputo una vez; el reader (cliente, ES2015-safe)
> solo parsea bytes y dibuja. El servidor sirve un **archivo estático** → ≈0 cómputo en playtime.
>
> Estado: formato v1 implementado para imagen y video. Incluye RAW, ZLIB, DELTA,
> DELTA_MASK, paletas globales/temporales y envelope `.asclv` con audio.

---

## 0. Decisiones que fija esta versión

| Decisión | Valor v1 | Dónde vive |
|---|---|---|
| **D1** Resolución | **variable** (`cols`/`rows` en header), objetivo 1080p | header |
| **D2** Render | el `.ascl` es agnóstico al renderer; sirve a Canvas2D `fillText`, glyph-atlas e instancing WebGL | reader elige en runtime |
| **D3** Paleta | 1..256 colores; global, bloque/adaptativa o per-frame. `encoder.py` directo conserva per-frame y `make_clip.py` usa global como defaults de interfaz | header `flags` + `pal_count` por frame |
| **D9** Fork | encoder/reader construidos sobre `YusufB5/ASCILINE` (rampa, delta y tags reusados) | — |
| FPS | **configurable**, default 15 (20/25/30 válidos) | header `fps` |
| Peso | **1 byte/celda** vía índice de paleta | plano de índices |
| Compresión | `zlib` (DEFLATE) por frame, o RAW + gzip/br por HTTP (ver §6) | tag por frame |

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
| 4  | 1 | uint8   | `version` | `1`. |
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
| 26 | 2 | uint16  | `reserved`| `0`. |
| 28 | 4 | uint32  | `crc32`   | CRC32 (IEEE) de **todo el archivo desde el byte 32 hasta el final**. `0` = sin verificar. Detecta corrupción de cache. |

Total: **32 bytes**.

### 2.1 `flags` (bitfield)

| Bit | Nombre | Significado |
|---:|---|---|
| 0 | `LOSSY` | Hubo delta temporal con pérdida (tolerancia > 0). El plano de carácter siempre es exacto. |
| 1 | `PAL_PER_SCENE` | Paleta temporal: se reemite en cambios de escena o bloque y en todo keyframe (frames con `pal_count > 0`). |
| 2 | `PAL_GLOBAL` | Una sola paleta para todo el clip (solo el frame 0 trae `pal_count > 0`). |
| 3 | `HAS_OFFSET_TABLE` | Hay tabla de offsets (siempre `1` en v1). |
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
> Es el que sube a 1080p barato (en WebGL: 1 `texImage2D` del plano de índices + 1 draw call).

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
  RAW/ZLIB que pueda iniciar un seek; `0` = reusar la última dentro de una cadena DELTA.
- **Global:** `pal_count > 0` solo en el frame 0.
- En modos sin paleta (BW/RGB): `pal_count = 0` siempre.

### 5.3 `tag` — codificación del payload de planos

> **Optimización A+B (encoder `_encode_opt.py`):** además del DELTA por índices (tag 2),
> existe DELTA por **máscara de bits** (tag 3). Opcionalmente, un **umbral perceptual T**
> (distancia Euclídea RGB vía paleta) trata como "sin cambio" los pixeles cuyo color difiere
> ≤ T de lo ya mostrado (T=0 = lossless). Todo el umbral vive en el encoder: el decoder solo
> reconstruye lo emitido, por lo que el player sigue ES2015 y la compatibilidad es total.


Los planos se **concatenan** en el orden de §3 y forman el "payload crudo". Luego:

| `tag` | Nombre | Payload almacenado | Uso |
|---:|---|---|---|
| 0 | `RAW`   | planos crudos, tal cual | frames incompresibles o `--compress none` |
| 1 | `ZLIB`  | `zlib(planos crudos)` (DEFLATE) | caso general; el encoder elige RAW vs ZLIB y se queda con el más chico |
| 2 | `DELTA` | `zlib( índices_celdas_cambiadas[uint32 LE] ++ valores )` respecto al frame mostrado anterior | **video** (Fase 3); estático/poco movimiento. Plano de carácter siempre exacto |
| 3 | `DELTA_MASK` | `zlib( máscara_bits[1 bit/celda, LSB-first, ceil(N/8) bytes] ++ valores_celdas_cambiadas )` respecto al frame anterior | **video**; gana mientras cambie <~87,5% de la imagen (mucho más barato que tag 2 en alto movimiento). El encoder elige el menor entre RAW/ZLIB/DELTA/DELTA_MASK |

En `DELTA` (tag 2), los índices son canónicos: deben estar estrictamente ordenados de
menor a mayor y no pueden repetirse. Esto permite validar completamente el payload antes
de mutar la matriz y hace determinista su representación. El encoder oficial siempre los
emite en ese orden; un reader puede rechazar un DELTA que incumpla esta regla.

El encoder, por frame, prueba los candidatos aplicables y **emite el más chico**; nunca
supera el tamaño RAW (DEFLATE puede inflar datos incompresibles, en ese caso cae a RAW).
Esto es la misma estrategia del codec original de ASCILINE, reusada (D9).

> **DELTA** queda **especificado pero no usado en Fase 1** (imagen): una imagen es siempre
> keyframe (RAW o ZLIB). Se activa en Fase 3 con video.

---

## 6. Compresión y webviews viejos (nota de diseño, liga con D5)

`zlib`/DEFLATE **no se decodifica nativo en JS** en webviews viejos: el reader necesitaría
un `inflate` en JS (p.ej. `pako`, ~10 KB) para el `tag = ZLIB`. Dos caminos, ambos soportados:

1. **`tag = ZLIB` + inflate en JS** — archivo más chico en disco; cuesta ~10 KB de lib y algo de CPU.
2. **`tag = RAW` + compresión de transporte HTTP** — el `.ascl` se sirve con
   `Content-Encoding: gzip` (universal) o `br` (donde haya). El webview descomprime **nativo**,
   el reader recibe bytes ya crudos. Cero lib extra, ideal para el target más viejo.

El encoder expone `--compress {auto,none,zlib}`:
- `auto` (default): por frame elige el más chico entre RAW y ZLIB.
- `none`: fuerza RAW (pensado para servir con gzip/br por HTTP).
- `zlib`: fuerza ZLIB.

`zstd` (mencionado en el plan) queda para Fase 6 como **mejora opcional**: mejor ratio/velocidad
offline, pero requiere decoder zstd en JS → se trata como lujo, nunca requisito.

---

## 7. Audio y envelope `.asclv`

El audio no forma parte del `.ascl` interior. El artefacto normal de distribución es un
único `.asclv` cacheable:

```text
magic      8 bytes = "ASCLVID1"
ascl_len   uint32 LE
audio_len  uint32 LE, 0 si no hay audio
ascl       ascl_len bytes
audio      audio_len bytes, MP3 en la versión actual
```

El reader crea vistas dentro del mismo `ArrayBuffer`, sin copiar el `.ascl` completo, y
expone el audio mediante `Blob`/object URL. Un `.ascl` suelto con MP3 externo se conserva
solo como entrada legacy del player tradicional.

El audio es el **reloj maestro**: el frame visible es
`Math.floor(audio.currentTime × fps)`; si el render se atrasa se descartan frames y el
audio nunca espera. MP3 es el piso universal. Una imagen puede usar `audio_len=0`.

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

## 11. Constantes de referencia

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
copia el frame previo y sobreescribe las `k` celdas. **DELTA siempre va comprimido (zlib).**

### 12.2 Keyframes y seek

Un frame es **keyframe** si su tag ≠ DELTA (RAW/ZLIB, decodificable sin estado previo).
El encoder fuerza uno cada `--keyint` frames (default `fps×2`). El reader, para ir al
frame T, arranca en el último keyframe ≤ T y decodifica hacia adelante la cadena DELTA.
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
