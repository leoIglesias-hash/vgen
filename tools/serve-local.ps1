# Server HTTP local para revisar el player con el ultimo clip.asclv.
#
#   powershell -ExecutionPolicy Bypass -File tools\serve-local.ps1
#   -> http://localhost:8123/
#
# Imita el despliegue plano del TV (frontend/ como raiz, outputs/ al lado) y
# responde con Cache-Control: no-store para que el navegador siempre muestre
# el ultimo artefacto y el ultimo frontend, sin cache vieja. EXCEPCION
# (CACHE-001, F6-4): los clips versionados por contenido clip.<sha>.asclv se
# sirven immutable, como en produccion — su nombre ES su invalidacion.
# Es herramienta de revision local: no corre en CI ni en el TV.
$root = Split-Path -Parent $PSScriptRoot
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:8123/")
$listener.Start()
Write-Host "sirviendo $root (layout plano, sin cache) en http://localhost:8123/"
$types = @{ ".html"="text/html; charset=utf-8"; ".js"="application/javascript"; ".css"="text/css"; ".asclv"="application/octet-stream"; ".ascl"="application/octet-stream"; ".mp3"="audio/mpeg"; ".png"="image/png"; ".bin"="application/octet-stream"; ".md"="text/plain; charset=utf-8"; ".txt"="text/plain; charset=utf-8" }
while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
    $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
    # La raiz abre el runtime real (overlay + texto nativo), que es lo que el
    # operador revisa al cierre de cada etapa; player.html sigue en /player.html.
    if ($rel -eq "") { $rel = "live-player.html" }
    $relWin = $rel -replace '/', '\'
    $candidates = @((Join-Path $root $relWin), (Join-Path (Join-Path $root "frontend") $relWin))
    $full = $null
    foreach ($candidate in $candidates) {
      $resolved = [IO.Path]::GetFullPath($candidate)
      if ($resolved.StartsWith($root) -and (Test-Path $resolved -PathType Leaf)) { $full = $resolved; break }
    }
    if ($full) {
      $bytes = [IO.File]::ReadAllBytes($full)
      $ext = [IO.Path]::GetExtension($full).ToLower()
      if ($types.ContainsKey($ext)) { $ctx.Response.ContentType = $types[$ext] }
      if ([IO.Path]::GetFileName($full) -cmatch '^clip\.[0-9a-f]{8,64}\.asclv$') {
        $ctx.Response.Headers.Add("Cache-Control", "public, max-age=31536000, immutable")
      } else {
        $ctx.Response.Headers.Add("Cache-Control", "no-store, must-revalidate")
        $ctx.Response.Headers.Add("Pragma", "no-cache")
      }
      $ctx.Response.ContentLength64 = $bytes.Length
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
    }
    $ctx.Response.Close()
  } catch { }
}
