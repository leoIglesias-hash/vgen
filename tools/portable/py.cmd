@echo off
rem P-008: el Python embebido del bundle con el ffmpeg del bundle en el PATH (solo este proceso).
rem   py.cmd repo\tools\emit_v1.py master.asclv --out outputs\v1 ...
rem   py.cmd repo\backend\encoder.py ...      (la mitad A: el master)
setlocal
set "ROOT=%~dp0"
set "PATH=%ROOT%ffmpeg\bin;%PATH%"
set "PYTHONIOENCODING=utf-8"
"%ROOT%python\python.exe" %*
