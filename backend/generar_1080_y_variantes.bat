@echo off
REM ============================================================
REM  ASCILINE - Genera el 1080p pendiente + la tanda de variantes
REM  Uso: generar_1080_y_variantes.bat "ruta\al\video.mp4"
REM  Requiere: Python 3.8+ con requirements.txt instalado + ffmpeg en el PATH.
REM ============================================================
setlocal
if "%~1"=="" (
  echo Uso: %~nx0 "ruta\al\video.mp4"
  exit /b 2
)
set "IN=%~f1"
cd /d "%~dp0"

echo.
echo === 1) Clip 1080p pendiente (cols 1920, 10 fps, paleta global) ===
python make_clip.py "%IN%" --cols 1920 --fps 10 --palette global --out "..\outputs\clip_1080_fps10.asclv"

echo.
echo === 2) Tanda de variantes: cols {200,320,480} x fps {12,15,25}, pixel global ===
for %%C in (200 320 480) do (
  for %%F in (12 15 25) do (
    echo --- cols %%C @ %%F fps ---
    python make_clip.py "%IN%" --cols %%C --fps %%F --palette global --out "..\outputs\clip_%%Cc_%%Ffps.asclv"
  )
)

echo.
echo === LISTO. Revisa la carpeta outputs\ ===
dir /b "..\outputs\*.asclv"
echo.
endlocal
