# S-7 — barrido de resolución + deploy del player a Cloudflare — CERRADOS

Dos cierres entrelazados (2026-08-30/31): el barrido de resolución definió el producto
y el hosting público permitió validarlo con el pipeline JS real (no solo previews).

## S-7 — barrido 768 → 1280 → 1920 (Instancia 028, cerrada 2026-08-31)

- Tres escalones con la receta de producto de F5, todos aprobados a ojo por el
  operador: **1280@15** «quedó perfecto» (`2a9201bf…b778`, 24.530.460 B = 63,0 %
  de la fuente, 35,02 dB), **1280@12** «casi ni se nota» (`27ae0019…e828`,
  21.196.032 B = 54,4 %), **1920@10** «espectacular» (`87160987…8d4e`,
  32.838.265 B = 84,3 %, wall 1:02:07, RSS 3,35 GB).
- **Definición del operador (regla 9): el producto pasa a 1280 @15 fps.** El 1920 NO
  quedó por FLUIDEZ a 10 fps («se pone un poco trabado»), no por imagen — **vuelve
  como prueba futura a más fps y el front debe procesar cualquier resolución/fps que
  se le tire** (directiva; 1920×1080 entra holgado en el reader y reproduce en
  navegador; el TV físico se valida en F8-2).
- Hallazgo de referencia: la tasa por celda **CAE** al subir resolución
  (0,1451 → 0,1144 → 0,1023 B/celda/frame) — las estimaciones lineales son pesimistas.
- Preparación: `timeout-minutes` del workflow encode 120 → 350 (`2260d21`).
- El re-encode del producto se difirió al cierre de S-4 y **se ejecutó**
  (v3 + tile=sweep → `dcd6afb6…1632a`, ver
  [`2026-08-31-F6-formato-v3-S4.md`](2026-08-31-F6-formato-v3-S4.md)).

## Deploy del player (cerrado 2026-08-30; raíz actualizada a v3 el 31)

Directiva del operador: «de lo que hay activo en Cloudflare no toques nada, solo es
agregar» — todo lo creado es NUEVO; homepage de iargen.com intacto.

- **URLs**: `https://iargen.com/player/` (raíz = PRODUCTO, hoy 1280@15 **v3** vía
  puntero CACHE-001), `/player/1280-15/` (v2), `/player/1280-12/`, `/player/1920-10/`;
  espejo `https://asciline-player.iargen.workers.dev/`.
- **Infra**: bucket R2 `asciline-player` + Worker `asciline-player` (file-server
  ES-modules, binding `BUCKET`, ETag/304, strip de `/player`, regla immutable para
  `clip.<hex>.asclv`), ruta `iargen.com/player*` en la zona. R2 en vez de Pages/KV
  por el límite de 25 MB.
- **Subir clips (sin redeploy)**: (a) manual — rotar el secret `UPLOAD_TOKEN` vía API
  y `PUT /__upload/<key>` con `x-upload-token` + `x-sha256` (R2 verifica el digest en
  el put); (b) desde CI — workflow `publish-player` autorizado POR CONTENIDO (pin
  key+SHA-256 cargado antes y retirado después). **Ningún token se persiste jamás**:
  se rota antes de subir y se quema después con un valor aleatorio no registrado.
  Mejora anotada: `__pins.json` en el bucket si (b) se vuelve habitual.
- Reproducción verificada en navegador en las 4 resoluciones; el detalle operativo
  vive también en la memoria de sesión `proximo-deploy-player-cloudflare`.

Evidencia: REGISTRO Instancia 028 + bitácora archivada (filas 2026-08-30) en
[`2026-08-31-tablas-de-tareas-cerradas.md`](2026-08-31-tablas-de-tareas-cerradas.md).
Pendiente del operador: probar el player en celular y Smart TV (antesala de F8).
