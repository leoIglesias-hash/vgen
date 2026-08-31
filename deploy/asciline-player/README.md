# `deploy/asciline-player/` — copia de lo que está vivo en Cloudflare

Existe por una directiva del operador (2026-08-31): **lo desplegado tiene que estar
guardado en el repo antes de actualizarlo**. Una actualización es una mejora sobre lo
que ya hay; no puede perder nada, y no se puede volver atrás de lo que no se guardó.

Hasta esta fecha el player vivía **solo** dentro de Cloudflare: el `worker.js` no
existía en ningún lado más, y el árbol servido se armaba en `outputs/deploy-player/`,
que está en `.gitignore`. Si alguien pisaba el bucket o el worker, no había copia.

## Qué hay acá

| Archivo | Qué es |
| --- | --- |
| `worker.js` | El código **exacto** del Worker `asciline-player` desplegado, recuperado con la API. Incluye cómo redesplegarlo y las trampas que no se deducen leyéndolo. |
| `site/` | Los 15 archivos de texto que servía la **raíz** del player el 2026-08-31, bajados del bucket. Los 13 `md5` coinciden uno a uno con los `etag` del bucket. |
| `site/outputs-clip.current.txt` | El puntero CACHE-001 vivo (renombrado para no crear un `outputs/` que `.gitignore` come). |
| `MANIFEST.tsv` | Las **71** keys del bucket con tamaño y `etag`, incluidas las que no se guardan acá. |

## Lo que NO se guarda, y por qué

- **Los clips** (`*.asclv`, 4 archivos, 90 MB en total) — regla del proyecto: los videos
  de producto no van a `main`. Quedan registrados en `MANIFEST.tsv` por tamaño y `etag`,
  y sus SHA-256 están en `RUNBOOK-ESTADO.md` §Referencias de clips. Se regeneran con el
  workflow `encode`.
- **`logo.png`** — ya versionado en el repo; en el bucket hay 4 copias idénticas.

## Dos hechos que el manifiesto prueba y conviene no re-descubrir

1. **Las tres variantes (`1280-15/`, `1280-12/`, `1920-10/`) tienen copias
   byte-idénticas del código de la raíz.** Mismos `etag` en las 15 keys. Lo único
   propio de cada una es su `outputs/clip.asclv`. Cualquier actualización de código
   hay que aplicarla a las **cuatro** carpetas o quedan desparejas.
2. **`index.html` es `live-player.html`** (mismo `etag` `534abb7e…`), en las cuatro
   carpetas. O sea: lo que sirve `iargen.com/player/` es el **live-player**, no el
   `tv-player.html` que el mapa del proyecto llama «producción». `tv-player.html` no
   estaba publicado en ninguna key.

## Cómo se actualiza

`PUT /__upload/<key>` contra el worker, con `x-upload-token` (== el secret
`UPLOAD_TOKEN` del worker) y `x-sha256`. El digest se verifica de los dos lados: el
que sube lo calcula y R2 lo vuelve a calcular del cuerpo recibido. El token se rota
por la API justo antes de publicar y se **quema** después con un valor aleatorio que
no se registra en ningún lado.
