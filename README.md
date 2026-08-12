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

Opciones principales: `--profile detail|balanced|graphic|color|custom`, `--cols 320`,
`--palette-size 128`, `--fps 15`, `--palette global|block|per-frame`,
`--palette-algorithm median-cut|fast-octree|kmeans-rgb`,
`--reconstruction nearest|soft`, `--bake-smoothing none|soft`,
`--dither off|selective`, `--dither-matrix 2|4` y
`--mode pixel|ascii-pal|ascii-rgb|ascii-bw`. Los valores manuales de columnas y colores
siempre prevalecen sobre el perfil.
Para imágenes: `python make_clip.py ../inputs/foto.jpg --image`.

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
```

En `--palette block`, el valor `0` usa `fps × 2`. El encoder mantiene en memoria solo el
bloque activo y hace que todo keyframe incluya su paleta, por lo que el seek sigue siendo
independiente y compatible con el reader v1.

`make_clip.py` usa `kmeans-rgb` por defecto: tarda más al crear el archivo, pero no agrega
ningún trabajo al navegador y en el video TKN redujo de forma clara el error de color y de
bajas frecuencias frente a MEDIANCUT. `fast-octree` es la alternativa rápida del procesador;
`median-cut` conserva el comportamiento histórico y sigue siendo el default de `encoder.py`.

El dithering selectivo se hornea como indices ASCL v1 normales: no cambia el player ni
suma CPU/GPU al reproducir. En video se admite con paleta `global` o `block`; `per-frame`
queda excluida para evitar inestabilidad temporal entre paletas.

## Reproducir

Abrí `frontend/player.html`, elegí el `.asclv` y Play. El `.asclv` ya contiene video y
audio en un único archivo. El selector de MP3 externo se conserva solamente para abrir
un `.ascl` suelto/antiguo sin perder compatibilidad. El renderer va WebGL→Canvas2D solo;
el audio es el reloj maestro (si el render se atrasa, descarta frames).

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
```
