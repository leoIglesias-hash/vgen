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

## Actualización del 2026-08-31 (F9, segundo acto — motor único)

Se subieron **28 keys** = 7 por cada una de las 4 carpetas:

| Archivo | Por qué |
| --- | --- |
| `live-player.html` + `index.html` | W-24: la raíz estrena cadencia y pre-decode (son la misma copia, dos keys) |
| `tv-player.html`, `diagnostic-player.html` | W-23: pasan a usar el motor compartido |
| `overlay.js` | W-24: método `rebind()`, que hace legal el intercambio de readers con overlay activo |
| `playloop.js` | **nuevo** — el motor compartido (W-22) |
| `player.html` | **nuevo** — no estaba publicado en ninguna carpeta; ahora el árbol servido coincide con el repo |

**El número salió de auditar, no de estimar.** Se bajaron los 18 archivos de las 4
carpetas y se comparó SHA-256 contra el repo: 4 diferían, 2 daban 404 y el resto estaba
igual. Los runbooks decían «25 keys»; eran 28. Vale la pena repetir esa auditoría antes
de cada publicación en vez de confiar en la cuenta escrita.

Aditiva otra vez: ningún archivo fuera de esos 7 se tocó. Las 28 keys quedaron
verificadas byte a byte contra el repo después de subirlas, y el token se quemó (el viejo
da `403`). **Ojo con el burn:** el secret tarda unos segundos en propagarse — el primer
`PUT` con el token viejo puede devolver `200` todavía. Hay que reintentar hasta ver el
`403`, no darlo por quemado con una sola prueba.

## Actualización del 2026-09-01 (H-10, pack v0)

**El worker se redesplegó** —primera vez desde que existe esta copia— con dos
agregados y nada más. La copia de `worker.js` de acá se actualizó y se commiteó
**antes** de desplegar, como manda la directiva:

1. **Tipos de video**: `mp4`, `webm` y `tsv` en la tabla `TYPES`. Antes, toda
   extensión desconocida salía `application/octet-stream`, y servir el pack v0
   así habría dado un **falso negativo**: varios WebViews de TV miran el
   `content-type` antes de decidir si pueden reproducir.
2. **`Range`**: `206` con `content-range`, `416` fuera de rango y
   `accept-ranges: bytes` también en las respuestas completas. Hay reproductores
   de TV que directamente no arrancan un video si el servidor no sirve rangos, y
   el que arranca no puede buscar. La rama sin `Range` quedó idéntica.

Verificado después del despliegue: la raíz sigue devolviendo el mismo
`live-player.html` (200, 26.679 B), `playloop.js` sale con su `content-type` de
siempre, un `Range: bytes=0-99` devuelve `206 · bytes 0-99/10999`, y **el secret
`UPLOAD_TOKEN` sobrevivió al redeploy** (se envió `keep_bindings:
["secret_text"]`; las bindings quedaron en `BUCKET` + `UPLOAD_TOKEN`).

**Se subieron 6 keys nuevas bajo el prefijo `v0/`** (pack v0 de H-9):
`index.html` (copia de `frontend/v0.html`), `MANIFEST.tsv` y las cuatro piezas
de video. Las cuatro piezas están listadas en `MANIFEST.tsv` pero **no se guardan
acá**, por la regla de que los videos no van a `main`; se regeneran con el
workflow `emitir-v0` desde el máster, y sus SHA-256 están en el REGISTRO.

Verificación: se bajaron las 6 y se comparó **SHA-256 contra el archivo local** —
las 6 idénticas, con `video/mp4` y `video/webm` correctos. El token se quemó y el
viejo dio `403` en el primer intento.

Queda servido en **`https://iargen.com/player/v0/`**.

## Actualización del 2026-09-01 (mando numérico y lanzador)

**2 keys** más bajo `v0/`: `index.html` (regenerada, ahora con teclas numéricas)
y **`keypad.js`** (nueva, el mando compartido). El bucket queda con **60 keys**
en `v0/`. Verificadas bajando y comparando SHA-256 contra el archivo local;
token efímero quemado (403 al primer intento).

**Lo que NO se publicó acá, a propósito:** `frontend/ir.html`, el lanzador. Por
decisión del operador va en **otro servidor**, así que se le entregó como archivo
suelto. Por eso es autocontenido (no carga `keypad.js`) y usa **URLs absolutas**
hacia `https://iargen.com/player/`: desde otro dominio una ruta relativa no llega
a ningún lado. Si alguna vez se decide publicarlo también acá, la key natural
sería `ir/index.html` y habría que subir `ir/keypad.js` al lado **solo** si antes
se lo convierte en no-autocontenido — hoy no hace falta.

**Cuidado al verificar tipos MIME después de tocar el worker:** la primera
comprobación de un `.m4s` dio `application/octet-stream` por **caché de borde**;
con un parámetro anti-caché salió `video/iso.segment`. Verificar siempre con
cache-buster, o se concluye lo contrario de lo que pasa.

## Actualización del 2026-09-01, noche (H-13, por dónde entra el paquete)

**2 keys** bajo `v0/`: `index.html` (regenerada = `frontend/v0.html` con las
teclas `96`/`97`/`98`/`8`/`99` y el `5`, columnas `congel`/`cambio_ms`, sin pausa
al terminar) y **`vgenfeed.js`** (nueva: MSE, Blob concatenado y cambio por
`src`; el módulo que H-8 reusa). `keypad.js` no se tocó (`md5` igual). El bucket
queda con **61 keys** en `v0/`. Orden respetado: las dos estaban commiteadas en
`main` (`b3d5837`, CI verde) **antes** de subir. Verificadas bajando con
cache-buster y comparando SHA-256 contra el archivo local: idénticas, con
`text/html` y `application/javascript`. Token efímero acuñado por la API,
usado para las dos subidas y quemado en la misma sesión (403 comprobado con el
token viejo, reintentando hasta verlo).

Nada nuevo que emitir: las cinco pruebas usan `v0/dash/init.m4s` +
`v0/dash/chunk-*.m4s`, que ya estaban publicados.

## Actualización del 2026-09-01, noche (H-11, la capa encima del video)

Una key reemplazada bajo `v0/` (el resto del prefijo queda igual; siguen siendo
61 keys):

| key | bytes | md5 | qué cambia |
|---|---|---|---|
| `v0/index.html` | 37981 | `050c910fb354e184f9f8804dd345ee09` | H-11: `<canvas id="capa">` encima del `<video>` dimensionado al panel; cargas nada / rect 15 fps / pantalla una vez sobre Baseline y VP9; teclas `930` (lote de la visita: capa ×6 + `blob:` + `blob concat`), `931`, `932`, `933` (a ojo); contador `oculto`; el `1` incluye las seis |

Verificación tras subir: `GET https://iargen.com/player/v0/index.html?x=<nonce>`
→ SHA-256 igual al del archivo local; token de subida quemado después.

## Actualización del 2026-09-02 (H-11, corrección del mando y de la leyenda)

La misma key de siempre bajo `v0/` (siguen siendo 61 keys):

| key | bytes | md5 | qué cambia |
|---|---|---|---|
| `v0/index.html` | 40410 | `9e6a24caa16de69af9dbe40f3f692807` | teclas de la capa a dos cifras (`80` lote de la visita, `81` baseline, `82` vp9, `83` a ojo; el `8` pasa a ser puerta y espera 900 ms u OK); leyenda por tier (`now` grande y arriba, `tool`, `done` chico), agrupada y sin desbordar sobre el zócalo |

Verificación tras subir: `GET https://iargen.com/player/v0/index.html?x=<nonce>`
→ SHA-256 igual al del archivo local; token de subida quemado después.
