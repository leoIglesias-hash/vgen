# ASCILINE — Estado histórico y traspaso de las primeras sesiones

> **Documento histórico.** Conserva el traspaso de las primeras sesiones, pero sus
> pendientes ya no representan el estado actual. Para continuar desde la versión Oklab
> adaptativa use `HOJA-DE-RUTA-TECNICA-V2.md` y
> `REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`.

> Documento de traspaso. Resume qué se construyó, las decisiones tomadas, el estado de
> cada fase, los comandos clave y lo que falta. Para el detalle del formato ver
> `docs/ASCL-format-spec.md`; para el contexto original ver `docs/ASCILINE-contexto.md`.
> Para pegar como arranque en la próxima sesión, ver la sección 9 ("Prompt sugerido").

---

## 1. Qué es

Rediseño de **ASCILINE** (fork conceptual de `github.com/YusufB5/ASCILINE`): convierte
imagen/video a una grilla de texto (ASCII) o de bloques de color (pixel mode) y la
reproduce en el navegador. Clave del rediseño: **pre-encodear offline** a un formato
compacto `.ascl` para que el playback sea **estático** (≈0 cómputo de servidor), con render
**WebGL** (rompe el techo de ~360p) y **fallback Canvas2D** para webviews viejos (ES2015).

---

## 2. Decisiones tomadas (cerradas con el usuario)

| # | Decisión | Valor elegido |
|---|---|---|
| D1 | Resolución | **Variable** (cols/rows en header). Objetivo **1080p**. El sweet-spot de prueba fue 320 col, pero el target real es 1080. |
| D2 | Render ASCII | Las **tres rutas disponibles** por compatibilidad: Canvas2D `fillText`, glyph-atlas y WebGL. Hoy implementado: WebGL (pixel) + Canvas2D (pixel mosaico y ASCII glifos). Glyph-atlas WebGL = pendiente. |
| D3 | Paleta | **256 colores**. Default `per-frame`; también está `global` (256 por video, habilita DELTA, más liviano). |
| D9 | Fork vs nuevo | **Fork** conceptual: se reusan ideas (rampa, delta, tags) en código nuevo standalone. |
| FPS | Configurable | Default 15; se puede 10/12/20/25… (vive en el header). |
| Compresión | zlib (DEFLATE) por frame; alternativa RAW + gzip/br por HTTP. zstd queda como mejora opcional (necesita decoder JS). |
| Audio | Carril separado MP3 (reloj maestro), nunca dentro del `.ascl`. |

**Última pedida del usuario (PENDIENTE de generar):** una variante **1080p, paleta global
(256 por video), 10 fps** — y poder generar varias combinaciones de fps/cols para evaluar
(sin importar el peso). No se pudo correr porque la VM de cómputo se cayó (ver sección 8).

---

## 3. Estructura de carpetas (ya ordenada)

```
ASCILINE-video/
├── frontend/   # SOLO esto se sube para reproducir (hosting estático, sin instalar nada)
│   ├── player.html          # player: file picker o autocarga ?src=, audio reloj maestro
│   ├── inflate.js           # descompresor zlib propio, ES5 (para tag ZLIB/DELTA)
│   ├── reader.js            # parser .ascl + decode RAW/ZLIB/DELTA + seek por keyframes
│   ├── render-webgl.js      # WebGL 1.0: textura RGBA + quad (NEAREST)
│   └── render-canvas2d.js   # fallback Canvas2D: mosaico (pixel) + glifos (ASCII)
├── backend/    # CREA los archivos (Python offline)
│   ├── encoder.py           # imagen/video -> .ascl (+ audio mp3 aparte)
│   ├── ascl_decode.py       # decoder/verificador de referencia + preview MP4/PNG
│   ├── ascl_bundle.py       # empaqueta .ascl + .mp3 -> .asclv (UN archivo)
│   ├── make_clip.py         # UN comando: video -> outputs/<nombre>.asclv
│   └── requirements.txt     # Pillow, numpy, opencv-python-headless (+ ffmpeg del sistema)
├── inputs/     # videos/imágenes fuente (incluye TKN-2434-VACANTE-gana-19 seg-.mp4)
├── outputs/    # resultados .asclv / .ascl / previews
└── docs/       # ASCL-format-spec.md · DESPLIEGUE.md · ASCILINE-contexto.md · este archivo
```

---

## 4. Estado por fase (todo lo marcado ✅ está VERIFICADO)

- **Fase 1 — Formato + encoder imagen** ✅ Spec byte-por-byte (`ASCL-format-spec.md`),
  encoder de imagen, round-trip pixel-perfect en 4 modos.
- **Fase 2 — Reader/player ES2015** ✅ `reader.js` decodifica **idéntico** al decoder Python
  (cross-test en Node, incluido seek adelante/atrás). `inflate.js` verificado contra zlib.
- **Fase 3 — Video** ✅ encoder multi-frame con DELTA + paleta per-frame/global + decimación
  de fps. Fidelidad pixel-perfect en 246/246 frames del clip real.
- **Fase 4 — Audio** ✅ extracción a mp3 + sync por `audio.currentTime` (descarta frames).
- **Bundle `.asclv`** ✅ junta video+audio en un archivo. `make_clip.py` = un comando.
- **Render** ✅ WebGL (pixel, rompe 360p) + Canvas2D (fallback). Bug resuelto: un canvas
  no puede cambiar de contexto WebGL↔2D; el player **reemplaza el nodo** al cambiar renderer.
- **Pruebas en navegador** ✅ El usuario confirmó: WebGL y Canvas2D funcionan y se ven igual.

### Medición real (clip `TKN-2434...`, fuente 1920×1080 25fps, 19.7s)
- pixel 320×180, 15fps, global+DELTA → `.ascl` 7.13 MB + mp3 233 KB (`.asclv` 7.5 MB), ~435 KB/s.
- Es un clip de **alto movimiento**: 222 frames ZLIB / 24 DELTA → el delta casi no gana, por eso
  pesa. En clips estáticos el formato es mucho más liviano.

---

## 5. Formato (resumen; detalle en `ASCL-format-spec.md`)

- **`.ascl`**: header 32 B (magic "ASCL", mode, cols, rows, fps, n_frames, pal_size, crc32…)
  + rampa (solo ASCII) + tabla de offsets + frames. Por frame: `block_len`, `tag`
  (0 RAW / 1 ZLIB / 2 DELTA), `pal_count` + paleta, planos. 1 byte/celda en pixel.
- **`.asclv`** (bundle): magic `ASCLVID1`(8) + `ascl_len`(u32 LE) + `audio_len`(u32 LE)
  + bytes del `.ascl` + bytes del `.mp3`.

---

## 6. Comandos clave

```bash
# Crear (un comando) — requiere Python + requirements + ffmpeg
cd backend
python make_clip.py "../inputs/mi-video.mp4"                 # default pixel 320 / 15fps / global
python make_clip.py "../inputs/mi-video.mp4" --cols 1920 --fps 10 --palette global \
       --out ../outputs/clip_1080_fps10.asclv                # << el 1080 PENDIENTE
python make_clip.py "../inputs/foto.jpg" --image             # imagen (sin audio)

# Verificar / preview sin navegador
python ascl_bundle.py unpack ../outputs/clip.asclv /tmp
python ascl_decode.py /tmp/clip.ascl --mp4 /tmp/preview.mp4

# Reproducir: publicar frontend/ + outputs/ en el servidor PHP/Apache existente.
# El proyecto no incluye ni inicia un servidor auxiliar.
```

`make_clip.py` flags: `--cols` (resolución; rows auto), `--fps` (10/12/15/20/25; tope = fps
de la fuente, acá 25), `--palette global|per-frame`, `--mode pixel|ascii-pal|ascii-rgb|ascii-bw`.

---

## 7. Despliegue (detalle en `docs/DESPLIEGUE.md`)

| Quiero… | Subo | Instalo |
|---|---|---|
| Solo **reproducir** | `frontend/` + los `.asclv` | **nada** (hosting estático: nginx, GitHub Pages, S3+CDN, etc.) |
| **Crear** clips | `backend/` | Python 3.8+ + `pip install -r requirements.txt` + **ffmpeg** del sistema |

La recomendación de esta etapa era gzip/brotli, `immutable` y nombres por hash. Fue
reemplazada por la política medida y la ruta estable de `DESPLIEGUE.md`; no debe usarse
como configuración actual.

---

## 8. Limitación histórica que sigue siendo relevante

`file://` suele bloquear XHR. La autocarga de `tv-player.html` se prueba desde el servidor
PHP/Apache existente; con doble clic se usa el selector de archivo del player tradicional.
Las incidencias específicas del entorno de trabajo original se retiraron porque no forman
parte del producto ni del procedimiento reproducible.

---

## 9. Pendientes / próximos pasos (priorizados)

1. **Generar el 1080p** pedido: `--cols 1920 --fps 10 --palette global` → `clip_1080_fps10.asclv`,
   y opcionalmente dejarlo como `DEFAULT_SRC` en `player.html`.
2. **Tanda de variantes para evaluar**: grilla fps (12/15/25) × cols (200/320/480), pixel global,
   con tabla de peso/KB-s. (El usuario ya la pidió.)
3. **Zoom 1 en el player** (para ver 1080 a 1:1; hoy el selector arranca en 2).
4. **Bajar peso del clip de alto movimiento**: comparar cols/fps/modo; evaluar chroma subsampling.
5. **Fase 5 — `storage.js`**: HTTP-cache + IndexedDB (+ Service Worker opcional) con versionado
   por hash para precarga y playback offline en webviews. (No empezada.)
6. **Glyph-atlas WebGL** para ASCII (3ª ruta de D2, opcional).
7. **zstd** como mejora opcional (necesita decoder JS; tratar como lujo).

---

## 10. Prompt sugerido para arrancar la próxima sesión

> "Continuamos el proyecto ASCILINE. Leé `docs/ESTADO-Y-CONTINUACION.md` (y si hace falta
> `docs/ASCL-format-spec.md`) para el contexto completo. Primero verificá si el entorno de
> cómputo (bash) está disponible. Si está, generá el clip 1080p pendiente
> (`--cols 1920 --fps 10 --palette global` -> `outputs/clip_1080_fps10.asclv`) y después la
> tanda de variantes para evaluar. Mantené el código del cliente ES2015-safe."

---

## 11. Optimización A/B/C (sesión 2026-06-25)

**Contexto fps:** la fuente es 25 fps; la decimación entera da 12,5 fps reales (1 de cada 2).
El header `fps` es un byte entero (no admite 12,5) → se escribe 13; el nombre del archivo usa
`fps12_5`. Con audio como reloj maestro, la reproducción va a tiempo real igual.

**A — DELTA por máscara de bits (tag 3, lossless).** Además del DELTA por índices (tag 2,
4 bytes/celda), se agregó DELTA por máscara: `zlib( bitmask[1 bit/celda, LSB-first] ++ valores )`.
Cuesta ~1,125 bytes por celda cambiada → **gana mientras cambie <~87,5%** de la imagen (vs ~20%
del tag 2). Implementado en `encoder.py` (`encode_frame`) y decodificado en `reader.js` y
`ascl_decode.py`. Round-trip verificado (200 casos aleatorios + video, CRC OK).

**B — umbral perceptual T.** En `encoder.py`/`make_clip.py`: `--threshold T` (distancia
Euclídea RGB vía paleta; solo pixel+global). Un pixel se considera "sin cambio" si su color
difiere ≤ T de lo ya emitido (se compara contra lo EMITIDO para acotar el drift). T=0 = lossless.
Toda la lógica vive en el encoder; el decoder solo reconstruye → player ES2015 intacto.
Bug corregido en el camino: la distancia de color debe calcularse en int32 (en int16 el
cuadrado desborda y arruina el umbral).

**C — subida parcial de textura (WebGL).** `reader.js` expone `dirtyFull/dirtyY0/dirtyY1`
(banda de filas que cambió, unión por seek); `render-webgl.js` hace `texSubImage2D` de esa
banda (fallback a `texImage2D` completo en keyframe/primer frame/reader viejo). Verificado en
node: reconstrucción idéntica al full en todos los frames. **Ojo:** en clips de alto movimiento
la banda sucia abarca casi toda la altura → ahorro ~0,5%. C rinde en movimiento localizado.

### Resultados medidos (clip TKN, 1920×1080, 12,5 fps, 246 frames; KB de video, audio +228 KB)
| Versión | Calidad | Video | vs original |
|---|---|---|---|
| Original (formato viejo, ZLIB) | lossless | 124,3 MB | — |
| A lossless (nuevo canónico)     | lossless | 107,9 MB | −13% |
| A+B, T=24                       | 36,85 dB | 91,5 MB | −26% |

Curva a 480 cols: T=12 → 47,7 dB (−3%), T=24 → 37,0 dB (−15%), T=40 → 30,4 dB (−31%).

**Archivos nuevos/entregables:**
- `outputs/clip_1080_fps12_5.asclv` — 1080p lossless (reemplaza al de 124 MB).
- `outputs/clip_1080_fps12_5_T24.asclv` — 1080p perceptual T=24.
- `backend/_encode_opt.py` — fue el encoder A+B reanudable de esta instancia histórica.
  Se retiró del árbol publicable en v0.2 por usar checkpoints pickle predecibles; hoy se
  usa `make_clip.py --threshold` y el helper solo permanece en el historial Git.

**Comando oficial nuevo:** `python make_clip.py video.mp4 --cols 1920 --fps 10 --palette global --threshold 24`

### Pendientes que siguen
- Dirty-region por tiles/bloques (C más fino) — solo ayuda en movimiento localizado.
- Fase 5 `storage.js` (IndexedDB + SW). Glyph-atlas WebGL. zstd.
