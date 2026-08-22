# Generar el 1080p pendiente y la tanda de variantes (en tu PC)

> **Documento histórico.** Este procedimiento corresponde al pipeline global anterior.
> El backlog vigente está en `HOJA-DE-RUTA-TECNICA-V2.md`.

Este procedimiento se ejecuta offline en la PC que procesa el video. El encoder usa Python
y FFmpeg; no necesita internet ni un servidor de reproducción.

## 0) Requisitos (una sola vez)

1. **Python 3.8+** instalado y en el PATH.
2. Dependencias:
   ```bat
   cd ruta\al\repositorio\backend
   pip install -r requirements.txt
   ```
3. **ffmpeg** como binario del sistema (no es pip). Descargá de ffmpeg.org, descomprimí y
   agregá la carpeta `bin\` al PATH. Verificá con `ffmpeg -version`.

## 1) Helper histórico de variantes

Desde una consola, el helper recibe explícitamente la fuente y genera **10 clips** en
`outputs\`: el 1080p pedido + las 9 variantes.

```bat
backend\generar_1080_y_variantes.bat "inputs\video.mp4"
```

## 2) Comandos sueltos (si preferís control fino)

Desde la carpeta `backend\` del repositorio:

```bat
set "IN=..\inputs\video.mp4"

:: El 1080p pendiente (cols 1920, 10 fps, paleta global)
python make_clip.py "%IN%" --cols 1920 --fps 10 --palette global --out "..\outputs\clip_1080_fps10.asclv"

:: Variantes para evaluar peso (pixel global)
python make_clip.py "%IN%" --cols 200 --fps 12 --palette global --out "..\outputs\clip_200c_12fps.asclv"
python make_clip.py "%IN%" --cols 200 --fps 15 --palette global --out "..\outputs\clip_200c_15fps.asclv"
python make_clip.py "%IN%" --cols 200 --fps 25 --palette global --out "..\outputs\clip_200c_25fps.asclv"
python make_clip.py "%IN%" --cols 320 --fps 12 --palette global --out "..\outputs\clip_320c_12fps.asclv"
python make_clip.py "%IN%" --cols 320 --fps 15 --palette global --out "..\outputs\clip_320c_15fps.asclv"
python make_clip.py "%IN%" --cols 320 --fps 25 --palette global --out "..\outputs\clip_320c_25fps.asclv"
python make_clip.py "%IN%" --cols 480 --fps 12 --palette global --out "..\outputs\clip_480c_12fps.asclv"
python make_clip.py "%IN%" --cols 480 --fps 15 --palette global --out "..\outputs\clip_480c_15fps.asclv"
python make_clip.py "%IN%" --cols 480 --fps 25 --palette global --out "..\outputs\clip_480c_25fps.asclv"
```

Notas:
- La fuente es **25 fps**, así que 25 es el tope; pedir más no agrega nada.
- `rows` se calcula solo desde `cols` y el aspecto 16:9 (1920→1080, 480→270, 320→180, 200→112).
- Cada `make_clip.py` imprime al final: dimensiones, nº de frames, paleta y **peso + KB/s**.
  Anotá esa línea de cada corrida para armar la tabla comparativa.

## 3) Qué esperar (referencia)

Único dato medido real: **320×180 @15fps global+DELTA → 7.13 MB (.ascl) + 233 KB audio = ~7.5 MB, ~435 KB/s**.
Es un clip de **alto movimiento**, así que DELTA casi no ayuda y pesa bastante. Como referencia
relativa, el peso crece ~ con `cols² × fps`:

| cols | rows  | celdas/frame | peso relativo aprox (vs 320@15) |
|------|-------|--------------|---------------------------------|
| 200  | 112   | 22 K         | ~0.4× a 15fps                   |
| 320  | 180   | 58 K         | 1× (≈7.5 MB @15fps)             |
| 480  | 270   | 130 K        | ~2.2× a 15fps                   |
| 1920 | 1080  | 2.07 M       | mucho mayor (es el target real) |

El factor fps es casi lineal: 12fps ≈ 0.8×, 25fps ≈ 1.7× respecto de 15fps. Son estimaciones
groseras; el peso real lo da el KB/s que imprime cada corrida (depende del movimiento).

## 4) Reproducir y comparar

Publicá `frontend/` y `outputs/` en el servidor PHP/Apache existente según
`DESPLIEGUE.md`. El proyecto no inicia ni incluye un servidor auxiliar. El player
tradicional también permite elegir un `.asclv` local mediante el selector de archivo.

## 5) Verificar sin navegador (opcional)

```bat
cd backend
python ascl_bundle.py unpack ..\outputs\clip_1080_fps10.asclv .\tmp
python ascl_decode.py .\tmp\clip_1080_fps10.ascl --mp4 .\tmp\preview.mp4
```
