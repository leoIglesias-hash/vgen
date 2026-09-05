# ASCILINE-hybrid → máster `.ascl`/`.asclv` + formato propio por hardware

**Sucesor de `ASCILINE-video` (2026-09-01).** El encoder Python **offline** sigue
decidiendo todo (paleta perceptual, trellis, look) y emitiendo el `.asclv` como
máster determinista; al TV viaja un **paquete propio, códec-agnóstico**, emitido
desde ese máster, cuyo video reproduce `<video>` con decodificador de **hardware**
y cuya intervención (texto, logo, canal en vivo) va en un canvas encima. El
servidor de playback no calcula nada: solo sirve archivos estáticos.

**Encoder caro, decoder sin estrés.** Norte del proyecto:
[`docs/VISION-Y-OBJETIVOS.md`](docs/VISION-Y-OBJETIVOS.md).

## Estado de esta versión

Al 2026-09-01: máster de producto **1280×720 @15 fps formato v3** (`dcd6afb6…1632a`,
24,5 MB = 62,8 % del mp4 fuente, 35,02 dB); su emisión mp4 pesa **4,1 MB** y es la
primera reproducción fluida del producto en la TV box real (DIAG-002/003). Fases
F0-F9 del paradigma anterior cerradas y verificadas; en curso la **fase H**. El
**pack v0** ya está emitido y publicado (`https://iargen.com/player/v0/`): cuatro
piezas —H.264 Baseline y Main, VP9 y VP9 con alfa— más los empaquetados **HLS y
DASH** obtenidos por remux, y la página que las reproduce y mide. **La TV box ya
la reprodujo** (2026-09-01): todo lo progresivo fluido por hardware, Main =
Baseline (decodificador hardware), arranque atado a los bytes por red (517 ms
desde `blob:`), VP9 reproduce, HLS-TS nativo sí, DASH no, MSE sin probar. El
rumbo que sale de ahí está en
[`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md); el
estado vivo en [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md). Una publicación
pública sigue condicionada por licencia, procedencia y derechos de los videos.

La compatibilidad legacy es un objetivo verificado por sintaxis/API y fallbacks:
frontend ES5, XHR, Canvas2D como piso. El player 100 % JS anterior se mantiene
como reproductor de escritorio y banco de verificación del máster.

El índice de documentación está en [`docs/README.md`](docs/README.md); los diseños
del paradigma anterior, en [`docs/historico/`](docs/historico/README.md).

## Estructura

```
ASCILINE-hybrid/
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

# Reducir bandas sin agregar una etapa perceptual al navegador (solo mode pixel).
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
el procesamiento. Elegir exacto o LUT no agrega algoritmos ni buffers al navegador; el
costo efectivo del archivo resultante depende de sus cambios y debe medirse en el TV.

`make_clip.py` usa `kmeans-rgb` por defecto: tarda más al crear el archivo, pero no agrega
una etapa nueva al navegador y en el video TKN redujo de forma clara el error de color y de
bajas frecuencias frente a MEDIANCUT. `fast-octree` es la alternativa rápida del procesador;
`median-cut` conserva el comportamiento histórico y sigue siendo el default de `encoder.py`.

El dithering selectivo se hornea como indices ASCL v1 normales: no cambia el player ni
agrega un algoritmo de dither al reproducir. Sí puede modificar entropia, bytes y cantidad
de celdas sucias, por lo que su costo efectivo queda sujeto al presupuesto y a TV-02. En
video se admite con paleta `global` o `block`; `per-frame` queda excluida para evitar
inestabilidad temporal entre paletas.

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

- [`CLAUDE.md`](CLAUDE.md): guía de arranque de sesión, modelo de trabajo e invariantes.
- [`docs/VISION-Y-OBJETIVOS.md`](docs/VISION-Y-OBJETIVOS.md): **el norte** — qué
  construimos, de qué linaje sale cada pieza, escalera de intervención, no-objetivos.
- [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md): estado vivo — próxima acción, una
  fila por tarea cerrada, SHAs de referencia.
- [`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md): **el rumbo** —
  evidencia medida, caminos de runtime, gates numéricos, orden de tareas y decisiones
  pendientes del operador.
- [`docs/RUNBOOK-IMPLEMENTACION.md`](docs/RUNBOOK-IMPLEMENTACION.md): reglas de ejecución
  y tareas de la fase H (H-9 cerrada; H-10 abierta con la caja medida; H-13, H-11, H-12,
  H-6, H-7, H-8, H-14, W-26).
- [`docs/EMISION-V0.md`](docs/EMISION-V0.md): el primer video — qué le tomamos a cada
  códec y las suposiciones, cada una con su refutación escrita.
- [`docs/PLAN-DE-MEDICION.md`](docs/PLAN-DE-MEDICION.md): sondas, banco de reproducción y
  registro de aparatos — lo que desbloquea al formato.
- [`docs/DISENO-FORMATO-VGEN.md`](docs/DISENO-FORMATO-VGEN.md): el formato en obra, con
  la tabla de decidido vs. gateado por medición.
- [`docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md):
  decisiones append-only, por Instancia.
- [`docs/ejecutados/`](docs/ejecutados/README.md): resumen por fase cerrada.
- [`docs/ASCL-format-spec.md`](docs/ASCL-format-spec.md): formato máster v1 y revisión v2.
- [`docs/historico/`](docs/historico/README.md): diseños y planes del paradigma
  100 % JS, archivados verbatim el 2026-09-01.
- [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md): hosting y caché.

El índice completo está en [`docs/README.md`](docs/README.md).

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
de control remoto— o con la pestaña translúcida **MENU** de la esquina inferior izquierda.
**Limpiar caché / descargar de nuevo** libera primero reader, audio, Canvas y recursos GPU;
después rota un token de consulta y solicita revalidación HTTP. Esto renueva solamente ese
ASCLV: JavaScript no puede borrar la caché global ni sus entradas anteriores. En browsers
legacy, `keyCode=9` se conserva como Tab y no abre el menú; el hotspot sigue disponible.
Hay que desplegar `cache-refresh.js` junto con los demás archivos de frontend.

El servidor PHP existente debe publicar el clip en esa ruta relativa. El artefacto local
de esta entrega también se llama `outputs/clip.asclv`; ese nombre estable no forma parte
del contenido binario.
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

`outputs/clip.asclv` está ignorado por Git para no engordar cada commit. Un clon limpio
puede generar una prueba libre y pequeña con:

```bash
python backend/make_clip.py inputs/synthetic.mp4 --format v2 \
  --out outputs/synthetic-v2.asclv --cols 64 --fps 10 \
  --palette global --palette-size 32
```

Ese archivo se abre desde el selector del player tradicional. Para probar específicamente
la ruta fija de `tv-player.html` en un clon limpio, cambie solo `--out` por
`outputs/clip.asclv`. No use esa variante dentro del workspace de release: reemplazaría el
HQ local que usa la misma ruta estable.

El HQ exacto se distribuye como asset de release solo después de confirmar los derechos
del video; su hash y tamaño están en `docs/RUNBOOK-ESTADO.md` (Referencias de clips).

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

Requieren Python 3.8+ con `backend/requirements.txt` y Node.js 20 en el entorno de
desarrollo. El frontend desplegado no necesita Node ni Python.

```bash
pip install -r backend/requirements.txt
python tests/run_all.py

# Gate local de release: además exige outputs/clip.asclv.
python tests/run_all.py --require-release-artifact
```

El workflow de CI (`regression`) corre la misma regresión en cada push, sin descargar
videos de producto ni iniciar servidores. El workflow `encode` (dispatch manual) genera
el clip de producto desde la rama `assets` y publica artifacts con SHA y preview.

## Cómo colaborar (repositorio público de solo lectura)

Este repositorio se puede **leer, clonar y correr entero**; nadie de afuera
escribe en él. Lo que buscamos de afuera son **ideas**: el espacio para eso es
[`PROPUESTAS.md`](PROPUESTAS.md), y la puerta de entrada es un *issue* con la
plantilla «Propuesta» (problema, idea, qué compra, qué cuesta, cómo se mide,
qué la refutaría). Una propuesta se adopta cuando tiene **una fila medida** en
un aparato real; hasta entonces es una apuesta escrita, que también vale.

Para reproducir lo que hay:

- **Leer:** empezá por [`docs/VISION-Y-OBJETIVOS.md`](docs/VISION-Y-OBJETIVOS.md)
  (qué es el formato), después
  [`docs/PLAN-IMPLEMENTACION-VGEN.md`](docs/PLAN-IMPLEMENTACION-VGEN.md) (evidencia
  medida y gates) y el estado vivo en [`docs/RUNBOOK-ESTADO.md`](docs/RUNBOOK-ESTADO.md).
  Toda decisión tiene su porqué en
  [`docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md`](docs/REGISTRO-DE-PRUEBAS-Y-DECISIONES.md).
- **Correr:** `python tests/run_all.py` (Python 3.8+ y Node 20) corre la misma
  regresión que el CI. Los workflows `emitir-v0`, `matriz-h6` y `emitir-v1`
  (carpeta `.github/workflows/`) emiten los packs desde el máster publicado; se
  pueden correr en un *fork* sin ningún secreto.
- **Mirar:** la página de banco está en producción en
  `https://iargen.com/player/v0/` con el manual de teclas en
  [`docs/MANUAL-TECLAS-V0.md`](docs/MANUAL-TECLAS-V0.md).

Reglas que no se negocian, porque el parque las impone: frontend **ES5.1
estricto** (Chromium 70 en las cajas), **`<video>` como única puerta al
hardware**, **determinismo** (mismo máster → mismos bytes, en cualquier máquina)
y todo lo caro **offline**. Lo que necesita pantalla lo firma el operador del
proyecto, que es quien tiene los aparatos.

## Licencia

La licencia de publicación todavía no está definida. El proyecto declara una relación
conceptual con [`YusufB5/ASCILINE`](https://github.com/YusufB5/ASCILINE), cuyo
[`LICENSE`](https://github.com/YusufB5/ASCILINE/blob/main/LICENSE) agrega una restricción
de publicidad a MIT. No debe agregarse una licencia genérica ni hacerse un release público
hasta resolver procedencia, atribución y compatibilidad de uso (PUB-001, abierta).
