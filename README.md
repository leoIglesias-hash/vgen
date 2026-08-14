# ASCILINE → `.ascl` / `.asclv`

Convierte imagen o video a una grilla de texto/bloques de color y la reproduce en el
navegador (incluso webviews viejos), **pre-encodeando offline**: el servidor de playback
no calcula nada, solo sirve archivos estáticos.

## Estructura

```
ASCILINE-video/
├── frontend/     # lo que corre en el navegador (SOLO esto para reproducir)
│   ├── player.html
│   ├── tv-player.html       # fullscreen y precarga con URL estable
│   ├── tv-controller.js     # teclas/click y fullscreen con prefijos legacy
│   ├── cache-refresh.js     # renovación compatible del ASCLV con el mismo nombre
│   ├── inflate.js          # descompresor zlib propio (ES5)
│   ├── reader.js           # ReaderV1: RAW/ZLIB/DELTA/DELTA_MASK + seek
│   ├── reader-v2.js        # ReaderV2 ES5: tiles/predictores + fallback v1
│   ├── reader-factory.js   # despacho por version interior 1/2
│   ├── render-webgl.js     # renderer WebGL (rompe el techo de 360p)
│   └── render-canvas2d.js  # fallback Canvas2D (mosaico + glifos ASCII)
├── backend/      # lo que CREA los archivos (Python, offline)
│   ├── encoder.py          # imagen/video -> .ascl  (+ audio .mp3 aparte)
│   ├── ascl_decode.py      # decoder/verificador de referencia + preview
│   ├── ascl_bundle.py      # empaqueta .ascl + .mp3 -> .asclv (un archivo)
│   ├── regional_codec_v2.py # codec regional lossless de referencia
│   ├── ascl_v2.py          # transcode exacto v1 -> v2 + decoder Python
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

El formato predeterminado sigue siendo **v1**. La primera revisión v2 se solicita de
forma explícita:

```bash
python make_clip.py "../inputs/mi-video.mp4" --format v2 \
  --out ../outputs/mi-video-v2.asclv

# Convertir un ASCLV v1 existente sin volver a cuantizar y copiando su audio exacto:
python ascl_v2.py ../outputs/mi-video.asclv ../outputs/mi-video-v2.asclv
```

`--format v2` crea primero la matriz v1 aprobada y después elige, frame por frame, una
representación regional/predictiva solo si es lossless y estrictamente menor. Los tags
v1 permanecen como fallback, por lo que el bundle v2 no crece frente a esa entrada v1.
No hay inspección visual ni IA en esta decisión. V2 inicial solo admite `mode pixel`.

Opciones principales: `--format v1|v2` (default `v1`),
`--profile detail|balanced|graphic|graphic-hq|graphic-ultra|color|custom`,
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
- `docs/ASCL-format-spec.md`: formato v1 y primera revisión v2.
- `docs/DISENO-ASCL-V2-TILES.md`: contrato v2 implementado, límites y pendientes.
- `docs/BENCHMARK-V2-HQ-768.md`: evidencia exacta reproducible del primer HQ v2.
- `docs/DISENO-PLANIFICADOR-REGIONAL-V2.md`: selección píxel/máscara/bloque y
  near-lossless temporal propuesto para v2.
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

La factory abre v1 con `reader.js` y v2 con `reader-v2.js`; ambos usan los mismos
renderers. ReaderV2 conserva tags v1 como fallback, agrega tiles de 16, predictores
reversibles y CRC de header+cuerpo. Su dirty set híbrido combina celdas exactas y tiles
sin duplicar la capa de video. Todo el frontend usa sintaxis ES5 compatible con el piso
ECMAScript 2015.

El reader v1 evita arrays JavaScript por frame, valida la estructura y, cuando está
presente/no nulo, el CRC antes de decodificar. Descomprime en un scratch tipado
reutilizable. Los deltas conservan un
bitset de celdas modificadas: Canvas2D y WebGL1 convierten únicamente esos índices al
RGBA persistente y presentan la misma banda lógica. Estas optimizaciones del camino v1 no
reescriben el `.asclv`.
Una pérdida de contexto o un fallo WebGL durante playback degrada al mismo frame en
Canvas2D sin reiniciar el reloj.

### Prueba directa en Smart TV

`frontend/tv-player.html` es el frontend sin controles de laboratorio. Precarga
`./outputs/clip.asclv`, ajusta el video a la pantalla sin
deformarlo y entra
en fullscreen/reproduce al presionar una tecla del `1` al `8` o al hacer click/toque.
Incluye un boton pequeno **Iniciar descarga** para repetir manualmente la precarga desde
un gesto del control remoto. Si la red falla, tanto ese boton como un nuevo click en la
pantalla vuelven a intentar la descarga sin recargar la pagina.

El menú técnico queda oculto. Se abre con la tecla `9` —también numpad y códigos modernos
de control remoto— o con el hotspot transparente de la esquina inferior izquierda.
**Limpiar caché / descargar de nuevo** libera primero reader, audio, Canvas y recursos GPU;
después rota un token de consulta y solicita revalidación HTTP. Esto renueva solamente ese
ASCLV: JavaScript no puede borrar la caché global ni sus entradas anteriores. En browsers
legacy, `keyCode=9` se conserva como Tab y no abre el menú; el hotspot sigue disponible.
Hay que desplegar `cache-refresh.js` junto con los demás archivos de frontend.

El servidor PHP existente debe publicar el clip en esa ruta relativa. El archivo
versionado conserva su nombre original; `clip.asclv` es solamente su nombre al subirlo.
Como `./outputs/clip.asclv` se resuelve desde la URL del HTML, el despliegue recomendado
pone los archivos de `frontend/` en el mismo directorio público que la carpeta
`outputs/`. Si el HTML se publica como `/frontend/tv-player.html`, el clip debe existir
en `/frontend/outputs/clip.asclv` o el servidor debe mapear esa ruta.
La pagina tambien acepta:

```text
frontend/tv-player.html?renderer=canvas2d
frontend/tv-player.html?loop=0
```

El demo usa loop por defecto. WebGL1 se intenta primero y Canvas2D conserva la misma
funcionalidad como fallback. Tanto v1 como v2 se descargan completos por XHR antes de
reproducir y se cachean como un único recurso; esta revisión no implementa streaming ni
carga HTTP parcial.

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
node tests/test_reader_safety.js
node tests/test_cache_refresh.js
node tests/test_tv_controller.js
node tests/test_tv_player_page.js
node tests/test_tv_player_runtime.js
node tests/test_reader_v2.js
node tests/test_reader_factory.js
```
