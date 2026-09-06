@echo off
rem P-008: doble clic o linea de comando; pasa todo a emitir.ps1 (Windows PowerShell 5.1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0emitir.ps1" %*
