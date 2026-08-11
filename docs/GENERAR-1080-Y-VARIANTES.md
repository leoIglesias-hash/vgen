# Generar el 1080p pendiente y la tanda de variantes (en tu PC)

La VM de cómputo de la sesión Cowork está caída, así que el encode hay que correrlo en tu
máquina. El encoder es Python + ffmpeg (offline); no necesita internet ni servidor.

## 0) Requisitos (una sola vez)

1. **Python 3.8+** instalado y en el PATH.
2. Dependencias:
   ```bat
   cd C:\Users\Leo\Desktop\ASCILINE-video\backend
   pip install -r requirements.txt
   ```
3. **ffmpeg** como binario del sistema (no es pip). Descargá de ffmpeg.org, descomprimí y
   agregá la carpeta `bin\` al PATH. Verificá con `ffmpeg -version`.

## 1) Lo más rápido: el .bat

Doble clic en `backend\generar_1080_y_variantes.bat` (o ejecutarlo desde una consola en
`backend\`). Genera **10 clips** en `outputs\`: el 1080p pedido + las 9 variantes.

## 2) Comandos sueltos (si preferís control fino)

Desde `C:\Users\Leo\Desktop\ASCILINE-video\backend`:

```bat
set "IN=..\inputs\TKN-2434-VACANTE-gana-19 seg-.mp4"

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

```bat
cd C:\Users\Leo\Desktop\ASCILINE-video
python -m http.server 8000
```
Abrí `http://localhost:8000/frontend/player.html` y elegí cada `.asclv`, o autocargá uno:
`http://localhost:8000/frontend/player.html?src=../outputs/clip_1080_fps10.asclv`

(El player solo autocarga servido por HTTP; `file://` bloquea la lectura de otros archivos.)

## 5) Verificar sin navegador (opcional)

```bat
cd backend
python ascl_bundle.py unpack ..\outputs\clip_1080_fps10.asclv .\tmp
python ascl_decode.py .\tmp\clip_1080_fps10.ascl --mp4 .\tmp\preview.mp4
```
