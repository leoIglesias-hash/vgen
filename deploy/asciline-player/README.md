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

## Actualización del 2026-09-02 (H-12, la caché)

**2 keys** bajo `v0/`: `index.html` (regenerada = `frontend/v0.html` con las
teclas `84`/`85`/`86`, la cabecera `cache` y la leyenda de siete `now`) y
**`vgencache.js`** (nueva: la puerta a IndexedDB). El bucket queda con
**62 keys**. Orden respetado: las dos estaban commiteadas en `main` antes de
subirlas.

| key | bytes | md5 | qué es |
|---|---|---|---|
| `v0/index.html` | 50860 | `ecd7849b29ff8277b4c5986af05b4e3b` | H-12: `84` guardar + desde caché + techo, `85` desde caché (tras reiniciar), `86` borrar; filas sin video no son «ciegas» |
| `v0/vgencache.js` | 10281 | `a427ea837d9760ad02cf63a813b8e33d` | IndexedDB: bajada con progreso, pineo por contenido, poda, techo, cuota |

Verificación tras subir: `GET https://iargen.com/player/v0/<key>?x=<nonce>`
→ SHA-256 igual al del archivo local en las dos; token de subida quemado.

## Actualización del 2026-09-04 (H-14b, el pack re-emitido con `cpu-independent=1`)

**54 keys** bajo `v0/`: las **dos piezas H.264** y **todo lo que sale de ellas
por remux** (los 16 segmentos TS, los 16 CMAF, los 16 `chunk` de DASH, los dos
`init`, `dash/manifest.mpd` y `v0/MANIFEST.tsv`). El bucket sigue con **62
keys**: no se agregó ni se borró ninguna, se reemplazó contenido.

**Qué NO cambió, y por qué importa:** `v0-vp9.webm` y `v0-vp9-alpha.webm`
salieron **byte-idénticos** al pack del 2026-09-01 (mismo md5), y los dos
`stream.m3u8` también (son listas de nombres y duraciones, que no se movieron).
O sea que la re-emisión tocó exactamente el carril que se quiso tocar. Los 16
segmentos de `hls-fmp4/` siguen siendo byte-idénticos a los 16 `chunk` de
`dash/`, uno a uno, como en el pack anterior.

| key | bytes | md5 | qué cambió |
|---|---|---|---|
| `v0/v0-h264-baseline.mp4` | 9553193 | `761cd4c023b53fe449c5ee0ab7f6ad9e` | re-emitida con `cpu-independent=1` (+1.478 B, +0,015 %) |
| `v0/v0-h264-main.mp4` | 8681167 | `50348aaccf07a43becd915f289b91b72` | ídem (−5.271 B, −0,061 %) |
| `v0/MANIFEST.tsv` | 1528 | `347a4eb8cbcfb33489363eb717f75e11` | los SHA-256 de las dos piezas H.264 |
| `v0/hls-ts/seg000..015.ts` | — | ver filas | remux de la baseline nueva |
| `v0/hls-fmp4/init.mp4` + `seg000..015.m4s` | — | ver filas | ídem |
| `v0/dash/init.m4s` + `chunk-00001..16.m4s` + `manifest.mpd` | — | ver filas | ídem |

SHA-256 de las dos piezas, para pinear por contenido:

- `v0-h264-baseline.mp4` → `abe6caf9fa545da428792accad163477a1ba58fe9275b87f24b241636fa6f63d`
- `v0-h264-main.mp4` → `1f92c55217dce6334232342bf7d9674355fc179954f5000f6a6ff8f77af0b95f`

Esas huellas ya no dependen del runner: son las mismas que H-14 midió en Intel
8370C y 8573C, y las que dieron ahora AMD EPYC 9V74 (pack) y 7763 (corrida de
determinismo). Cuatro CPUs, un solo archivo.

Verificación tras subir: `GET https://iargen.com/player/v0/<key>?x=<nonce>`
→ SHA-256 igual al del archivo local en las 54; token de subida quemado.

## Actualización del 2026-09-04 (H-12b, la prueba de techo que no cierra la app)

**2 keys** bajo `v0/`: `index.html` (regenerada = `frontend/v0.html`) y
`vgencache.js`. El bucket sigue con **62 keys**. Orden respetado: las dos
commiteadas en `main` antes de subirlas.

| key | bytes | md5 | qué es |
|---|---|---|---|
| `v0/index.html` | 54349 | `836ae47ed2c40fdd7f277eb993276650` | techo en tandas de 5 MB hasta 50, cuota declarada reportada primero, `83` que arranca VP9 en bucle y avisa si falta el gesto, caídos que no pueden ser negativos |
| `v0/vgencache.js` | 10786 | `8cfb75a0b598d742fee3f5971cac9387` | `TANDA_MB = 5`: `noise()` rechaza que le pidan más de una tanda de una vez |

Por qué importa el segundo: el límite de una tanda lo cumple ahora el módulo y
no la disciplina de quien lo llama. Pedir 50 MB contiguos —y clonarlos para
guardarlos— fue lo que cerró la app de la caja el 2026-09-04, y una app cerrada
no informa ningún techo.

Verificación tras subir: `GET https://iargen.com/player/v0/<key>?x=<nonce>`
→ SHA-256 igual al del archivo local en las dos; token de subida quemado.

## Actualización del 2026-09-04 (H-16, Hobo y la página reformada)

**2 keys** bajo `v0/`: `index.html` (regenerada = `frontend/v0.html`) y
**`HoboStd.ttf`** (nueva). El bucket pasa a **63 keys**.

| key | bytes | md5 | qué es |
|---|---|---|---|
| `v0/index.html` | 59530 | `5d3b22e235c292bec371de064cb3ab81` | tres columnas (teclas a la izquierda, video, tabla con el alto entero); solo 12 teclas a la vista; `1` = lo que falta, `89` = correr todo; la capa dibuja con Hobo |
| `v0/HoboStd.ttf` | 31444 | `56461958360533730babbd1bcc04ca77` | la fuente de la capa (OpenType CFF, la que pasó el operador) |

**Un detalle deliberado sobre el tipo de contenido.** El Worker no tiene `ttf`
en su tabla, así que la fuente se sirve como `application/octet-stream`. No se
tocó el Worker a propósito: cambiarlo obliga a re-desplegar el script (todas las
demás subidas son solo R2), y los navegadores **no** exigen un tipo MIME para
las fuentes de `@font-face`. Si aun así la caja la rechazara, la página lo dice
sola —el reporte saldría con `fuente fallback`— y ahí sí la corrección es una
línea: sumar `ttf` a `TYPES` en `worker.js`.

**Licencia:** `HoboStd.ttf` es una fuente de Adobe, publicada acá solo para
**probar** en los aparatos. El operador cerró el punto el 2026-09-04: «no la voy
a usar en el producto a la fuente, es una prueba… luego usaremos otras». O sea
que no hay nada que revisar para el producto; la fuente del producto se elige
después, y esta se puede sacar del bucket el día que deje de hacer falta.

Verificación tras subir: `GET https://iargen.com/player/v0/<key>?x=<nonce>`
→ SHA-256 igual al del archivo local en las dos; token de subida quemado.

### Corrección del mismo día (H-16, lo que apareció al probar la página)

`v0/index.html` → **60541 B**, md5 `042cf70a68ab86786e7d14c7cf6d600e`. Dos arreglos que salieron de abrir la
página publicada en un navegador y medirla, no de leerla:

1. **La detección de la fuente pasa a M contra i.** La versión anterior comparaba
   el ancho de una frase contra monospace y el margen era de **1,5 px sobre 285**
   (medido: 285,9 contra 284,4). Andaba, pero por poco. Ahora se comparan
   `MMMMM` e `iiiii` **en la misma familia**: monospace le da a toda letra el
   mismo avance, así que anchos distintos solo pueden venir de Hobo. Medido en el
   mismo navegador: 170,2 contra 53,2.
2. **La columna de teclas dejaba de entrar en pantallas angostas** (a 399 px
   mostraba «cache: gua…»). Ahora tiene un piso de 200 px acotado a un tercio del
   ancho, y `box-sizing: border-box` para que el relleno no la monte 14 px sobre
   el video.

**Comprobado sobre lo publicado:** la fuente carga y se detecta pese a servirse
como `application/octet-stream`, el `83` arranca VP9 en bucle y la capa pinta
encima del video.

### Segunda corrección del mismo día (H-16, la carrera del `83`)

`v0/index.html` → **61329 B**, md5 `8fd7a9c6ad7a6e536f02297877829316`. Apretar `83` **antes** de que llegara el
manifiesto dejaba la capa encendida sobre un `<video>` vacío: el mismo síntoma
que el operador reportó en la caja, por otra causa. Ahora reintenta cada 300 ms
hasta 6 s y se corta solo si mientras tanto se apagó la capa.

## Actualización del 2026-09-04 (W-26b, la raíz auditada y puesta al día)

Antes de tocar nada se **auditó**: se bajaron las 16 rutas de código de cada una
de las cuatro carpetas (`/`, `/1280-15/`, `/1280-12/`, `/1920-10/`) y se
compararon byte a byte contra el repo. Resultado:

| | keys |
|---|---:|
| iguales al repo | 56 |
| distintas | 8 |

Las 8 distintas son **la misma página en cuatro carpetas**: `index.html` y
`live-player.html`, que en el bucket eran byte-idénticas entre sí
(`505071f1…`, 26.679 B) y no traían **W-26**. Lo único que les faltaba es esto:

```
-    if(!textLayer){
+    if(!textLayer && qs("renderer")!=="canvas2d"){
```

O sea el escape `?renderer=canvas2d`, que en la caja evita el pantallazo blanco
de DIAG-002. Todo lo demás —incluido `playloop.js`, el motor único de
W-22..W-25— ya estaba al día en las cuatro carpetas.

**Dos cosas que la auditoría confirma y conviene no volver a suponer:** las
cuatro carpetas siguen sirviendo copias **byte-idénticas** del código, y
`index.html` sigue siendo `live-player.html` (mismo digest, ahora
`ba612f0dcb61317c9753ba77842e4252`).

**Corrección del manifiesto:** `playloop.js` estaba servido en las cuatro
carpetas desde el 2026-08-31 pero **no figuraba** en este archivo. Se agregaron
sus 4 filas. Este manifiesto es el registro de lo desplegado: una key servida y
no anotada es una mentira silenciosa.

| key | bytes | md5 |
|---|---:|---|
| `index.html` y `live-player.html`, en las 4 carpetas (8 keys) | 27004 | `ba612f0dcb61317c9753ba77842e4252` |
| `playloop.js`, en las 4 carpetas (4 filas nuevas, ya servidas) | 10999 | `dcfbf631f50112547f742d87284352b1` |

Verificación tras subir: `GET https://iargen.com/player/<key>?x=<nonce>`
→ SHA-256 igual al del archivo local en las 8; token de subida quemado.

## Actualización del 2026-09-04 (H-18, el segundo `<video>`)

`v0/index.html` → **65383 B**, md5 `4c1e4bd3a344738087bc2295a5d27596`. Tecla **`87`**: el loop VP9 abajo y
`v0-vp9-alpha` **encima**, en un segundo `<video>` del tamaño del rectángulo de
la capa. La fila mide el de abajo como cualquier otra y la nota trae los cuadros
del de arriba: si solo se midiera uno, la prueba no contestaría la pregunta del
operador —si un efecto puede **ser** video en vez de estar horneado—.

Dos gates viejos chocaban con esto por diseño y se **reformularon, no se
aflojaron**: «una sola etiqueta `<video>`» pasa a «un solo `<video>` para las
piezas, más exactamente uno para el efecto», y «una sola `.pause()`» pasa a
«el `<video>` de las piezas sigue con una sola pausa, la del `0`; la otra es la
del efecto al terminar su prueba».

### Corrección del mismo día (H-18, el contador del video de arriba)

`v0/index.html` → **66267 B**, md5 `5946130981042e522864d86c2e3d4aad`. Corriendo la prueba **dos veces
seguidas** —única forma de verlo— la segunda informaba «1/2 caídos» arriba: la
línea de base se tomaba al pedirle que suene, o sea contra los contadores de la
pasada anterior que `load()` acababa de poner en cero. Ahora se arma en la
primera vuelta con `currentTime > 0`, y si nunca sonó la fila lo dice.

## 2026-09-04 (noche) — H-18b + H-20: tres keys

`v0/v0-vp9-alpha.webm` → **2.434.369 B**, md5 `b011a443f2d31956fa117958e9f6b37a`
(era 4.664.676 B: **−47,8 %**, porque la pieza pasó a ser casi toda
transparente). `v0/MANIFEST.tsv` → **1.538 B**, md5
`fbad17b4fc5e838214a70fcae0258dda`. `v0/index.html` → **76.483 B**, md5
`b70f7286b1a8c1731a66b14ce8dbfd91`.

**Y solo tres.** El pack se re-emitió entero (run `33912699058`, workflow
`emitir-v0`) y las otras seis piezas —las dos H.264, VP9, y los tres
empaquetados con sus segmentos— salieron **byte-idénticas** a las publicadas el
2026-09-04 por la mañana, en otro runner. Es la segunda confirmación del
invariante 7 después de H-14b, y esta vez gratis: se verificó comparando md5
contra este mismo manifiesto antes de subir nada.

**Qué cambió en la pieza con alfa.** El operador rechazó el armado de H-18: el
segundo `<video>` iba encogido y corrido, y la pieza llevaba **el RGB del propio
máster**, así que superpuesta exacta habría sido indistinguible de lo de abajo.
Ahora lleva **papelitos de colores sobre transparencia total** —contenido que no
existe en el video de abajo— y el segundo `<video>` va exactamente sobre el
primero. El generador usa **enteros y ondas triangulares, nunca `sin`/`cos`**:
1 ULP de diferencia entre dos libm movería un borde y cambiaría los bytes.

**Qué cambió en la página** (H-20): el video a **pantalla entera** en cuatro
escalones (teclas `70` y `73`) y el reporte en **dos columnas** con el `88` para
volver, con la letra buscada por medición hasta que entra. Deja de vivir en un
`<textarea>`, donde el foco adentro apagaba el mando numérico entero.

## 2026-09-04 (noche, 2ª foto) — H-21: una key

| key | bytes | md5 |
|---|---|---|
| `v0/index.html` | 80.329 | `ad073ac10fa236754b02b3844b7a9316` |

La foto de la caja cerró H-18b y H-20 —dos planos de video se sostienen (2/154
y 1/141), la superficie 4K no le cuesta al `<video>` (1/155), pero **video +
video alfa + canvas juntos dan 11 %**: el presupuesto de composición es **dos
planos, no tres**—. Sobre esa foto el operador pidió mirar los dos planos **sin
los cortes de la medición**: los cortes son del `70`, que corre cuatro
escalones y para entre uno y otro.

**Qué cambió en la página**: tecla **`71`**, los dos planos a toda la
superficie, **en bucle y sin un solo corte**, hasta que se apague. No agrega
fila al reporte —no mide, muestra— pero el zócalo lleva los **caídos vivos de
los dos**, para que el ojo y los números se miren juntos. El reloj se apaga en
`stopAll()`, no en la tecla, para que las dos no se llamen en círculo. Son
**14 teclas a la vista**.
