# emitir.ps1 - P-008: la emision desde la carpeta portatil, sin instalar nada.
#
#   .\emitir.cmd                       emite el pack v1 del master producto en outputs\v1
#   .\emitir.cmd -Fuente C:\clip.mp4   H-26: emite el pack v2 DESDE LA FUENTE en outputs\v2
#   .\emitir.cmd -Fuente C:\clip.mp4 -Receta "--vp9-crf 32 --h264-crf 20"      otra receta v2
#   .\emitir.cmd -Fuente C:\clip.mp4 -Receta "--barrer 28,32,36,40 --sin-piezas" la matriz v2
#   .\emitir.cmd -Out C:\algo\v1       otra carpeta de salida
#   .\emitir.cmd -Master C:\x.asclv -Sha256 <hex>   otro master (archivo o URL)
#   .\emitir.cmd -Receta "--vp9-crf 34 ..."         otra receta v1 (docs/EMISION-V1.md)
#   .\emitir.cmd -Frames 30            corte de humo (v1 y v2)
#
# Corre el MISMO tools/emit_v1.py (o emit_v2.py con -Fuente) que el CI, con el
# Python embebido y el ffmpeg del bundle. El PATH se toca solo en este proceso.
# Al final imprime el SHA-256 de cada pieza: el numero que se compara contra
# el resumen del workflow `portable`, que emite con ESTE MISMO bundle en dos
# runners de Windows. El bundle manda (P-008b, decision del operador
# 2026-09-06): si los SHA coinciden, el pack local ES el pack publicado.
# Para v2 el CI todavia no emite (H-26: "debe correr lo mismo de mi PC en CI",
# se cablea cuando terminen las optimizaciones desde la PC); mientras tanto el
# SHA local es la huella y va al REGISTRO con la receta.
#
# Windows PowerShell 5.1 alcanza (viene con Windows).

param(
  [string]$Master = "https://iargen.com/player/outputs/clip.dcd6afb66907.asclv",
  [string]$Sha256 = "dcd6afb669078a5b0d1bf4e4d42cdd2d8497ea70908a3e283183fe7d2431632a",
  [string]$Fuente = "",
  [string]$FuenteSha256 = "",
  [string]$Out = "outputs\v1",
  [string]$Receta = "--vp9-crf 38 --h264-profile high --h264-crf 23 --h264-bframes 3 --h264-refs 4",
  [string]$RecetaV2 = "--fps 20 --ancho 1280 --vp9-crf 34 --h264-crf 21 --techo 20000000",
  [int]$Frames = 0,
  [switch]$SinVerificar
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root "python\python.exe"
$ffbin = Join-Path $root "ffmpeg\bin"

# Carril: v1 (el master indexado, plan B desde H-26) o v2 (la fuente, -Fuente).
$carril = "v1"
if ($Fuente) { $carril = "v2" }
if ($carril -eq "v2") {
  $script = Join-Path $root "repo\tools\emit_v2.py"
  if (-not $PSBoundParameters.ContainsKey("Out")) { $Out = "outputs\v2" }
  if (-not $PSBoundParameters.ContainsKey("Receta")) { $Receta = $RecetaV2 }
  $manifiesto = "MANIFEST-v2.tsv"
} else {
  $script = Join-Path $root "repo\tools\emit_v1.py"
  $manifiesto = "MANIFEST-v1.tsv"
}

foreach ($p in @($python, (Join-Path $ffbin "ffmpeg.exe"), $script)) {
  if (-not (Test-Path $p)) { Write-Error "falta $p (el bundle esta incompleto)"; exit 2 }
}

# Solo este proceso ve el ffmpeg del bundle. Nada se instala ni se registra.
$env:PATH = "$ffbin;" + $env:PATH
$env:PYTHONIOENCODING = "utf-8"

function Bajar-Si-Hace-Falta([string]$origen, [string]$destino, [string]$sha) {
  # Baja `origen` a `destino` salvo que ya este y coincida con `sha`.
  $ok = $false
  if ($sha -and (Test-Path $destino)) {
    $ok = ((Get-FileHash -Algorithm SHA256 $destino).Hash.ToLower() -eq $sha.ToLower())
  }
  if (-not $ok) {
    Write-Host "bajando: $origen"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $origen -OutFile $destino
  } else {
    Write-Host "ya bajado y verificado: $destino"
  }
}

function Verificar([string]$path, [string]$sha, [string]$que) {
  if (-not (Test-Path $path)) { Write-Error "no existe $que $path"; exit 2 }
  $hash = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower()
  if ($sha -and -not $SinVerificar) {
    if ($hash -ne $sha.ToLower()) {
      Write-Error "$que no es el esperado: SHA-256 $hash (se esperaba $sha)"; exit 3
    }
    Write-Host "$que verificado: $hash"
  } else {
    Write-Host "$que SHA-256: $hash"
  }
}

$t0 = Get-Date
$work = Join-Path $root "work"
if (-not (Test-Path $work)) { New-Item -ItemType Directory -Path $work | Out-Null }

if ($carril -eq "v2") {
  $fuentePath = $Fuente
  if ($Fuente -match '^https?://') {
    $ext = [IO.Path]::GetExtension(($Fuente -split '\?')[0])
    if (-not $ext) { $ext = ".mp4" }
    $fuentePath = Join-Path $work ("fuente" + $ext)
    Bajar-Si-Hace-Falta $Fuente $fuentePath $FuenteSha256
  }
  Verificar $fuentePath $FuenteSha256 "la fuente"
  $argv = @($script, $fuentePath, "--out", $Out)
  if ($FuenteSha256 -and -not $SinVerificar) { $argv += @("--fuente-sha256", $FuenteSha256) }
} else {
  $masterPath = $Master
  if ($Master -match '^https?://') {
    $masterPath = Join-Path $work "master.asclv"
    Bajar-Si-Hace-Falta $Master $masterPath $Sha256
  }
  Verificar $masterPath $Sha256 "el master"
  $argv = @($script, $masterPath, "--out", $Out)
}

if ($Frames -gt 0) { $argv += @("--frames", "$Frames") }
if ($Receta.Trim()) { $argv += ($Receta.Trim() -split '\s+') }

Write-Host ("python " + ($argv -join " "))
& $python @argv
$codigo = $LASTEXITCODE
if ($codigo -eq 4 -and $carril -eq "v2") {
  Write-Warning "una pieza de video SUPERA EL TECHO: se emitio, no se publica (ver la nota en $manifiesto)"
} elseif ($codigo -ne 0) {
  Write-Error "$(Split-Path -Leaf $script) termino con codigo $codigo"; exit $codigo
}

$workOut = Join-Path $Out "work"
if (Test-Path $workOut) { Remove-Item -Recurse -Force $workOut }

$segundos = [int]((Get-Date) - $t0).TotalSeconds
Write-Host ""
Write-Host "-- PIEZAS $carril ($segundos s) --  SHA-256 para comparar contra el CI / el REGISTRO:"
Get-ChildItem -Path $Out -File | Where-Object { $_.Extension -in ".webm", ".mp4", ".mp3", ".m4a" } | Sort-Object Name | ForEach-Object {
  "{0}  {1,10}  {2}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $_.Length, $_.Name
}
Write-Host ""
Write-Host "manifiesto: $(Join-Path $Out $manifiesto)"
if (Test-Path (Join-Path $Out "MATRIZ-v2.tsv")) { Write-Host "matriz:     $(Join-Path $Out 'MATRIZ-v2.tsv')" }
exit $codigo
