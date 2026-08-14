# ASCILINE → `.ascl` / `.asclv`

Convierte imagen o video a una grilla de texto/bloques de color y la reproduce en el
navegador (incluso webviews viejos), **pre-encodeando offline**: el servidor de playback
no calcula nada, solo sirve archivos estáticos.

## Estructura

```
ASCILINE-video/
├── frontend/     # lo que corre en el navegador (SOLO esto para reproducir)
│   ├── player.html
│   ├── inflate.js          # descompresor zlib propio (ES5)
│   ├── reader.js           # parser .ascl + decode RAW/ZLIB/DELTA + seek
│   ├── render-webgl.js     # renderer WebGL (rompe el techo de 360p)
│   └── render-canvas2d.js  # fallback Canvas2D (mosaico + glifos ASCII)
├── backend/      # lo que CREA los archivos (Python, offline)
│   ├── encoder.py          # imagen/video -> .ascl  (+ audio .mp3 aparte)
│   ├── ascl_decode.py      # decoder/verificador de referencia + preview
│   ├── ascl_bundle.py      # empaqueta .ascl + .mp3 -> .asclv (un archivo)
│   ├── make_clip.py        # UN comando: video -> outputs/<nombre>.asclv
│   └── requirements.txt
├── inputs/       # videos/imágenes fuente a transformar
├── outputs/      # resultados (.asclv = video+audio juntos)
└── docs/         # spec del formato, contexto y despliegue
```

## Crear un clip (un solo comando)

```bash
cd backend
python make_clip.py "../inputs/mi-video.mp4"
# -> ../outputs/mi-video.asclv   (video ASCII + audio en UN archivo)
```

Opciones principales: `--profile detail|balanced|graphic|graphic-hq|graphic-ultra|color|custom`,
`--cols 320`,
`--palette-size 128`, `--fps 15`, `--palette global|block|adaptive|per-frame`,
`--palette-algorithm median-cut|fast-octree|kmeans-rgb|kmeans-oklab`,
`--reconstruction nearest|soft`, `--bake-smoothing none|soft`,
`--dither off|selective|auto`, `--dither-matrix 2|4` y
`--mode pixel|ascii-pal|ascii-rgb|ascii-bw`. Los valores manuales de columnas y colores
siempre prevalecen sobre el perfil.
Para imágenes: `python make_clip.py ../inputs/foto.jpg --image`.

Los perfiles graficos de resolucion creciente conservan 256 colores: `graphic` usa
640 columnas, `graphic-hq` 768 y `graphic-ultra` 960. Son atajos seleccionables;
`--cols` continua permitiendo cualquier valor manual y tiene prioridad sobre el perfil.

Ejemplos de calidad:

```bash
# Más detalle espacial, menos colores, presentación suave recomendada
python make_clip.py ../inputs/video.mp4 --profile detail --reconstruction soft

# Valores totalmente manuales y suavizado 2x horneado offline
python make_clip.py ../inputs/video.mp4 --cols 960 --palette-size 96 \
  --bake-smoothing soft --reconstruction nearest

# Paleta renovada cada dos segundos: mejor adaptación de color sin perder DELTA
python make_clip.py ../inputs/video.mp4 --profile graphic \
  --palette block --palette-block-frames 0 --palette-algorithm kmeans-rgb

# Reducir bandas de color sin costo nuevo en el navegador (solo mode pixel).
python make_clip.py ../inputs/video.mp4 --palette block --palette-size 128 \
  --dither selective --dither-matrix 4

# Calidad experimental v1: paleta perceptual, bloques por cambio real de color,
# estabilidad temporal y dithering aceptado solo cuando mejora numericamente.
python make_clip.py ../inputs/video.mp4 --profile graphic-hq \
  --palette adaptive --palette-algorithm kmeans-oklab \
  --adaptive-min-frames 5 --adaptive-max-frames 10 \
  --adaptive-change-threshold 0.20 --adaptive-hard-cut-threshold 0.58 \
  --adaptive-stability-max 0.25 --perceptual-lut-bits 0 \
  --dither auto --dither-budget 0.05 \
  --dither-min-improvement 0.08 --dither-window 10
```

En `--palette block`, el valor `0` usa `fps × 2`. El encoder mantiene en memoria solo el
bloque activo y hace que todo keyframe incluya su paleta, por lo que el seek sigue siendo
independiente y compatible con el reader v1.

En `--palette adaptive` no se usa IA ni reconocimiento visual. El procesador compara
numericamente histogramas Oklab, color medio y energia de gradiente. Un cambio fuerte
corta exactamente antes del primer frame nuevo; una deriva gradual puede renovar la
paleta despues del minimo y todo bloque queda limitado por el maximo. Los defaults son
5/10 frames, deriva `0.20`, hard cut `0.58` y estabilidad maxima `0.25`. El maximo
de 10 es una guarda de calidad, no un intervalo fijo: el detector puede cortar antes.
La CLI imprime tamano, motivo y score de cada bloque para que estas decisiones puedan
auditarse. Sigue siendo ASCL v1 con `PAL_PER_SCENE`, sin cambios en el player.

`kmeans-oklab` construye y compara los colores en un espacio perceptual y pondera
gradientes suaves para reducir banding. `--perceptual-lut-bits 0` hace cuantizacion
Oklab exacta y prioriza calidad; valores `3..7` construyen una LUT offline para acelerar
el procesamiento. Elegir exacto o LUT no agrega CPU, GPU ni RAM al navegador.

`make_clip.py` usa `kmeans-rgb` por defecto: tarda más al crear el archivo, pero no agrega
ningún trabajo al navegador y en el video TKN redujo de forma clara el error de color y de
bajas frecuencias frente a MEDIANCUT. `fast-octree` es la alternativa rápida del procesador;
`median-cut` conserva el comportamiento histórico y sigue siendo el default de `encoder.py`.

El dithering selectivo se hornea como indices ASCL v1 normales: no cambia el player ni
suma CPU/GPU al reproducir. En video se admite con paleta `global` o `block`; `per-frame`
queda excluida para evitar inestabilidad temporal entre paletas.

El modo `--dither auto` agrega tres limites verificables: presupuesto maximo de celdas,
mejora minima del error de baja frecuencia y ventana temporal de histeresis. Solo acepta
tiles que mejoran el proxy, nunca altera bordes protegidos y conserva su estado entre
renovaciones normales de paleta; se reinicia ante un hard cut real. Tambien admite
paleta `adaptive`, pero no `per-frame`.

Las pruebas, observaciones visuales y decisiones por version se conservan en
`docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`. Cada conclusion queda ligada a su
configuracion; si cambia el modo, la grilla, los FPS, la paleta, el dithering o el codec,
debe validarse nuevamente.

### Documentación activa

- `docs/HOJA-DE-RUTA-TECNICA-V2.md`: backlog vigente, dependencias y gates.
- `docs/PLAN-IMPLEMENTACION-OPTIMIZACION.md`: principios e invariantes.
- `docs/ASCL-format-spec.md`: formato v1.
- `docs/DISENO-ASCL-V2-TILES.md`: propuesta binaria v2.
- `docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`: decisiones append-only.
- `docs/BENCHMARK-V1-ADAPTATIVO-OKLAB.md`: evidencia de la versión actual.
- `docs/DESPLIEGUE.md`: hosting y caché.

`ESTADO-Y-CONTINUACION.md`, `GENERAR-1080-Y-VARIANTES.md` y los diseños preliminares
quedan como evidencia histórica; no constituyen el backlog actual.

## Reproducir

Abrí `frontend/player.html`, elegí el `.asclv` y Play. El `.asclv` ya contiene video y
audio en un único archivo. El selector de MP3 externo se conserva solamente para abrir
un `.ascl` suelto/antiguo sin perder compatibilidad. El renderer va WebGL→Canvas2D solo;
el audio es el reloj maestro (si el render se atrasa, descarta frames).

### Prueba directa en Smart TV

`frontend/tv-player.html` es el frontend sin controles de laboratorio. Precarga
la ruta relativa configurada en `DEFAULT_SRC`, ajusta el video a la pantalla sin
deformarlo y entra
en fullscreen/reproduce al presionar una tecla del `1` al `8` o al hacer click/toque.
Incluye un boton pequeno **Iniciar descarga** para repetir manualmente la precarga desde
un gesto del control remoto. Si la red falla, tanto ese boton como un nuevo click en la
pantalla vuelven a intentar la descarga sin recargar la pagina.

El servidor PHP existente debe publicar el clip en esa ruta relativa. El archivo
versionado conserva su nombre original; `clip.asclv` es solamente su nombre al subirlo.
La pagina tambien acepta:

```text
frontend/tv-player.html?renderer=canvas2d
frontend/tv-player.html?loop=0
```

El demo usa loop por defecto. WebGL1 se intenta primero y Canvas2D conserva la misma
funcionalidad como fallback.

## Verificar / preview sin navegador

```bash
cd backend
python ascl_bundle.py unpack ../outputs/mi-video.asclv /tmp     # -> .ascl + .mp3
python ascl_decode.py /tmp/mi-video.ascl --mp4 /tmp/preview.mp4 # MP4 de control
```

## Despliegue: ver `docs/DESPLIEGUE.md`

- **Solo reproducir** → subir `frontend/` + los `.asclv`. Sin Python, sin ffmpeg, sin instalar nada.
- **Crear en el servidor** → además Python 3 + `requirements.txt` + `ffmpeg`.

## Pruebas

```bash
python -m unittest discover -s tests -v
node tests/test_frontend_renderers.js
node tests/test_reader_bundle_view.js
node tests/test_tv_controller.js
node tests/test_tv_player_page.js
```
