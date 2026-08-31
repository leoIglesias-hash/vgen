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

## Cómo se actualiza (procedimiento ejecutado el 2026-08-31)

No hace falta CI ni pegar secrets a mano: se hace entero desde acá con la API de
Cloudflare (MCP `cloudflare-api-mcp`) y `curl`. Cuatro pasos:

1. **Acuñar un token efímero** y ponerlo en el worker:
   `PUT /accounts/<id>/workers/scripts/asciline-player/secrets`
   con `{name:"UPLOAD_TOKEN", text:"<aleatorio>", type:"secret_text"}`.
2. **Subir** cada archivo: `PUT <base>/__upload/<key>` con `x-upload-token` y
   `x-sha256`. El digest se verifica de los dos lados —quien sube lo calcula y R2 lo
   recalcula del cuerpo recibido—, así que un archivo corrupto en tránsito no entra.
3. **Verificar** bajando lo servido y comparando SHA-256 contra el repo, y de paso
   comprobar que el `md5` de lo NO tocado sigue igual al de `MANIFEST.tsv`.
4. **Quemar** el token: otro `PUT` del secret con un valor aleatorio generado
   *dentro* de la llamada y nunca devuelto. Comprobar que el token viejo da `403`.

El repo **no guarda ningún token**, ni siquiera cifrado. Por eso no hay workflow de
publicación de frontend: se intentó uno con un secret de GitHub y se descartó — el
secret habría quedado persistido, que es justo lo que el modelo de trabajo prohíbe.

## Actualización del 2026-08-31 (F9)

Se subieron **24 keys**: los 4 archivos compartidos que F9 cambió
(`reader.js`, `reader-v2.js`, `render-webgl.js`, `render-canvas2d.js`) y 2 páginas
nuevas (`tv-player.html`, `diagnostic-player.html`), **por cada una de las 4
carpetas**. Los 24 quedaron verificados byte a byte contra el repo.

Fue **puramente aditiva**: los 11 archivos restantes —`live-player.html`,
`index.html`, `overlay.js`, `textlayer.js`, `slots.js`, `textfeed.js`,
`datachannel.js`, `inflate.js`, `reader-factory.js`, `tv-controller.js`,
`cache-refresh.js`— conservan exactamente el `md5` que tenían antes, comprobado
contra `MANIFEST.tsv`. No se perdió nada: overlay, textos y datachannel siguen
donde estaban.
