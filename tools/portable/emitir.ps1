# emitir.ps1 - P-008: la emision v1 desde la carpeta portatil, sin instalar nada.
#
#   .\emitir.cmd                       emite el pack v1 del master producto en outputs\v1
#   .\emitir.cmd -Out C:\algo\v1       otra carpeta de salida
#   .\emitir.cmd -Master C:\x.asclv -Sha256 <hex>   otro master (archivo o URL)
#   .\emitir.cmd -Receta "--vp9-crf 34 ..."         otra receta (docs/EMISION-V1.md)
#   .\emitir.cmd -Frames 30            corte de humo
#
# Corre el MISMO tools/emit_v1.py que el CI, con el Python embebido y el ffmpeg
# del bundle. El PATH se toca solo en este proceso. Al final imprime el SHA-256
# de cada pieza: el numero que se compara contra el resumen del workflow
# `portable` / `emitir-v1` (el CI es el arbitro de bytes).
#
# Windows PowerShell 5.1 alcanza (viene con Windows).

param(
  [string]$Master = "https://iargen.com/player/outputs/clip.dcd6afb66907.asclv",
  [string]$Sha256 = "dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a",
  [string]$Out = "outputs\v1",
  [string]$Receta = "--vp9-crf 38 --h264-profile high --h264-crf 23 --h264-bframes 3 --h264-refs 4",
  [int]$Frames = 0,
  [switch]$SinVerificar
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "python\python.exe"
$ffbin = Join-Path $root "ffmpeg\bin"
$script = Join-Path $root "repo\tools\emit_v1.py"

foreach ($p in @($python, (Join-Path $ffbin "ffmpeg.exe"), $script)) {
  if (-not (Test-Path $p)) { Write-Error "falta $p (el bundle esta incompleto)"; exit 2 }
}

# Solo este proceso ve el ffmpeg del bundle. Nada se instala ni se registra.
$env:PATH = "$ffbin;" + $env:PATH
$env:PYTHONIOENCODING = "utf-8"

$t0 = Get-Date
$masterPath = $Master
if ($Master -match '^https?://') {
  $work = Join-Path $root "work"
  if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work | Out-Null }
  $masterPath = Join-Path $work "master.asclv"
  $ok = $false
  if ($Sha256 -and (Test-Path $masterPath)) {
    $ok = ((Get-FileHash -Algorithm SHA256 $masterPath).Hash.ToLower() -eq $Sha256.ToLower())
  }
  if (-not $ok) {
    Write-Host "bajando el master: $Master"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Master -OutFile $masterPath
  } else {
    Write-Host "master ya bajado y verificado: $masterPath"
  }
}
if (-not (Test-Path $masterPath)) { Write-Error "no existe el master $masterPath"; exit 2 }

if ($Sha256 -and -not $SinVerificar) {
  $hash = (Get-FileHash -Algorithm SHA256 $masterPath).Hash.ToLower()
  if ($hash -ne $Sha256.ToLower()) {
    Write-Error "el master no es el esperado: SHA-256 $hash (se esperaba $Sha256)"; exit 3
  }
  Write-Host "master verificado: $hash"
}

$argv = @($script, $masterPath, "--out", $Out)
if ($Frames -gt 0) { $argv += @("--frames", "$Frames") }
if ($Receta.Trim()) { $argv += ($Receta.Trim() -split '\s+') }

Write-Host ("python " + ($argv -join " "))
& $python @argv
if ($LASTEXITCODE -ne 0) { Write-Error "emit_v1.py termino con codigo $LASTEXITCODE"; exit $LASTEXITCODE }

$workOut = Join-Path $Out "work"
if (Test-Path $workOut) { Remove-Item -Recurse -Force $workOut }

$segundos = [int]((Get-Date) - $t0).TotalSeconds
Write-Host ""
Write-Host "-- PIEZAS ($segundos s) --  SHA-256 para comparar contra el CI:"
Get-ChildItem -Path $Out -File | Where-Object { $_.Extension -in ".webm", ".mp4", ".mp3" } | Sort-Object Name | ForEach-Object {
  "{0}  {1,10}  {2}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Length, $_.Name
}
Write-Host ""
Write-Host "manifiesto: $(Join-Path $Out 'MANIFEST-v1.tsv')"
